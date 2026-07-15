"""Diagnostics support for Tapo P110."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}

    # Redact sensitive fields
    def _redact(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if k in (
                    "device_id", "mac", "hw_id", "fw_id", "oem_id",
                    "ssid", "owner", "ip",
                ) else _redact(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_redact(i) for i in obj]
        return obj

    return {
        "entry": {
            "host": entry.data.get("host"),
            "username": "***REDACTED***",
        },
        "device_info": _redact(data.get("device_info", {})),
        "energy_usage": data.get("energy_usage", {}),
        "emeter_data": data.get("emeter_data", {}),
        "device_usage": data.get("device_usage", {}),
        "device_time": data.get("device_time", {}),
        "led_info": data.get("led_info", {}),
        "auto_update_info": data.get("auto_update_info", {}),
        "auto_off_config": data.get("auto_off_config", {}),
    }