"""Binary sensor platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapoP110HubEntry
from .const import SUBENTRY_TYPE_DEVICE
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity

_LOGGER = logging.getLogger(__name__)

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="overheated",
        name="Overheat",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
    ),
    BinarySensorEntityDescription(
        key="overloaded",
        name="Power Overload",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:flash-alert",
    ),
    BinarySensorEntityDescription(
        key="overcurrent",
        name="Overcurrent",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:current-ac",
    ),
    BinarySensorEntityDescription(
        key="charging_protection",
        name="Charging Protection",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:battery-alert",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapoP110HubEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tapo P110 binary sensors, one set per device subentry."""
    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        coordinator = coordinators[subentry.subentry_id]
        entities = [
            TapoP110BinarySensor(coordinator, desc, subentry.subentry_id)
            for desc in BINARY_SENSORS
        ]
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class TapoP110BinarySensor(TapoP110Entity, BinarySensorEntity):
    """Binary sensor for Tapo P110 protection statuses."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: BinarySensorEntityDescription,
        subentry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{subentry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        info = data.get("device_info", {})
        key = self.entity_description.key
        # Protection statuses: "normal" = off, anything else = on (problem)
        if key == "overheated":
            status = info.get("overheat_status")
        elif key == "overloaded":
            status = info.get("power_protection_status")
        elif key == "overcurrent":
            status = info.get("overcurrent_status")
        elif key == "charging_protection":
            status = info.get("charging_status")
        else:
            return None
        if status is None:
            return None
        return status != "normal"

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None