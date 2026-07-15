"""Select platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
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

SELECTS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="led_rule",
        name="LED Mode",
        options=["Always On", "Auto", "Off"],
        icon="mdi:led-on",
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="default_states",
        name="Default State",
        options=["last_states", "on", "off"],
        icon="mdi:power-settings",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tapo P110 selects."""
    coordinator: TapoP110DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TapoP110Select(coordinator, desc) for desc in SELECTS]
    async_add_entities(entities)


class TapoP110Select(TapoP110Entity, SelectEntity):
    """Select entity for Tapo P110 LED mode."""

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data
        if not data:
            return None
        key = self.entity_description.key
        if key == "led_rule":
            rule = data.get("led_info", {}).get("led_rule")
            return {"always": "Always On", "auto": "Auto", "never": "Off"}.get(rule)
        if key == "default_states":
            ds = data.get("device_info", {}).get("default_states", {})
            dtype = ds.get("type")
            if dtype == "last_states":
                return "last_states"
            elif dtype == "custom":
                state = ds.get("state", {})
                if state.get("on") is True:
                    return "on"
                elif state.get("on") is False:
                    return "off"
            return None
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the selected option."""
        key = self.entity_description.key
        try:
            if key == "led_rule":
                option_map = {"Always On": "always", "Auto": "auto", "Off": "never"}
                await self.hass.async_add_executor_job(
                    self.coordinator.client.set_led_rule, option_map[option]
                )
            elif key == "default_states":
                await self.hass.async_add_executor_job(
                    self.coordinator.client.set_default_state, option
                )
            await self.coordinator.async_request_refresh()
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Set option failed: %s", exc)