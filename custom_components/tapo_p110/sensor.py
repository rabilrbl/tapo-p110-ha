"""Sensor platform for Tapo P110."""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapoP110HubEntry
from .const import SUBENTRY_TYPE_DEVICE
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity

_LOGGER = logging.getLogger(__name__)


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string.
    
    Scales up: seconds → minutes → hours → days → months → years.
    Only shows non-zero leading units, trailing units are zero-padded.
    Example: 3661s → "1h 1m 1s", 90061s → "1d 1h 1m 1s"
    """
    if seconds < 0:
        seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    # Approximate months and years from days
    mo, d = divmod(d, 30)
    y, mo = divmod(mo, 12)
    
    parts = []
    if y:
        parts.append(f"{y}y")
    if mo or parts:
        parts.append(f"{mo}mo")
    if d or parts:
        parts.append(f"{d}d")
    if h or parts:
        parts.append(f"{h}h")
    if m or parts:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    
    # Show at most 3 most significant non-zero units
    # But always show down to seconds if total < 1 minute
    result = parts[0] if parts else "0s"
    for p in parts[1:3]:
        result += f" {p}"
    return result

SENSORS: tuple[SensorEntityDescription, ...] = (
    # Power & Energy
    SensorEntityDescription(
        key="current_power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:flash",
    ),
    SensorEntityDescription(
        key="today_energy",
        name="Today Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
    ),
    SensorEntityDescription(
        key="month_energy",
        name="Month Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar-month",
    ),
    SensorEntityDescription(
        key="total_energy",
        name="Total Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:summit",
    ),
    # Runtime
    SensorEntityDescription(
        key="today_runtime",
        name="Today Runtime",
        icon="mdi:timer-sand",
    ),
    SensorEntityDescription(
        key="month_runtime",
        name="Month Runtime",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="on_time",
        name="On Time",
        icon="mdi:timer-outline",
    ),
    # Electrical
    SensorEntityDescription(
        key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    SensorEntityDescription(
        key="current",
        name="Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    # WiFi (diagnostic)
    SensorEntityDescription(
        key="rssi",
        name="WiFi Signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="signal_level",
        name="WiFi Signal Level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi-strength-3",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="ssid",
        name="WiFi SSID",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Timestamps (diagnostic)
    SensorEntityDescription(
        key="on_since",
        name="On Since",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Device info (diagnostic)
    SensorEntityDescription(
        key="device_id",
        name="Device ID",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapoP110HubEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tapo P110 sensors, one set per device subentry."""
    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        coordinator = coordinators.get(subentry.subentry_id)
        if coordinator is None:
            continue
        entities = [
            TapoP110Sensor(coordinator, desc, subentry.subentry_id)
            for desc in SENSORS
        ]
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class TapoP110Sensor(TapoP110Entity, SensorEntity):
    """Sensor for Tapo P110 metrics."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: SensorEntityDescription,
        subentry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{subentry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not data:
            return None

        key = self.entity_description.key

        # Current power: mW → W
        if key == "current_power":
            eu = data.get("energy_usage", {})
            em = data.get("emeter_data", {})
            mw = eu.get("current_power") or em.get("power_mw")
            if mw is not None:
                return round(mw / 1000, 2)
            return None

        # Energy: Wh → kWh
        if key == "today_energy":
            wh = data.get("energy_usage", {}).get("today_energy")
            if wh is not None:
                return round(wh / 1000, 3)
            return None
        if key == "month_energy":
            wh = data.get("energy_usage", {}).get("month_energy")
            if wh is not None:
                return round(wh / 1000, 3)
            return None
        if key == "total_energy":
            wh = data.get("emeter_data", {}).get("energy_wh")
            if wh is not None:
                return round(wh / 1000, 3)
            return None

        # Runtime and on_time → human-readable duration
        if key in ("today_runtime", "month_runtime"):
            minutes = data.get("energy_usage", {}).get(key)
            if minutes is not None:
                return _format_duration(minutes * 60)
            return None
        if key == "on_time":
            seconds = data.get("device_info", {}).get("on_time")
            if seconds is not None:
                return _format_duration(seconds)
            return None

        # Electrical (emeter_data)
        if key == "voltage":
            mv = data.get("emeter_data", {}).get("voltage_mv")
            if mv is not None:
                return round(mv / 1000, 1)
            return None
        if key == "current":
            ma = data.get("emeter_data", {}).get("current_ma")
            if ma is not None:
                return round(ma / 1000, 3)
            return None

        # WiFi
        if key == "rssi":
            return data.get("device_info", {}).get("rssi")
        if key == "signal_level":
            return data.get("device_info", {}).get("signal_level")
        if key == "ssid":
            raw = data.get("device_info", {}).get("ssid")
            if raw:
                try:
                    return base64.b64decode(raw).decode()
                except Exception:
                    return raw
            return None

        # Timestamp: on_since = device_time - on_time
        if key == "on_since":
            info = data.get("device_info", {})
            dt = data.get("device_time", {})
            on_time = info.get("on_time")
            timestamp = dt.get("timestamp")
            if on_time is not None and timestamp is not None and info.get("device_on"):
                return datetime.fromtimestamp(timestamp - on_time, tz=timezone.utc)
            return None

        # Device ID
        if key == "device_id":
            return data.get("device_info", {}).get("device_id")

        return None

    @property
    def available(self) -> bool:
        if self.coordinator.data is None:
            return False
        if self.entity_description.key == "device_id":
            return self.coordinator.data.get("device_info") is not None
        return self.native_value is not None