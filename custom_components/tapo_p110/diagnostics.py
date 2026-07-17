"""Diagnostics support for Tapo P110 (hub + device subentries)."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, SUBENTRY_TYPE_DEVICE

_REDACT_KEYS = {
    "device_id",
    "mac",
    "hw_id",
    "fw_id",
    "oem_id",
    "ssid",
    "owner",
    "ip",
}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if k in _REDACT_KEYS else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i) for i in obj]
    return obj


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a hub config entry and all its device subentries."""
    coordinators: dict = entry.runtime_data or {}
    devices: list[dict[str, Any]] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        coordinator = coordinators.get(subentry.subentry_id)
        data = coordinator.data if coordinator and coordinator.data else {}
        devices.append(
            {
                "host": subentry.data.get(CONF_HOST),
                "device_info": _redact(data.get("device_info", {})),
                "energy_usage": data.get("energy_usage", {}),
                "emeter_data": data.get("emeter_data", {}),
                "device_usage": data.get("device_usage", {}),
                "device_time": data.get("device_time", {}),
                "led_info": data.get("led_info", {}),
                "auto_update_info": data.get("auto_update_info", {}),
                "auto_off_config": data.get("auto_off_config", {}),
                "protection_power": data.get("protection_power", {}),
                "max_power": data.get("max_power", {}),
            }
        )
    return {
        "hub": {"username": "***REDACTED***"},
        "devices": devices,
    }