"""Number platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity
from .tpap_client import TapoAuthError, TapoConnectionError

_LOGGER = logging.getLogger(__name__)

NUMBERS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="auto_off_minutes",
        name="Auto-Off Delay",
        native_min_value=1,
        native_max_value=120,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:timer-settings-outline",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tapo P110 number entities."""
    coordinator: TapoP110DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TapoP110Number(coordinator, desc) for desc in NUMBERS]
    async_add_entities(entities)


class TapoP110Number(TapoP110Entity, NumberEntity):
    """Number entity for Tapo P110."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data:
            return None
        key = self.entity_description.key
        if key == "auto_off_minutes":
            return data.get("auto_off_config", {}).get("delay_min")
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_auto_off_minutes, int(value)
            )
            await self.coordinator.async_request_refresh()
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Set auto-off minutes failed: %s", exc)