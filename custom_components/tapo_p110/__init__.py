"""Tapo P110 custom integration for Home Assistant.

Hub model: one config entry per TP-Link account (holds username+password),
with one device subentry per plug (holds host). Each device subentry has its
own TapoP110DataCoordinator (one SPAKE2+ session per plug). Coordinators are
stored on the hub entry's ``runtime_data`` keyed by ``subentry_id``.

Per-device resilience: an offline device's failed first-refresh does NOT abort
hub setup — that coordinator stays in ``runtime_data`` with
``last_update_success=False`` and HA's 15s update_coordinator loop retries it
independently. Adding/removing/reconfiguring a single device subentry only
sets up or tears down that one subentry's coordinator + entities (no sibling
reload) via ``_async_subentry_listener``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback, EntityPlatform

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

    Builds one coordinator per device subentry. A single device's
    first-refresh failure does NOT abort hub setup: the coordinator is kept
    in ``runtime_data`` (``last_update_success=False``) and retried by HA's
    normal 15s update loop. Online devices get entities immediately.
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
            subentry.subentry_id,
        )
        coordinators[subentry.subentry_id] = coordinator
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as exc:
            _LOGGER.warning(
                "Device %s (%s) not ready, will retry: %s",
                subentry.title,
                subentry.subentry_id,
                exc,
            )

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_subentry_listener))
    return True


async def _async_subentry_listener(hass: HomeAssistant, entry: TapoP110HubEntry) -> None:
    """Reconcile device subentries with live coordinators (add/remove/reconfigure).

    Fired by ``async_add_subentry``/``async_remove_subentry``/``async_update_subentry``
    (all fire ``update_listeners``). Diffs ``entry.subentries`` against
    ``entry.runtime_data`` and sets up / tears down only the affected
    subentry's coordinator + entities — siblings are never touched.
    """
    from .coordinator import TapoP110DataCoordinator

    coordinators: dict[str, TapoP110DataCoordinator] = entry.runtime_data

    # Add coordinators for new device subentries; rebuild on host change.
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_DEVICE:
            continue
        sid = subentry.subentry_id
        host = subentry.data[CONF_HOST]
        existing = coordinators.get(sid)
        if existing is not None and existing.host == host:
            continue  # unchanged
        if existing is not None:
            # Host changed (reconfigure) — tear down + rebuild this subentry only.
            await _async_unload_subentry(hass, entry, sid)
            await coordinators.pop(sid).async_shutdown()
        coordinator = TapoP110DataCoordinator(
            hass,
            entry,
            host,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            sid,
        )
        coordinators[sid] = coordinator
        try:
            await coordinator.async_refresh()
        except Exception as exc:
            _LOGGER.warning(
                "Device %s (%s) not ready, will retry: %s",
                subentry.title,
                sid,
                exc,
            )
        await _async_forward_subentry_setup(hass, entry, sid)

    # Remove coordinators for deleted device subentries.
    live_ids = {s.subentry_id for s in entry.subentries.values() if s.subentry_type == SUBENTRY_TYPE_DEVICE}
    for sid in list(coordinators):
        if sid in live_ids:
            continue
        await _async_unload_subentry(hass, entry, sid)
        await coordinators.pop(sid).async_shutdown()


def _make_add_entities(hass: HomeAssistant, platform: EntityPlatform) -> AddConfigEntryEntitiesCallback:
    """Build a sync ``AddConfigEntryEntitiesCallback`` shim for ``platform``.

    ``EntityPlatform.async_add_entities`` is a coroutine; the platform handlers
    call it synchronously (per the ``AddEntitiesCallback`` contract), so this
    wraps it in a sync callable that schedules the coro. Capturing ``platform``
    as a factory argument binds it by value (avoids B023 late-binding).
    """

    def _add_entities(
        new_entities: Iterable[Entity],
        update_before_add: bool = False,
        *,
        config_subentry_id: str | None = None,
    ) -> None:
        hass.async_create_task(
            platform.async_add_entities(new_entities, update_before_add, config_subentry_id=config_subentry_id)
        )

    return _add_entities


async def _async_forward_subentry_setup(hass: HomeAssistant, entry: TapoP110HubEntry, subentry_id: str) -> None:
    """Forward platform setup for a single device subentry's entities.

    Called from ``_async_subentry_listener`` for a newly-added or reconfigured
    subentry (the hub is already ``LOADED`` at that point, so the normal
    ``async_setup_entry`` iterate-all path does not run for it). Maps each live
    ``EntityPlatform`` to its module's ``async_setup_subentry`` handler by
    ``platform.domain`` (sensor/switch/...), not ``platform.platform_name``
    (the integration domain, ``tapo_p110``).
    """
    from homeassistant.helpers.entity_platform import async_get_platforms

    from . import binary_sensor, button, number, select, sensor, switch

    platforms = async_get_platforms(hass, DOMAIN)
    handlers = {
        "sensor": sensor.async_setup_subentry,
        "switch": switch.async_setup_subentry,
        "binary_sensor": binary_sensor.async_setup_subentry,
        "button": button.async_setup_subentry,
        "number": number.async_setup_subentry,
        "select": select.async_setup_subentry,
    }
    for platform in platforms:
        handler = handlers.get(platform.domain)
        if handler is None:
            continue

        # EntityPlatform.async_add_entities is a coroutine; the platform
        # handlers call it synchronously (per the AddEntitiesCallback
        # contract), so wrap it in a sync shim that schedules the coro.
        # Use a factory to bind `platform` by value (avoids B023 late-binding
        # and keeps the callback signature matching AddConfigEntryEntitiesCallback).
        await handler(hass, entry, subentry_id, _make_add_entities(hass, platform))


async def _async_unload_subentry(hass: HomeAssistant, entry: TapoP110HubEntry, subentry_id: str) -> None:
    """Remove a device subentry's entities + device-registry entry.

    Clears every entity and device tagged with ``config_subentry_id`` from the
    registries; HA removes the entities from their ``EntityPlatform`` via the
    registry. No per-platform unload code needed.
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    er.async_get(hass).async_clear_config_subentry(entry.entry_id, subentry_id)
    dr.async_get(hass).async_clear_config_subentry(entry.entry_id, subentry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TapoP110HubEntry) -> bool:
    """Unload a config entry (hub) — shuts down every device coordinator."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        for coordinator in (entry.runtime_data or {}).values():
            await coordinator.async_shutdown()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries.

    v1 stored one entry per plug (host+username+password at top level, no
    subentries). v2 is the hub+subentry model. The chosen v1->v2 migration
    path is a clean start: all v1 entries are removed so the user can set up a
    fresh hub and re-add the plugs as device subentries.

    The v2 -> v2.1 entity-identifier change (``device_id`` -> ``subentry_id``)
    is NOT migrated: existing device-registry rows keyed by ``device_id``
    become orphans after upgrade. Users delete them once via the UI; the new
    ``subentry_id``-keyed rows are created automatically by the entities. This
    trades a one-time manual cleanup for not carrying re-key logic that HA's
    migration plumbing makes brittle.
    """
    if entry.version < 2:
        # Remove every v1 entry (one-per-plug). Guard against races: the entry
        # may already be gone by the time the scheduled task runs (HA loads
        # entries concurrently, so multiple v1 entries schedule overlapping
        # removals for the same set).
        for e in hass.config_entries.async_entries(DOMAIN):
            if e.version < 2 and hass.config_entries.async_get_entry(e.entry_id) is not None:
                hass.async_create_task(_safe_remove_entry(hass, e.entry_id))
        return True
    return True


async def _safe_remove_entry(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a config entry, ignoring UnknownEntry if already gone."""
    if hass.config_entries.async_get_entry(entry_id) is None:
        return
    try:
        await hass.config_entries.async_remove(entry_id)
    except Exception:
        _LOGGER.debug("Entry %s already removed during migration", entry_id)
