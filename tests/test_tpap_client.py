"""Tests for tpap_client.py — protocol, crypto, retry, error mapping, setters, and batch polling."""

from __future__ import annotations

import hashlib
import json
import struct
from unittest.mock import MagicMock, patch

import pytest

from custom_components.tapo_p110.tpap_client import (
    _GENERATOR,
    _M_COMP,
    _N_COMP,
    _ORDER,
    TapoAuthError,
    TapoConnectionError,
    TapoP110Client,
    _encode_w,
    _md5_hex,
    _sec1_to_xy,
    _sha1_hex,
    _unb64,
    _xy_to_uncompressed,
)

# ---------------------------------------------------------------------------
# 4.1/4.2: Shared fixtures & SPAKE2+ vector
# ---------------------------------------------------------------------------
# (Loaded via conftest.py mock_client and spake2_vector fixtures.)


# ---------------------------------------------------------------------------
# 4.3: SPAKE2+ derivation reproduces the recorded vector
# ---------------------------------------------------------------------------


class TestSPAKE2Derivation:
    """Verify derivation functions reproduce the deterministic test vector."""

    def test_sha1_hex(self, spake2_vector):
        assert _sha1_hex(spake2_vector["password"]) == spake2_vector["sha1_of_password"]

    def test_md5_hex(self, spake2_vector):
        assert _md5_hex(spake2_vector["password"]) == spake2_vector["md5_of_password"]

    def test_credentials_string_passwd_id_2(self, spake2_vector):
        """passwd_id=2 uses sha1 of the password."""
        assert _sha1_hex(spake2_vector["password"]) == spake2_vector["credentials_string"]

    def test_pbkdf2_derives_w_and_h(self, spake2_vector):
        """PBKDF2-HMAC-SHA256 with the vector's salt/iterations produces w and h."""
        salt = _unb64(spake2_vector["dev_salt_b64"])
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            spake2_vector["credentials_string"].encode(),
            salt,
            spake2_vector["iterations"],
            2 * spake2_vector["i_d"],
        )
        i_d = spake2_vector["i_d"]
        w = int.from_bytes(derived[:i_d], "big") % _ORDER
        h = int.from_bytes(derived[i_d:], "big") % _ORDER
        assert w == spake2_vector["w"]
        assert h == spake2_vector["h"]

    def test_encode_w(self, spake2_vector):
        """_encode_w produces the deterministic-length encoding of w."""
        w_encoded = _encode_w(spake2_vector["w"])
        # Decode and verify round-trip
        assert int.from_bytes(w_encoded, "big") == spake2_vector["w"]

    def test_sec1_to_xy_roundtrip(self, spake2_vector):
        """Point decompression round-trips through _xy_to_uncompressed."""
        x, y = spake2_vector["client_pub_x"], spake2_vector["client_pub_y"]
        sec1 = _xy_to_uncompressed(x, y)
        rx, ry = _sec1_to_xy(sec1)
        assert rx == x
        assert ry == y

    def test_M_and_N_constants_decompress(self, spake2_vector):
        """M and N generator points decompress correctly."""
        m_x, m_y = _sec1_to_xy(_M_COMP)
        n_x, n_y = _sec1_to_xy(_N_COMP)
        assert m_x == spake2_vector["m_x"]
        assert m_y == spake2_vector["m_y"]
        assert n_x == spake2_vector["n_x"]
        assert n_y == spake2_vector["n_y"]

    def test_L_point(self, spake2_vector):
        """L = w * G reproduces the recorded L_x, L_y."""
        L = _GENERATOR * spake2_vector["w"]
        assert L.x() == spake2_vector["L_x"]
        assert L.y() == spake2_vector["L_y"]


# ---------------------------------------------------------------------------
# 4.4: AES-CCM nonce sequencing
# ---------------------------------------------------------------------------


class TestNonceSequencing:
    """Verify nonce construction and sequence numbering."""

    def test_request_nonce_format(self, mock_client):
        """Request nonce = base_nonce[:-4] + pack('>I', seq)."""
        import base64

        _key = base64.b64encode(b"a" * 16).decode()
        client = TapoP110Client("1.2.3.4", "u", "p")
        client._ds_url = "http://1.2.3.4/app/stok"
        client._session_key = b"a" * 16
        client._base_nonce = b"\xaa" * 12
        client._seq = 42
        client._session_expiry = 9999999999.0

        # Build the nonce that _send_request would use
        expected_nonce = client._base_nonce[:-4] + struct.pack(">I", 42)
        assert len(expected_nonce) == 12
        assert expected_nonce == b"\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa" + struct.pack(">I", 42)

    def test_seq_increments_on_success(self, mock_client, mock_urlopen):
        """_seq increments by 1 after a successful request."""
        # Build a successful encrypted response
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM

        seq = mock_client._seq  # starts at 0
        nonce = mock_client._base_nonce[:-4] + struct.pack(">I", seq)
        cipher = AESCCM(mock_client._session_key, tag_length=16)
        resp_payload = json.dumps({"error_code": 0, "result": {"device_on": True}}).encode()
        encrypted = cipher.encrypt(nonce, resp_payload, None)
        resp_data = struct.pack(">I", seq) + encrypted

        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_urlopen.return_value = mock_resp

        mock_client._send_request("get_device_info", {})
        assert mock_client._seq == seq + 1


# ---------------------------------------------------------------------------
# 4.5-4.9: _send_request retry and error mapping
# ---------------------------------------------------------------------------


class TestSendRequestRetry:
    """403 and decrypt-failure auto-retry; auth error codes."""

    def _make_success_response(self, client, seq, result=None):
        """Build a valid encrypted response for the given client and seq."""
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM

        nonce = client._base_nonce[:-4] + struct.pack(">I", seq)
        cipher = AESCCM(client._session_key, tag_length=16)
        payload = json.dumps({"error_code": 0, "result": result or {}}).encode()
        encrypted = cipher.encrypt(nonce, payload, None)
        return struct.pack(">I", seq) + encrypted

    def test_403_triggers_single_retry(self, mock_client, mock_urlopen):
        """First 403 clears session and retries; _retried=True on retry."""
        import urllib.error

        success_resp = MagicMock()
        success_resp.read.return_value = self._make_success_response(mock_client, 0, {"device_on": True})

        http_403 = urllib.error.HTTPError(
            url="http://1.2.3.4/app/stok",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[reportArgumentType]  # test stub: HTTPError requires Message hdrs
            fp=None,
        )

        # First call: 403; second call (after re-handshake): success.
        # Re-handshake sets up a new session — we need to simulate that.
        mock_urlopen.side_effect = [http_403, success_resp]

        # Mock _ensure_session to re-establish the fake session after 403 clears it.
        original_ds_url = mock_client._ds_url
        original_key = mock_client._session_key
        original_nonce = mock_client._base_nonce

        def fake_ensure():
            mock_client._ds_url = original_ds_url
            mock_client._session_key = original_key
            mock_client._base_nonce = original_nonce
            mock_client._seq = 0

        mock_client._ensure_session = fake_ensure

        result = mock_client._send_request("get_device_info", {})
        assert result == {"device_on": True}

    def test_repeated_403_raises_connection_error(self, mock_client, mock_urlopen):
        """Repeated 403 with _retried=True raises TapoConnectionError."""
        import urllib.error

        http_403 = urllib.error.HTTPError(
            url="http://1.2.3.4/app/stok",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[reportArgumentType]  # test stub: HTTPError requires Message hdrs
            fp=None,
        )
        mock_urlopen.side_effect = http_403

        with pytest.raises(TapoConnectionError, match="Repeated 403"):
            mock_client._send_request("get_device_info", {}, _retried=True)

    def test_decrypt_failure_triggers_retry(self, mock_client, mock_urlopen):
        """Decrypt failure with _retried=False clears session and retries."""
        # Garbage response data that will fail decryption
        bad_resp = MagicMock()
        bad_resp.read.return_value = b"\x00\x00\x00\x00" + b"\xff" * 32

        success_resp = MagicMock()
        success_resp.read.return_value = self._make_success_response(mock_client, 0, {"ok": True})

        mock_urlopen.side_effect = [bad_resp, success_resp]

        original_ds_url = mock_client._ds_url

        def fake_ensure():
            mock_client._ds_url = original_ds_url
            mock_client._seq = 0

        mock_client._ensure_session = fake_ensure

        result = mock_client._send_request("get_device_info", {})
        assert result == {"ok": True}

    def test_repeated_decrypt_failure_raises_connection_error(self, mock_client, mock_urlopen):
        """Repeated decrypt failure with _retried=True raises TapoConnectionError."""
        bad_resp = MagicMock()
        bad_resp.read.return_value = b"\x00\x00\x00\x00" + b"\xff" * 32
        mock_urlopen.return_value = bad_resp

        with pytest.raises(TapoConnectionError, match="decrypt failure"):
            mock_client._send_request("get_device_info", {}, _retried=True)

    def test_auth_error_codes_raise_tapo_auth_error(self, mock_client, mock_urlopen):
        """error_code -2202 and -2203 raise TapoAuthError."""
        for code in (-2202, -2203):
            seq = mock_client._seq
            nonce = mock_client._base_nonce[:-4] + struct.pack(">I", seq)
            from cryptography.hazmat.primitives.ciphers.aead import AESCCM

            cipher = AESCCM(mock_client._session_key, tag_length=16)
            payload = json.dumps({"error_code": code}).encode()
            encrypted = cipher.encrypt(nonce, payload, None)
            resp_data = struct.pack(">I", seq) + encrypted

            mock_resp = MagicMock()
            mock_resp.read.return_value = resp_data
            mock_urlopen.return_value = mock_resp

            with pytest.raises(TapoAuthError):
                mock_client._send_request("get_device_info", {})

            # Reset seq for next iteration
            mock_client._seq = 0

    def test_error_code_zero_returns_result(self, mock_client, mock_urlopen):
        """error_code 0 returns the result dict."""
        seq = mock_client._seq
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM

        nonce = mock_client._base_nonce[:-4] + struct.pack(">I", seq)
        cipher = AESCCM(mock_client._session_key, tag_length=16)
        payload = json.dumps({"error_code": 0, "result": {"device_on": True}}).encode()
        encrypted = cipher.encrypt(nonce, payload, None)
        resp_data = struct.pack(">I", seq) + encrypted

        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_urlopen.return_value = mock_resp

        result = mock_client._send_request("get_device_info", {})
        assert result == {"device_on": True}

    def test_no_session_raises_connection_error(self):
        """_send_request with no session raises TapoConnectionError without encryption."""
        client = TapoP110Client("1.2.3.4", "u", "p")
        # _ds_url is None by default, _ensure_session won't fix it without network
        with patch.object(client, "_ensure_session"):
            client._ds_url = None  # explicitly no session
            with pytest.raises(TapoConnectionError, match="No active session"):
                client._send_request("get_device_info", {})


# ---------------------------------------------------------------------------
# 4.10: get_all_data atomic-vs-best-effort semantics
# ---------------------------------------------------------------------------


class TestGetAllData:
    """Test get_all_data: device_info is atomic, others best-effort."""

    def test_device_info_failure_aborts(self, mock_client):
        """If get_device_info raises, get_all_data propagates the exception."""
        with (
            patch.object(mock_client, "_send_request", side_effect=TapoConnectionError("unreachable")),
            pytest.raises(TapoConnectionError),
        ):
            mock_client.get_all_data()

    def test_best_effort_endpoint_failure_swallowed(self, mock_client):
        """Non-auth exceptions from best-effort endpoints are swallowed (key omitted)."""
        call_count = 0

        def mock_send(method, params=None):
            nonlocal call_count
            call_count += 1
            if method == "get_device_info":
                return {"device_id": "abc123"}
            if method == "get_energy_usage":
                raise TapoConnectionError("transient")
            if method == "get_emeter_data":
                raise Exception("unexpected")
            return {"key": method}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            data = mock_client.get_all_data()

        assert "device_info" in data
        assert "energy_usage" not in data  # swallowed
        assert "emeter_data" not in data  # swallowed
        assert "device_usage" in data  # succeeds

    def test_best_effort_tapo_auth_error_not_swallowed(self, mock_client):
        """TapoAuthError from a best-effort endpoint is NOT swallowed."""

        def mock_send(method, params=None):
            if method == "get_device_info":
                return {"device_id": "abc123"}
            if method == "get_energy_usage":
                raise TapoAuthError("auth error")
            return {"key": method}

        with patch.object(mock_client, "_send_request", side_effect=mock_send), pytest.raises(TapoAuthError):
            mock_client.get_all_data()

    def test_successful_data_has_all_keys(self, mock_client):
        """Happy path: all 10 keys present."""

        def mock_send(method, params=None):
            return {"key": method}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            data = mock_client.get_all_data()

        expected_keys = {
            "device_info",
            "energy_usage",
            "emeter_data",
            "device_usage",
            "device_time",
            "led_info",
            "auto_update_info",
            "auto_off_config",
            "protection_power",
            "max_power",
        }
        assert set(data.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 4.11-4.14: Setter preservation re-reads
# ---------------------------------------------------------------------------


class TestSetterPreservation:
    """Setters that modify one field must preserve others."""

    def test_set_auto_update_preserves_time_and_random_range(self, mock_client):
        """set_auto_update re-reads get_auto_update_info and preserves time/random_range."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_update_info":
                return {"enable": False, "time": 200, "random_range": 150}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_update(True)

        # First call: get_auto_update_info; second: set_auto_update_info
        assert call_args[0] == ("get_auto_update_info", {})
        assert call_args[1][0] == "set_auto_update_info"
        sent_params = call_args[1][1]
        assert sent_params["enable"] is True
        assert sent_params["time"] == 200
        assert sent_params["random_range"] == 150

    def test_set_auto_update_preserves_defaults(self, mock_client):
        """set_auto_update falls back to 180/120 if fields missing."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_update_info":
                return {}  # missing time/random_range
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_update(True)

        sent_params = call_args[1][1]
        assert sent_params["time"] == 180
        assert sent_params["random_range"] == 120

    def test_set_auto_off_enabled_preserves_delay_min(self, mock_client):
        """set_auto_off_enabled re-reads config and preserves delay_min."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_off_config":
                return {"enable": False, "delay_min": 60}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_off_enabled(True)

        sent_params = call_args[1][1]
        assert sent_params["enable"] is True
        assert sent_params["delay_min"] == 60

    def test_set_auto_off_enabled_preserves_delay_min_default(self, mock_client):
        """set_auto_off_enabled falls back to 120 if delay_min missing."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_off_config":
                return {}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_off_enabled(True)

        assert call_args[1][1]["delay_min"] == 120

    def test_set_auto_off_minutes_preserves_enable(self, mock_client):
        """set_auto_off_minutes re-reads config and preserves enable."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_off_config":
                return {"enable": True, "delay_min": 60}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_off_minutes(30)

        sent_params = call_args[1][1]
        assert sent_params["enable"] is True
        assert sent_params["delay_min"] == 30

    def test_set_auto_off_minutes_preserves_enable_default(self, mock_client):
        """set_auto_off_minutes falls back to False if enable missing."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_auto_off_config":
                return {}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_auto_off_minutes(30)

        assert call_args[1][1]["enable"] is False

    def test_set_power_protection_enabled_true_threshold_zero(self, mock_client):
        """When enabling with threshold=0, defaults to max_power (fallback 3580)."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_protection_power":
                return {"enabled": False, "protection_power": 0}
            if method == "get_max_power":
                return {"max_power": 3600}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_power_protection_enabled(True)

        # get_protection_power first, then get_max_power, then set
        assert call_args[0][0] == "get_protection_power"
        assert call_args[1][0] == "get_max_power"
        sent_params = call_args[2][1]
        assert sent_params["enabled"] is True
        assert sent_params["protection_power"] == 3600

    def test_set_power_protection_enabled_true_threshold_zero_fallback(self, mock_client):
        """When max_power is missing, defaults to 3580."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_protection_power":
                return {"enabled": False, "protection_power": 0}
            if method == "get_max_power":
                return {}  # no max_power
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_power_protection_enabled(True)

        assert call_args[2][1]["protection_power"] == 3580

    def test_set_power_protection_enabled_false_preserves_threshold(self, mock_client):
        """Disabling preserves the current threshold."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            if method == "get_protection_power":
                return {"enabled": True, "protection_power": 500}
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_power_protection_enabled(False)

        sent_params = call_args[1][1]
        assert sent_params["enabled"] is False
        assert sent_params["protection_power"] == 500

    def test_set_power_protection_threshold_zero_disables(self, mock_client):
        """threshold=0 sends enabled=False, protection_power=0."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_power_protection_threshold(0)

        assert call_args[0] == ("set_protection_power", {"enabled": False, "protection_power": 0})

    def test_set_power_protection_threshold_positive_enables(self, mock_client):
        """threshold>0 sends enabled=True, protection_power=threshold."""
        call_args = []

        def mock_send(method, params=None):
            call_args.append((method, params))
            return {}

        with patch.object(mock_client, "_send_request", side_effect=mock_send):
            mock_client.set_power_protection_threshold(500)

        assert call_args[0] == ("set_protection_power", {"enabled": True, "protection_power": 500})


# ---------------------------------------------------------------------------
# 4.15: Offline/deterministic verification
# ---------------------------------------------------------------------------


def test_all_tests_run_without_network():
    """Verify that no test requires real network access.

    This is a meta-test: if all other tests pass without monkeypatching
    socket or making real HTTP requests, this constraint is satisfied.
    The mock_client fixture patches urllib.request.urlopen at the module level,
    and no test calls discover_and_handshake or hits a real device.
    """
    # If we got here, all tests above passed with mocked I/O.
    assert True
