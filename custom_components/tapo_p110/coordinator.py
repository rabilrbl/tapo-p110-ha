"""Data coordinator for Tapo P110."""
from __future__ import annotations

import base64
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN
from homeassistant.helpers import device_registry as dr
from .tpap_client import TapoAuthError, TapoConnectionError, TapoP110Client

_LOGGER = logging.getLogger(__name__)


class TapoP110DataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Tapo P110 data polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        username: str,
        password: str,
        subentry_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}_{host}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.client = TapoP110Client(host, username, password)
        self._entry = entry
        self.host = host
        self.subentry_id = subentry_id

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            data = await self.hass.async_add_executor_job(
                self.client.get_all_data
            )
        except TapoAuthError as exc:
            # Auth failed — surface to HA so it starts a re-auth flow instead
            # of retrying a bad credential forever. Session is dropped so the
            # next poll does a fresh handshake once credentials are corrected.
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise ConfigEntryAuthFailed(f"Auth error: {exc}") from exc
        except TapoConnectionError as exc:
            # Device unreachable or session stale — reset for fresh handshake
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise UpdateFailed(f"Connection error: {exc}") from exc
        except Exception as exc:
            # Unknown error — reset session just in case
            await self.hass.async_add_executor_job(self.client.shutdown)
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

        if not data:
            raise UpdateFailed("No data returned from device")

        self._async_sync_device_registry(data)

        return data

    def _async_sync_device_registry(self, data: dict[str, Any]) -> None:
        """Sync device-registry metadata from the latest successful poll."""
        info = data.get("device_info", {}) or {}
        raw_nickname = info.get("nickname", "")
        if raw_nickname:
            try:
                name: str | None = base64.b64decode(raw_nickname).decode()
            except Exception:
                name = raw_nickname
        else:
            name = f"Tapo P110 ({self.host})"

        dev_reg = dr.async_get(self.hass)
        dev_reg.async_get_or_create(
            config_entry_id=self._entry.entry_id,
            config_subentry_id=self.subentry_id,
            identifiers={(DOMAIN, self.subentry_id)},
            name=name,
            manufacturer="TP-Link",
            model=f"P110 ({specs})" if (specs := info.get("specs")) else "P110",
            sw_version=info.get("fw_ver") or None,
            hw_version=info.get("hw_ver") or None,
        )
        # Purge stale device rows for this subentry left from older
        # integration versions that keyed the device row by ``device_id``
        # instead of ``subentry_id``. Both rows are tagged with the same
        # config_subentry_id; the canonical row (identifiers =
        # (DOMAIN, subentry_id)) is kept, any others are removed.
        for device in dr.async_entries_for_config_entry(dev_reg, self._entry.entry_id):
            sub_ids = device.config_entries_subentries.get(self._entry.entry_id, [])
            if self.subentry_id not in sub_ids:
                continue
            if (DOMAIN, self.subentry_id) in device.identifiers:
                continue
            dev_reg.async_remove_device(device.id)

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        await self.hass.async_add_executor_job(self.client.shutdown)