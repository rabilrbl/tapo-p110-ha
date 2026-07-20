## Why

`AGENTS.md` is the repo's sole architecture reference for agents and contributors, but it describes a version that no longer exists. It documents the v1.0.0 single-entry-per-plug model; the code is v2.2.2 with a hub+subentry architecture, a different coordinator error contract, a migration path, and a subentry reconciliation listener. Any agent or contributor reading `AGENTS.md` today is actively misled. This change brings the architecture sections back in sync with the running code — no tooling (that's `add-dev-tooling-tests`), no behavior change, just accurate documentation.

## What Changes

- Rewrite `AGENTS.md` **Project Overview** to reflect the hub+subentry model (one config entry per TP-Link account, one device subentry per plug) and the current version (2.2.2).
- Rewrite **Architecture & Data Flow** to describe the actual setup path: `async_setup_entry` builds one `TapoP110DataCoordinator` per device subentry, stores them on `entry.runtime_data` keyed by `subentry_id`, and a failed first-refresh does NOT abort hub setup (coordinator stays with `last_update_success=False` and HA's 15s loop retries it).
- Add the **subentry lifecycle** to the data-flow section: `_async_subentry_listener` diffs `entry.subentries` against `runtime_data` and adds/removes/rebuilds only the affected subentry's coordinator + entities (siblings untouched); `_async_forward_subentry_setup` maps platforms to `async_setup_subentry` handlers; `_async_unload_subentry` clears entity/device registries via `async_clear_config_subentry`.
- Add the **migration** section: `async_migrate_entry` removes all v1 entries (clean-start v1→v2; no data carry-over); the v2→v2.1 entity-identifier change (`device_id`→`subentry_id`) is NOT migrated — orphaned device-registry rows are cleaned up once via the UI.
- Rewrite **Coordinator** section: `TapoP110DataCoordinator` now maps `TapoAuthError`→`ConfigEntryAuthFailed` (triggers HA re-auth flow), `TapoConnectionError`/unknown→`UpdateFailed`, and calls `client.shutdown()` on every error path; empty data → `UpdateFailed("No data returned from device")` (no shutdown). This replaces the stale "shutdown on ANY exception + raise UpdateFailed" description.
- Update **Config flow** section: split into `TapoP110ConfigFlow` (hub/account entry, zeroconf discovery) and `TapoP110DeviceSubentryFlow` (device subentry create/reconfigure under an existing hub).
- Update **Important Files** table: bump manifest version to 2.2.2, `requirements: ["ecdsa"]` (not `[]`), add `SUBENTRY_TYPE_DEVICE` to const, note `async_migrate_entry` and the subentry listener functions in `__init__.py`.
- Update **Key Directories** tree: note the `tests/`, `pyproject.toml`, `pyrightconfig.json`, `.github/workflows/` additions are owned by the `add-dev-tooling-tests` change (cross-referenced, not duplicated).
- Update **Code Conventions** to reflect the subentry unique-id convention (`f"{entry_id}:{subentry_id}_{key}"` or whatever the code actually uses — to be verified during implementation), the `runtime_data` coordinator-storage pattern, and the `async_setup_subentry` platform-handler pattern.
- Correct the **Quirks** section: "A network blip triggers a full SPAKE2+ re-handshake" is still true but now via `ConfigEntryAuthFailed`/`UpdateFailed` + `client.shutdown()`, not the old blanket-`UpdateFailed` path.
- **No code changes.** `AGENTS.md` is the only file modified. No runtime behavior change.

## Capabilities

### New Capabilities
- `architecture-documentation`: Accurate, code-synced architecture reference in `AGENTS.md` covering the hub+subentry model, per-subentry coordinators, subentry lifecycle listener, migration, and the current coordinator error-mapping contract.

### Modified Capabilities
<!-- None. No existing specs. -->

## Impact

- **Affected files (modified):** `AGENTS.md` only.
- **Affected files (unchanged):** all `custom_components/tapo_p110/*.py`, `manifest.json`, all configs — no code or runtime change.
- **Private APIs touched:** none. This is documentation only.
- **Rollback:** `git revert` the `AGENTS.md` change.
- **Risk:** very low. Documentation-only. The only risk is residual inaccuracy if the code changes between this change landing and a future code change — mitigated by landing this immediately and treating AGENTS.md as a living document.
- **Dependency:** should land after (or alongside) `add-dev-tooling-tests` so the Key Directories and Testing & QA sections aren't immediately re-stale. If landed first, those tooling sections remain stale until the other change lands — acceptable, since this change explicitly cross-references the tooling change rather than duplicating it.