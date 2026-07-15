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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity

_LOGGER = logging.getLogger(__name__)

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
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
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
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tapo P110 sensors."""
    coordinator: TapoP110DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TapoP110Sensor(coordinator, desc) for desc in SENSORS]
    async_add_entities(entities)


class TapoP110Sensor(TapoP110Entity, SensorEntity):
    """Sensor for Tapo P110 metrics."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

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

        # Runtime (minutes → "Xh Ym Zs" format)
        if key in ("today_runtime", "month_runtime"):
            minutes = data.get("energy_usage", {}).get(key)
            if minutes is not None:
                h = minutes // 60
                m = minutes % 60
                return f"{h}h {m}m"
            return None
        if key == "on_time":
            return data.get("device_info", {}).get("on_time")

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