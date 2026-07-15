"""Switch platform for Tapo P110."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
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

SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="power",
        name="Plug Power",
        device_class=SwitchDeviceClass.OUTLET,
        icon="mdi:power-plug",
    ),
    SwitchEntityDescription(
        key="auto_off_enabled",
        name="Auto-Off Timer",
        icon="mdi:timer-cancel-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="auto_update_enabled",
        name="Auto Firmware Update",
        icon="mdi:cloud-sync-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="power_protection_enabled",
        name="Power Protection",
        icon="mdi:flash-alert",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tapo P110 switches."""
    coordinator: TapoP110DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        TapoP110PowerSwitch(coordinator, SWITCHES[0]),
        TapoP110AutoOffSwitch(coordinator, SWITCHES[1]),
        TapoP110AutoUpdateSwitch(coordinator, SWITCHES[2]),
        TapoP110PowerProtectionSwitch(coordinator, SWITCHES[3]),
    ]
    async_add_entities(entities)


class TapoP110BaseSwitch(TapoP110Entity, SwitchEntity):
    """Base switch for Tapo P110."""

    def __init__(self, coordinator: TapoP110DataCoordinator, description: SwitchEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    async def _async_turn(self, on: bool, setter) -> None:
        try:
            await self.hass.async_add_executor_job(setter, on)
            await self.coordinator.async_request_refresh()
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Switch command failed: %s", exc)


class TapoP110PowerSwitch(TapoP110BaseSwitch):
    """Switch for the plug power state."""

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data.get("device_info", {}) if self.coordinator.data else {}
        return data.get("device_on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_turn(True, self.coordinator.client.set_device_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_turn(False, self.coordinator.client.set_device_on)

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and bool(
            self.coordinator.data.get("device_info")
        )


class TapoP110AutoOffSwitch(TapoP110BaseSwitch):
    """Switch for the auto-off timer."""

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data.get("auto_off_config", {}) if self.coordinator.data else {}
        return data.get("enable")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_turn(True, self.coordinator.client.set_auto_off_enabled)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_turn(False, self.coordinator.client.set_auto_off_enabled)


class TapoP110AutoUpdateSwitch(TapoP110BaseSwitch):
    """Switch for auto firmware updates."""

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data.get("auto_update_info", {}) if self.coordinator.data else {}
        return data.get("enable")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_turn(True, self.coordinator.client.set_auto_update)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_turn(False, self.coordinator.client.set_auto_update)


class TapoP110PowerProtectionSwitch(TapoP110BaseSwitch):
    """Switch for power protection."""

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data.get("protection_power", {}) if self.coordinator.data else {}
        return data.get("enabled")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_turn(True, self.coordinator.client.set_power_protection_enabled)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_turn(False, self.coordinator.client.set_power_protection_enabled)