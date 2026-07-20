"""TPAP protocol client for Tapo P110.

Implements the TP-Link Adaptive Protocol (TPAP) using SPAKE2+ P-256
key exchange and AES-128-CCM encrypted data channel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
import urllib.error
import urllib.request
from typing import Any

from cryptography.hazmat.primitives import hashes as crypto_hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import NIST256p, ellipticcurve


class TapoAuthError(Exception):
    """Authentication failed."""


class TapoConnectionError(Exception):
    """Connection failed."""


# SPAKE2+ P-256 suite constants (suite type 1)
_M_COMP = bytes.fromhex("02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f")
_N_COMP = bytes.fromhex("03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49")
_PAKE_CONTEXT_TAG = b"PAKE V1"

_CIPHER_PARAMS = {
    "aes_128_ccm": (
        b"tp-kdf-salt-aes128-key",
        b"tp-kdf-info-aes128-key",
        b"tp-kdf-salt-aes128-iv",
        b"tp-kdf-info-aes128-iv",
        16,
    ),
}

_NIST = NIST256p
_CRYPTO_CURVE = ec.SECP256R1()
_CURVE = _NIST.curve
_GENERATOR = _NIST.generator
_ORDER: int = _NIST.generator.order()  # type: ignore[reportAssignmentType]


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(data: str) -> bytes:
    return base64.b64decode(data)


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hkdf_expand(label: str, prk: bytes, length: int) -> bytes:
    return HKDF(
        algorithm=crypto_hashes.SHA256(),
        length=length,
        salt=b"\x00" * length,
        info=label.encode(),
    ).derive(prk)


def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def _len8le(data: bytes) -> bytes:
    return len(data).to_bytes(8, "little") + data


def _encode_w(value: int) -> bytes:
    ml = 1 if value == 0 else (value.bit_length() + 7) // 8
    u = value.to_bytes(ml, "big", signed=False)
    if ml % 2 == 0:
        return u
    if u[0] & 0x80:
        return b"\x00" + u
    return u


def _sec1_to_xy(sec1: bytes) -> tuple[int, int]:
    pk = ec.EllipticCurvePublicKey.from_encoded_point(_CRYPTO_CURVE, sec1)
    return pk.public_numbers().x, pk.public_numbers().y


def _xy_to_uncompressed(x: int, y: int) -> bytes:
    pk = ec.EllipticCurvePublicNumbers(x, y, _CRYPTO_CURVE).public_key()
    return pk.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


def _post_json(url: str, payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise TapoConnectionError(f"HTTP error {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise TapoConnectionError(str(exc.reason)) from exc


class TapoP110Client:
    """Client for Tapo P110 using TPAP protocol."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._base_url = f"http://{host}"
        self._ds_url: str | None = None
        self._session_key: bytes | None = None
        self._base_nonce: bytes | None = None
        self._seq: int | None = None
        self._session_expiry: float = 0
        self._device_mac: str = ""
        self._device_info: dict[str, Any] = {}

    def _ensure_session(self) -> None:
        if self._ds_url is None or time.monotonic() > self._session_expiry:
            self.discover_and_handshake()

    def discover_and_handshake(self) -> dict[str, Any]:
        """Perform full TPAP handshake and return device info."""
        # Step 1: Discover
        discover_resp = _post_json(
            self._base_url,
            {"method": "login", "params": {"sub_method": "discover"}},
        )
        if discover_resp.get("error_code") != 0:
            raise TapoConnectionError(f"Discover failed: {discover_resp.get('error_code')}")
        result = discover_resp["result"]
        self._device_mac = result.get("mac", "")

        # Step 2: PAKE Register
        user_random = _b64(secrets.token_bytes(32))
        register_params = {
            "sub_method": "pake_register",
            "username": _md5_hex("admin"),
            "user_random": user_random,
            "cipher_suites": [1],
            "encryption": ["aes_128_ccm"],
            "passcode_type": "userpw",
            "stok": None,
        }
        register_resp = _post_json(
            self._base_url,
            {"method": "login", "params": register_params},
        )
        if register_resp.get("error_code") != 0:
            raise TapoAuthError(f"Register failed: {register_resp.get('error_code')}")
        reg_result = register_resp["result"]

        # Build credentials (passwd_id=2 → sha1(password))
        extra_crypt = reg_result.get("extra_crypt", {})
        params = extra_crypt.get("params", {})
        passwd_id = int(params.get("passwd_id", 0))
        if passwd_id == 2:
            credentials_string = _sha1_hex(self._password)
        elif passwd_id == 1:
            from passlib.hash import md5_crypt  # type: ignore[import-not-found,attr-defined]

            prefix = params.get("passwd_prefix", "")
            credentials_string = md5_crypt.using(salt=prefix[3:11] if prefix else "").hash(self._password)
        else:
            credentials_string = self._password

        # Step 3: SPAKE2+ computation
        dev_random = reg_result["dev_random"]
        dev_salt = reg_result["dev_salt"]
        dev_share = reg_result["dev_share"]
        iterations = int(reg_result["iterations"])

        i_d = 40  # 32 + 8
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            credentials_string.encode(),
            _unb64(dev_salt),
            iterations,
            2 * i_d,
        )
        w = int.from_bytes(derived[:i_d], "big") % _ORDER
        h = int.from_bytes(derived[i_d:], "big") % _ORDER
        x = secrets.randbelow(_ORDER - 1) + 1

        m_x, m_y = _sec1_to_xy(_M_COMP)
        n_x, n_y = _sec1_to_xy(_N_COMP)
        m_pt = ellipticcurve.Point(_CURVE, m_x, m_y, _ORDER)
        n_pt = ellipticcurve.Point(_CURVE, n_x, n_y, _ORDER)

        l_pt = x * _GENERATOR + w * m_pt
        l_enc = _xy_to_uncompressed(l_pt.x(), l_pt.y())

        r_x, r_y = _sec1_to_xy(_unb64(dev_share))
        r_pt = ellipticcurve.Point(_CURVE, r_x, r_y, _ORDER)
        r_enc = _xy_to_uncompressed(r_pt.x(), r_pt.y())

        r_prime = r_pt + (-(w * n_pt))
        z_enc = _xy_to_uncompressed((x * r_prime).x(), (x * r_prime).y())
        v_enc = _xy_to_uncompressed(
            ((h % _ORDER) * r_prime).x(),
            ((h % _ORDER) * r_prime).y(),
        )
        m_enc = _xy_to_uncompressed(m_pt.x(), m_pt.y())
        n_enc = _xy_to_uncompressed(n_pt.x(), n_pt.y())

        ctx_hash = _sha256(_PAKE_CONTEXT_TAG + _unb64(user_random) + _unb64(dev_random))
        transcript = (
            _len8le(ctx_hash)
            + _len8le(b"")
            + _len8le(b"")
            + _len8le(m_enc)
            + _len8le(n_enc)
            + _len8le(l_enc)
            + _len8le(r_enc)
            + _len8le(z_enc)
            + _len8le(v_enc)
            + _len8le(_encode_w(w))
        )
        th = _sha256(transcript)

        ck = _hkdf_expand("ConfirmationKeys", th, 64)
        shared_key = _hkdf_expand("SharedKey", th, 32)
        user_confirm = _hmac_sha256(ck[:32], r_enc)
        expected_dev_confirm = _hmac_sha256(ck[32:64], l_enc)

        # Step 4: PAKE Share
        share_resp = _post_json(
            self._base_url,
            {
                "method": "login",
                "params": {
                    "sub_method": "pake_share",
                    "user_share": _b64(l_enc),
                    "user_confirm": _b64(user_confirm),
                },
            },
        )
        if share_resp.get("error_code") != 0:
            raise TapoAuthError(f"Share failed: {share_resp.get('error_code')}")
        share_result = share_resp["result"]
        dev_confirm = share_result.get("dev_confirm", "").lower()
        if dev_confirm != _b64(expected_dev_confirm).lower():
            raise TapoAuthError("Device confirmation mismatch")

        session_id = share_result.get("sessionId") or share_result.get("stok")
        start_seq = int(share_result.get("start_seq"))
        if not session_id:
            raise TapoAuthError("No session ID returned")

        # Derive session keys
        ks, ki, ns, ni, kl = _CIPHER_PARAMS["aes_128_ccm"]
        self._session_key = HKDF(crypto_hashes.SHA256(), kl, ks, ki).derive(shared_key)
        self._base_nonce = HKDF(crypto_hashes.SHA256(), 12, ns, ni).derive(shared_key)
        self._ds_url = f"{self._base_url}/stok={session_id}/ds"
        self._seq = start_seq
        self._session_expiry = time.monotonic() + 86400

        # Get device info
        self._device_info = self._send_request("get_device_info", {})
        return {**self._device_info, "mac": self._device_mac}

    def discover_only(self) -> dict[str, Any]:
        """Perform only the discover step (no PAKE) — returns {'mac': ...}."""
        resp = _post_json(
            self._base_url,
            {"method": "login", "params": {"sub_method": "discover"}},
        )
        if resp.get("error_code") != 0:
            raise TapoConnectionError(f"Discover failed: {resp.get('error_code')}")
        return {"mac": resp["result"].get("mac", "")}

    def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        _retried: bool = False,
    ) -> dict[str, Any]:
        """Send encrypted request to device.

        ``_retried`` bounds retry recursion to one level: a 403 or decrypt
        failure re-handshakes and retries exactly once; a second failure is
        raised as ``TapoConnectionError`` instead of recursing without bound
        (a device that persistently 403s would otherwise exhaust the stack).
        """
        self._ensure_session()
        if self._ds_url is None or self._seq is None:
            raise TapoConnectionError("No active session")
        if self._session_key is None or self._base_nonce is None:
            raise TapoConnectionError("No session keys")

        request_body = json.dumps({"method": method, "params": params or {}})
        seq = self._seq
        nonce = self._base_nonce[:-4] + struct.pack(">I", seq)
        cipher = AESCCM(self._session_key, tag_length=16)
        encrypted = cipher.encrypt(nonce, request_body.encode(), None)
        payload = struct.pack(">I", seq) + encrypted

        req = urllib.request.Request(self._ds_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            resp_data = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                if _retried:
                    raise TapoConnectionError("Repeated 403 after re-handshake") from exc
                self._ds_url = None
                self._ensure_session()
                return self._send_request(method, params, _retried=True)
            raise TapoConnectionError(f"HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TapoConnectionError(str(exc.reason)) from exc

        resp_seq = struct.unpack(">I", resp_data[:4])[0]
        resp_nonce = self._base_nonce[:-4] + struct.pack(">I", resp_seq)
        try:
            decrypted = cipher.decrypt(resp_nonce, resp_data[4:], None)
        except Exception as exc:
            if _retried:
                raise TapoConnectionError("Repeated decrypt failure after re-handshake") from exc
            self._ds_url = None
            self._ensure_session()
            return self._send_request(method, params, _retried=True)

        self._seq = seq + 1
        result = json.loads(decrypted)
        if result.get("error_code") != 0:
            ec_val = result.get("error_code")
            if ec_val in (-2202, -2203):
                raise TapoAuthError(f"Auth error: {ec_val}")
        return result.get("result", result)

    # === Getters ===
    def get_device_info(self) -> dict[str, Any]:
        return self._send_request("get_device_info", {})

    def get_energy_usage(self) -> dict[str, Any]:
        return self._send_request("get_energy_usage", {})

    def get_current_power(self) -> dict[str, Any]:
        return self._send_request("get_current_power", {})

    def get_emeter_data(self) -> dict[str, Any]:
        return self._send_request("get_emeter_data", {})

    def get_device_usage(self) -> dict[str, Any]:
        return self._send_request("get_device_usage", {})

    def get_device_time(self) -> dict[str, Any]:
        return self._send_request("get_device_time", {})

    def get_led_info(self) -> dict[str, Any]:
        return self._send_request("get_led_info", {})

    def get_countdown_rules(self) -> dict[str, Any]:
        return self._send_request("get_countdown_rules", {})

    def get_antitheft_rules(self) -> dict[str, Any]:
        return self._send_request("get_antitheft_rules", {})

    def get_auto_update_info(self) -> dict[str, Any]:
        return self._send_request("get_auto_update_info", {})

    def get_auto_off_config(self) -> dict[str, Any]:
        return self._send_request("get_auto_off_config", {})

    # === Setters ===
    def set_device_on(self, on: bool) -> None:
        self._send_request("set_device_info", {"device_on": on})

    def set_led_rule(self, rule: str) -> None:
        """Set LED rule: 'always', 'auto', or 'never'."""
        self._send_request("set_led_info", {"led_rule": rule})

    def set_default_state(self, state_type: str) -> None:
        """Set default state: 'last_states', 'on', or 'off'.

        Device stores on/off as {"type": "custom", "state": {"on": true/false}}.
        """
        if state_type == "last_states":
            self._send_request("set_device_info", {"default_states": {"type": "last_states"}})
        elif state_type == "on":
            self._send_request("set_device_info", {"default_states": {"type": "custom", "state": {"on": True}}})
        elif state_type == "off":
            self._send_request("set_device_info", {"default_states": {"type": "custom", "state": {"on": False}}})

    def set_auto_update(self, enable: bool) -> None:
        """Toggle auto firmware update. Must send all fields or device rejects."""
        info = self.get_auto_update_info()
        self._send_request(
            "set_auto_update_info",
            {
                "enable": enable,
                "time": info.get("time", 180),
                "random_range": info.get("random_range", 120),
            },
        )

    def set_auto_off_enabled(self, enable: bool) -> None:
        config = self.get_auto_off_config()
        self._send_request("set_auto_off_config", {"enable": enable, "delay_min": config.get("delay_min", 120)})

    def set_auto_off_minutes(self, delay_min: int) -> None:
        config = self.get_auto_off_config()
        self._send_request("set_auto_off_config", {"enable": config.get("enable", False), "delay_min": delay_min})

    def get_protection_power(self) -> dict[str, Any]:
        return self._send_request("get_protection_power", {})

    def get_max_power(self) -> dict[str, Any]:
        return self._send_request("get_max_power", {})

    def set_power_protection_threshold(self, threshold: int) -> None:
        """Set power protection threshold. 0 disables, >0 enables."""
        if threshold == 0:
            self._send_request("set_protection_power", {"enabled": False, "protection_power": 0})
        else:
            self._send_request("set_protection_power", {"enabled": True, "protection_power": threshold})

    def set_power_protection_enabled(self, enabled: bool) -> None:
        """Enable/disable power protection, preserving current threshold."""
        pp = self.get_protection_power()
        threshold = pp.get("protection_power", 0)
        if enabled and threshold == 0:
            max_p = self.get_max_power().get("max_power", 3580)
            threshold = max_p
        self._send_request("set_protection_power", {"enabled": enabled, "protection_power": threshold})

    # === Batch polling ===
    def get_all_data(self) -> dict[str, Any]:
        """Fetch all polling data in one call sequence."""
        data = {}
        # First request must succeed — if it fails, the device is unreachable
        # or the session is stale. Don't return partial data.
        data["device_info"] = self._send_request("get_device_info", {})
        for key, method in [
            ("energy_usage", "get_energy_usage"),
            ("emeter_data", "get_emeter_data"),
            ("device_usage", "get_device_usage"),
            ("device_time", "get_device_time"),
            ("led_info", "get_led_info"),
            ("auto_update_info", "get_auto_update_info"),
            ("auto_off_config", "get_auto_off_config"),
            ("protection_power", "get_protection_power"),
            ("max_power", "get_max_power"),
        ]:
            try:
                data[key] = self._send_request(method, {})
            except TapoAuthError:
                # A genuine auth failure is not best-effort — surface it so the
                # coordinator raises ConfigEntryAuthFailed (re-auth flow).
                raise
            except Exception:
                # Best-effort: partial data is acceptable for these endpoints.
                pass
        return data

    def shutdown(self) -> None:
        """Clear session state."""
        self._ds_url = None
        self._session_key = None
        self._base_nonce = None
        self._seq = None
