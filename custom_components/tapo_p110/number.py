"""Number platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapoP110HubEntry
from .const import SUBENTRY_TYPE_DEVICE
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity
from .tpap_client import TapoAuthError, TapoConnectionError

_LOGGER = logging.getLogger(__name__)

NUMBERS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="auto_off_minutes",
        name="Auto-Off After",
        native_min_value=0,
        native_max_value=1439,
        native_step=1,
        mode=NumberMode.BOX,
        native_unit_of_measurement="min",
        icon="mdi:timer-settings-outline",
    ),
    NumberEntityDescription(
        key="power_protection_threshold",
        name="Power Protection Threshold",
        native_min_value=1,
        native_max_value=3580,
        native_step=1,
        mode=NumberMode.BOX,
        native_unit_of_measurement="W",
        icon="mdi:flash-alert",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapoP110HubEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tapo P110 number entities, one set per device subentry."""
    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        coordinator = coordinators.get(subentry.subentry_id)
        if coordinator is None:
            continue
        entities = [
            TapoP110Number(coordinator, desc, subentry.subentry_id)
            for desc in NUMBERS
        ]
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class TapoP110Number(TapoP110Entity, NumberEntity):
    """Number entity for Tapo P110."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: NumberEntityDescription,
        subentry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{subentry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data:
            return None
        key = self.entity_description.key
        if key == "auto_off_minutes":
            return data.get("auto_off_config", {}).get("delay_min")
        if key == "power_protection_threshold":
            pp = data.get("protection_power", {})
            if pp.get("enabled"):
                return pp.get("protection_power", 0)
            return 0
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        key = self.entity_description.key
        try:
            if key == "auto_off_minutes":
                await self.hass.async_add_executor_job(
                    self.coordinator.client.set_auto_off_minutes, int(value)
                )
            elif key == "power_protection_threshold":
                await self.hass.async_add_executor_job(
                    self.coordinator.client.set_power_protection_threshold, int(value)
                )
            await self.coordinator.async_request_refresh()
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Set value failed: %s", exc)