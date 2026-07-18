"""Tapo P110 custom integration for Home Assistant.

Hub model: one config entry per TP-Link account (holds username+password),
with one device subentry per plug (holds host). Each device subentry has its
own TapoP110DataCoordinator (one SPAKE2+ session per plug). Coordinators are
stored on the hub entry's ``runtime_data`` keyed by ``subentry_id``.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN, SUBENTRY_TYPE_DEVICE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]

type TapoP110HubEntry = ConfigEntry[dict[str, Any]]


async def async_setup_entry(hass: HomeAssistant, entry: TapoP110HubEntry) -> bool:
    """Set up a Tapo P110 hub from a config entry.

    Builds one coordinator per device subentry.
    """
    from .coordinator import TapoP110DataCoordinator

    coordinators: dict[str, TapoP110DataCoordinator] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        host = subentry.data[CONF_HOST]
        coordinator = TapoP110DataCoordinator(
            hass,
            entry,
            host,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
        coordinators[subentry.subentry_id] = coordinator
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as exc:  # noqa: BLE001 - keep hub setup alive per device
            _LOGGER.warning(
                "Initial refresh failed for %s; device will start unavailable: %s",
                host,
                exc,
            )

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload the hub when a subentry is added/removed/updated (e.g. "Add Device"
    # via the UI) so the new subentry's coordinator + entities are created.
    entry.async_on_unload(entry.add_update_listener(_async_reload_listener))
    return True


async def _async_reload_listener(hass: HomeAssistant, entry: TapoP110HubEntry) -> None:
    """Reload the hub entry when its subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TapoP110HubEntry) -> bool:
    """Unload a config entry (hub) — shuts down every device coordinator."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        for coordinator in (entry.runtime_data or {}).values():
            await coordinator.async_shutdown()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries.

    v1 stored one entry per plug (host+username+password at top level, no
    subentries). v2 is the hub+subentry model. The chosen migration path is a
    clean start: all v1 entries are removed so the user can set up a fresh hub
    and re-add the plugs as device subentries.
    """
    if entry.version < 2:
        # Remove every v1 entry (one-per-plug). Guard against races: the entry
        # may already be gone by the time the scheduled task runs (HA loads
        # entries concurrently, so multiple v1 entries schedule overlapping
        # removals for the same set).
        for e in hass.config_entries.async_entries(DOMAIN):
            if e.version < 2 and hass.config_entries.async_get_entry(e.entry_id) is not None:
                hass.async_create_task(
                    _safe_remove_entry(hass, e.entry_id)
                )
        return True
    return True


async def _safe_remove_entry(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a config entry, ignoring UnknownEntry if already gone."""
    if hass.config_entries.async_get_entry(entry_id) is None:
        return
    try:
        await hass.config_entries.async_remove(entry_id)
    except Exception:  # noqa: BLE001 — best-effort cleanup during migration
        _LOGGER.debug("Entry %s already removed during migration", entry_id)