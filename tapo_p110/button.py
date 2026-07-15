"""Button platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
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

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tapo P110 buttons."""
    coordinator: TapoP110DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TapoP110Button(coordinator, desc) for desc in BUTTONS]
    async_add_entities(entities)


class TapoP110Button(TapoP110Entity, ButtonEntity):
    """Button for Tapo P110."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    async def async_press(self, **kwargs: Any) -> None:
        """Handle button press."""
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.reboot)
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Reboot failed: %s", exc)