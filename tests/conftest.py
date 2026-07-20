"""Shared test fixtures for tapo_p110."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_urlopen():
    """Return a mock for urllib.request.urlopen that can be configured per-call.

    Usage in tests::

        def test_foo(mock_urlopen):
            mock_urlopen.side_effect = [response1, response2]
            client = TapoP110Client(...)
    """
    with patch("custom_components.tapo_p110.tpap_client.urllib.request.urlopen") as m:
        yield m


@pytest.fixture
def mock_client(mock_urlopen):
    """Return a TapoP110Client with all I/O mocked and a fake session established.

    The client has a pre-set session (ds_url, session_key, base_nonce, seq) so
    _send_request can encrypt/decrypt without a real handshake. Individual tests
    can still override mock_urlopen responses as needed.
    """
    from custom_components.tapo_p110.tpap_client import TapoP110Client

    client = TapoP110Client("192.168.1.99", "user@example.com", "password123")

    # Establish a fake session so _send_request can proceed without discover_and_handshake.
    # These values are deterministic and only used for nonce/encryption tests —
    # they do NOT represent a real device handshake.
    client._ds_url = "http://192.168.1.99/app/stok"
    client._session_key = b"\x01" * 16  # 128-bit AES key
    client._base_nonce = b"\x00" * 12  # 12-byte base nonce
    client._seq = 0
    client._session_expiry = 9999999999.0  # far in the future

    yield client


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/."""
    path = FIXTURES_DIR / name
    return json.loads(path.read_text())


@pytest.fixture
def spake2_vector():
    """Load the SPAKE2+ derivation test vector (generated deterministically)."""
    return load_fixture("spake2_vector.json")
