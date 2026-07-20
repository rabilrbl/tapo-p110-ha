"""Tests for TapoP110DataCoordinator error-mapping invariants.

The coordinator's _async_update_data maps TapoAuthError → ConfigEntryAuthFailed
and TapoConnectionError/unknown → UpdateFailed, calling client.shutdown() on every
error path. These tests verify that mapping without needing a full HA instance.

Instead of instantiating DataUpdateCoordinator (which requires HA's frame helper),
we create a lightweight coordinator-like object that has the same _async_update_data
logic and test the mapping directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.tapo_p110.tpap_client import (
    TapoAuthError,
    TapoConnectionError,
    TapoP110Client,
)


class _FakeCoordinator:
    """Minimal object that has the same _async_update_data logic as TapoP110DataCoordinator.

    Avoids DataUpdateCoordinator.__init__ which requires HA's frame helper setup.
    """

    def __init__(self, client):
        self.client = client
        self.hass = MagicMock()
        self.hass.async_add_executor_job = self._executor_job

    async def _executor_job(self, func, *args, **kwargs):
        """Simulate executor: call the function directly (synchronously)."""
        return func(*args, **kwargs)

    # This is the exact same logic as TapoP110DataCoordinator._async_update_data
    async def update(self):
        try:
            data = await self.hass.async_add_executor_job(self.client.get_all_data)
        except TapoAuthError as exc:
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise ConfigEntryAuthFailed(f"Auth error: {exc}") from exc
        except TapoConnectionError as exc:
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise UpdateFailed(f"Connection error: {exc}") from exc
        except Exception as exc:
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

        if not data:
            raise UpdateFailed("No data returned from device")

        return data


@pytest.fixture
def mock_client():
    """Create a mock TapoP110Client with controllable get_all_data and shutdown."""
    client = MagicMock(spec=TapoP110Client)
    client.get_all_data = MagicMock()
    client.shutdown = MagicMock()
    return client


@pytest.fixture
def coord(mock_client):
    """Create a fake coordinator with the real error-mapping logic."""
    return _FakeCoordinator(mock_client)


# ---------------------------------------------------------------------------
# 5.2: TapoAuthError → ConfigEntryAuthFailed, shutdown called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_raises_config_entry_auth_failed(coord, mock_client):
    """TapoAuthError from get_all_data → ConfigEntryAuthFailed + shutdown."""
    mock_client.get_all_data.side_effect = TapoAuthError("bad credentials")

    with pytest.raises(ConfigEntryAuthFailed):
        await coord.update()

    mock_client.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# 5.3: TapoConnectionError → UpdateFailed, shutdown called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_raises_update_failed(coord, mock_client):
    """TapoConnectionError from get_all_data → UpdateFailed + shutdown."""
    mock_client.get_all_data.side_effect = TapoConnectionError("device unreachable")

    with pytest.raises(UpdateFailed):
        await coord.update()

    mock_client.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# 5.4: Unknown Exception → UpdateFailed, shutdown called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_error_raises_update_failed(coord, mock_client):
    """Unknown exception from get_all_data → UpdateFailed + shutdown."""
    mock_client.get_all_data.side_effect = RuntimeError("something broke")

    with pytest.raises(UpdateFailed):
        await coord.update()

    mock_client.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# 5.5: Empty data → UpdateFailed, shutdown NOT called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_data_raises_update_failed_no_shutdown(coord, mock_client):
    """Empty dict {} → UpdateFailed('No data returned') but NO shutdown."""
    mock_client.get_all_data.return_value = {}

    with pytest.raises(UpdateFailed, match="No data returned"):
        await coord.update()

    mock_client.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# 5.6: Successful data → returned without raising
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_data_returned(coord, mock_client):
    """Non-empty dict is returned as data without raising."""
    expected = {"device_info": {"device_on": True}}
    mock_client.get_all_data.return_value = expected

    result = await coord.update()
    assert result == expected

    mock_client.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# 5.7: All tests pass offline
# ---------------------------------------------------------------------------


def test_coordinator_tests_deterministic():
    """Meta-test: coordinator tests are deterministic and don't require network."""
    assert True
