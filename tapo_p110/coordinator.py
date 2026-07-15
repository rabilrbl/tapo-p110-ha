"""Data coordinator for Tapo P110."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN
from .tpap_client import TapoAuthError, TapoConnectionError, TapoP110Client

_LOGGER = logging.getLogger(__name__)


class TapoP110DataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Tapo P110 data polling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.client = TapoP110Client(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
        self._entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            data = await self.hass.async_add_executor_job(
                self.client.get_all_data
            )
        except TapoAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except TapoConnectionError as exc:
            raise UpdateFailed(f"Connection error: {exc}") from exc
        except Exception as exc:
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

        if not data:
            raise UpdateFailed("No data returned from device")

        return data

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        await self.hass.async_add_executor_job(self.client.shutdown)