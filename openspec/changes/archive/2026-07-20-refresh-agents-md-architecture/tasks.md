## 1. Verify current code facts

- [x] 1.1 Read each platform file's `async_setup_subentry` and record the exact subentry entity unique-id format (do not guess)
- [x] 1.2 Confirm the `manifest.json` fields: version 2.2.2, `requirements: ["ecdsa"]`, zeroconf, integration_type, iot_class
- [x] 1.3 Confirm `const.py` exports: `DOMAIN`, `CONF_HOST/USERNAME/PASSWORD`, `SUBENTRY_TYPE_DEVICE`, `DEFAULT_UPDATE_INTERVAL`
- [x] 1.4 Confirm the coordinator error-mapping branches by reading `coordinator.py` `_async_update_data` end-to-end
- [x] 1.5 Confirm `async_migrate_entry` behavior (v1 removal, no v2→v2.1 re-key migration) from `__init__.py`

## 2. Rewrite Project Overview

- [x] 2.1 Replace the single-entry-per-plug description with the hub+subentry model (one config entry per TP-Link account, one device subentry per plug)
- [x] 2.2 Update the version reference to 2.2.2
- [x] 2.3 Keep the TPAP/SPAKE2+ protocol description (still accurate); keep the HACS distribution note

## 3. Rewrite Architecture & Data Flow

- [x] 3.1 Replace the data-flow ASCII diagram: hub entry → N device subentries → N `TapoP110DataCoordinator` instances on `runtime_data` keyed by `subentry_id`
- [x] 3.2 Document `async_setup_entry`: builds one coordinator per device subentry, `async_config_entry_first_refresh` per coordinator, failed first-refresh does NOT abort hub setup (coordinator kept, retried by 15s loop), stores on `entry.runtime_data`, forwards platform setups, registers `_async_subentry_listener`
- [x] 3.3 Document `_async_subentry_listener`: diffs `entry.subentries` vs `runtime_data`, adds new subentry coordinators, rebuilds on host change, removes deleted subentry coordinators; siblings never touched
- [x] 3.4 Document `_async_forward_subentry_setup`: maps each live `EntityPlatform` to its module's `async_setup_subentry` by `platform.domain`; uses a sync `_add_entities` shim wrapping `async_create_task`
- [x] 3.5 Document `_async_unload_subentry`: clears entity + device registries via `async_clear_config_subentry`; no per-platform unload code
- [x] 3.6 Document `async_unload_entry`: unloads platforms, shuts down every coordinator in `runtime_data`

## 4. Rewrite Coordinator section

- [x] 4.1 Document `TapoP110DataCoordinator(DataUpdateCoordinator[dict])`, 15s `update_interval`, `hass.async_add_executor_job(client.get_all_data)`
- [x] 4.2 Document the error-mapping contract: `TapoAuthError`→`ConfigEntryAuthFailed` (re-auth flow), `TapoConnectionError`/unknown→`UpdateFailed`, `client.shutdown()` on every error path
- [x] 4.3 Document empty-data → `UpdateFailed("No data returned from device")` WITHOUT `shutdown()`
- [x] 4.4 Remove the stale "shutdown on ANY exception + raise UpdateFailed" text
- [x] 4.5 Document `_async_sync_device_registry` if present (verify from code)

## 5. Rewrite Config flow section

- [x] 5.1 Document `TapoP110ConfigFlow`: creates/reconfigures the hub (account) entry, handles zeroconf discovery, MAC sanitize → unique id, base64 nickname → title
- [x] 5.2 Document `TapoP110DeviceSubentryFlow`: creates/reconfigures a device subentry under an existing hub (host-only form)
- [x] 5.3 Document error mapping (`TapoAuthError`→`invalid_auth`, `TapoConnectionError`→`cannot_connect`) if still accurate (verify from code)

## 6. Add Migration section

- [x] 6.1 Document `async_migrate_entry`: v1→v2 is a clean start (all v1 entries removed via `_safe_remove_entry`, users re-add plugs as subentries)
- [x] 6.2 Document the v2→v2.1 entity-identifier change (`device_id`→`subentry_id`) is NOT migrated; orphaned device-registry rows cleaned once via UI
- [x] 6.3 Note the concurrency guard (multiple v1 entries scheduling overlapping removals; `_safe_remove_entry` ignores already-gone entries)

## 7. Update Important Files table

- [x] 7.1 `manifest.json` row: version 2.2.2, `requirements: ["ecdsa"]`, keep zeroconf/integration_type/iot_class
- [x] 7.2 `__init__.py` row: add `_async_subentry_listener`, `_async_forward_subentry_setup`, `_async_unload_subentry`, `async_migrate_entry`, `_safe_remove_entry` to the role description
- [x] 7.3 `const.py` row: add `SUBENTRY_TYPE_DEVICE`
- [x] 7.4 `config_flow.py` row: mention `TapoP110DeviceSubentryFlow` alongside `TapoP110ConfigFlow`
- [x] 7.5 Verify all other rows are still accurate; fix any that aren't

## 8. Update Code Conventions

- [x] 8.1 Document the subentry entity unique-id convention using the format verified in task 1.1
- [x] 8.2 Document the `runtime_data` coordinator-storage pattern (dict keyed by `subentry_id`)
- [x] 8.3 Document the `async_setup_subentry` platform-handler pattern (one per platform, mapped by `platform.domain`)
- [x] 8.4 Update the "Coordinator reset on error" convention to the new split contract (auth→`ConfigEntryAuthFailed`, transient→`UpdateFailed`)
- [x] 8.5 Keep still-accurate conventions (lazy import, base64 nickname decode, defensive `.get()`, unit conversions in sensor.py, command pattern)

## 9. Update Key Directories + Testing & QA (cross-reference)

- [x] 9.1 In Key Directories, keep the current tree; add a one-line note that `add-dev-tooling-tests` adds `tests/`, `pyproject.toml`, `pyrightconfig.json`, `.github/workflows/`
- [x] 9.2 In Testing & QA, keep the current "no tests exist" text as accurate-until-tooling-lands, and add a one-line cross-reference to `add-dev-tooling-tests`
- [x] 9.3 Do NOT duplicate the tooling change's content

## 10. Update Quirks

- [x] 10.1 Keep "partial coordinator data is normal" (still true)
- [x] 10.2 Update "network blip triggers re-handshake" to reference the new `ConfigEntryAuthFailed`/`UpdateFailed` + `shutdown()` path
- [x] 10.3 Add a quirk: a failed first-refresh does not abort hub setup (per-subentry resilience)
- [x] 10.4 Add a quirk: v1→v2 migration is a clean start, not data migration
- [x] 10.5 Keep the human-readable runtime sensors and setter re-read quirks (still accurate)

## 11. Final verification

- [x] 11.1 Spot-check every architecture claim in the rewritten AGENTS.md against the code: overview, data flow, coordinator contract, config flow split, migration, important files, unique-id convention
- [x] 11.2 Confirm the diff modifies only `AGENTS.md` (no `.py`, `.json`, `.yaml`, `.toml` changes)
- [x] 11.3 Run `openspec validate refresh-agents-md-architecture` and confirm it passes