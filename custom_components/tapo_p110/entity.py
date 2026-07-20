"""Entity base for Tapo P110."""

from __future__ import annotations

import base64

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoP110DataCoordinator


class TapoP110Entity(CoordinatorEntity[TapoP110DataCoordinator]):
    """Base entity for Tapo P110.

    Device identity is anchored to the subentry_id (a stable ULID assigned at
    subentry creation, known at setup time regardless of device state), NOT to
    the device's ``device_id``. The ``device_id`` is only known after a
    successful poll and is absent when the plug is offline at setup — using it
    as the registry key would collapse every offline device onto the hub's
    device row and produce duplicate rows when the plug later comes online.

    Descriptive device fields (name, model, sw_version, hw_version) are read
    from ``coordinator.data`` at entity-construction time and baked into
    ``_attr_device_info``. When the plug is offline at setup they fall back to
    host-based placeholders; the coordinator re-syncs the device-registry row
    from live data after each successful poll so the row updates in place when
    the plug comes online (no duplicate row, no orphan).
    """

    def __init__(self, coordinator: TapoP110DataCoordinator, subentry_id: str) -> None:
        super().__init__(coordinator)
        self._subentry_id = subentry_id
        self._attr_device_info = build_device_info(coordinator, subentry_id)


def build_device_info(coordinator: TapoP110DataCoordinator, subentry_id: str) -> DeviceInfo:
    """Build DeviceInfo from current coordinator data (placeholders when offline)."""
    info = coordinator.data.get("device_info", {}) if coordinator.data else {}

    # Decode nickname from base64 (fallback to raw on error).
    raw_nickname = info.get("nickname", "")
    if raw_nickname:
        try:
            name: str | None = base64.b64decode(raw_nickname).decode()
        except Exception:
            name = raw_nickname
    else:
        name = f"Tapo P110 ({coordinator.host})"

    return DeviceInfo(
        identifiers={(DOMAIN, subentry_id)},
        name=name,
        manufacturer="TP-Link",
        model=f"P110 ({specs})" if (specs := info.get("specs")) else "P110",
        sw_version=info.get("fw_ver") or None,
        hw_version=info.get("hw_ver") or None,
    )
