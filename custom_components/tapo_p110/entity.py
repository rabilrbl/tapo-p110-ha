"""Entity base for Tapo P110."""
from __future__ import annotations

import base64

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoP110DataCoordinator


class TapoP110Entity(CoordinatorEntity[TapoP110DataCoordinator]):
    """Base entity for Tapo P110."""

    def __init__(self, coordinator: TapoP110DataCoordinator) -> None:
        super().__init__(coordinator)
        info = coordinator.data.get("device_info", {}) if coordinator.data else {}

        # Decode nickname from base64
        nickname = ""
        raw_nickname = info.get("nickname", "")
        if raw_nickname:
            try:
                nickname = base64.b64decode(raw_nickname).decode()
            except Exception:
                nickname = raw_nickname

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.get("device_id", coordinator.config_entry.entry_id))},
            name=nickname or f"Tapo P110 ({coordinator.host})",
            manufacturer="TP-Link",
            model=f"P110 ({info.get('specs', '')})",
            sw_version=info.get("fw_ver", ""),
            hw_version=info.get("hw_ver", ""),
        )