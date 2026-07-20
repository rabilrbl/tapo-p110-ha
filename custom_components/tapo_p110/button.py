"""Button platform for Tapo P110."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapoP110HubEntry
from .const import SUBENTRY_TYPE_DEVICE
from .coordinator import TapoP110DataCoordinator
from .entity import TapoP110Entity
from .tpap_client import TapoAuthError, TapoConnectionError

_LOGGER = logging.getLogger(__name__)

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="reload_device",
        name="Reload Device",
        icon="mdi:restart-alert",
        entity_category=EntityCategory.CONFIG,
    ),
)


def _build_entities(coordinator: TapoP110DataCoordinator, subentry_id: str) -> list:
    """Build the button entities for one device subentry."""
    return [TapoP110ReloadButton(coordinator, BUTTONS[0], subentry_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapoP110HubEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tapo P110 buttons, one set per device subentry (initial setup)."""
    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        if subentry.subentry_id not in coordinators:
            continue
        async_add_entities(
            _build_entities(coordinators[subentry.subentry_id], subentry.subentry_id),
            config_subentry_id=subentry.subentry_id,
        )


async def async_setup_subentry(
    hass: HomeAssistant,
    entry: TapoP110HubEntry,
    subentry_id: str,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tapo P110 buttons for a single device subentry (post-setup add)."""
    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data
    if subentry_id not in coordinators:
        return
    async_add_entities(
        _build_entities(coordinators[subentry_id], subentry_id),
        config_subentry_id=subentry_id,
    )


class TapoP110ReloadButton(TapoP110Entity, ButtonEntity):
    """Reload a single Tapo P110 device (re-handshake + re-poll).

    Drops the plug's SPAKE2+ session and forces an immediate refresh, which
    re-runs ``_async_update_data`` -> ``get_all_data`` -> ``discover_and_handshake``.
    Scoped to the one plug: each entity holds its own ``coordinator.client``.
    Does NOT touch sibling coordinators or entities.
    """

    def __init__(
        self,
        coordinator: TapoP110DataCoordinator,
        description: ButtonEntityDescription,
        subentry_id: str,
    ) -> None:
        super().__init__(coordinator, subentry_id)
        self.entity_description = description
        self._attr_unique_id = f"{subentry_id}_{description.key}"

    async def async_press(self, **kwargs: Any) -> None:
        """Handle button press: drop session + immediate re-poll."""
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.shutdown)
            await self.coordinator.async_request_refresh()
        except (TapoAuthError, TapoConnectionError) as exc:
            _LOGGER.error("Reload device failed: %s", exc)
