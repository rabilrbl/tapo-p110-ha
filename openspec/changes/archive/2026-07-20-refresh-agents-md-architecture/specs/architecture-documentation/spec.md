## ADDED Requirements

### Requirement: Architecture sections match the running code
Every architecture-level claim in `AGENTS.md` (Project Overview, Architecture & Data Flow, Coordinator, Config flow, Important Files, Code Conventions, Quirks) MUST accurately describe the v2.2.2 hub+subentry code, not the v1.0.0 single-entry model.

#### Scenario: Project Overview reflects hub+subentry
- **WHEN** a reader checks the Project Overview
- **THEN** it describes one config entry per TP-Link account holding username+password, with one device subentry per plug holding host, and the current version (2.2.2)

#### Scenario: Data flow shows per-subentry coordinators
- **WHEN** a reader checks the Architecture & Data Flow section
- **THEN** it shows `async_setup_entry` building one `TapoP110DataCoordinator` per device subentry, stored on `entry.runtime_data` keyed by `subentry_id`
- **AND** it states a failed first-refresh does NOT abort hub setup (coordinator kept with `last_update_success=False`, retried by HA's 15s loop)

#### Scenario: Subentry lifecycle is documented
- **WHEN** a reader checks the Architecture & Data Flow section
- **THEN** it documents `_async_subentry_listener` (diffs `entry.subentries` vs `runtime_data`, adds/removes/rebuilds only the affected subentry), `_async_forward_subentry_setup` (maps platforms to `async_setup_subentry` handlers), and `_async_unload_subentry` (clears entity/device registries via `async_clear_config_subentry`)

#### Scenario: Coordinator error contract is accurate
- **WHEN** a reader checks the Coordinator section
- **THEN** it states `TapoAuthError`→`ConfigEntryAuthFailed` (triggers re-auth), `TapoConnectionError`/unknown→`UpdateFailed`, `client.shutdown()` on every error path, and empty-data→`UpdateFailed("No data returned from device")` WITHOUT `shutdown()`
- **AND** it does NOT claim "shutdown on ANY exception + raise UpdateFailed" (the stale v1 description)

#### Scenario: Migration is documented truthfully
- **WHEN** a reader checks the migration documentation
- **THEN** it states v1 entries are removed (clean-start, not data-migrated), users re-add plugs as subentries
- **AND** it states the v2→v2.1 device-registry re-key (`device_id`→`subentry_id`) is NOT migrated; orphaned rows are cleaned once via the UI

#### Scenario: Config flow is split correctly
- **WHEN** a reader checks the Config flow section
- **THEN** it documents `TapoP110ConfigFlow` (hub/account entry + zeroconf discovery) and `TapoP110DeviceSubentryFlow` (device subentry create/reconfigure under an existing hub) as separate flows

### Requirement: Important Files table is current
The Important Files table MUST reflect the current `manifest.json` (version 2.2.2, `requirements: ["ecdsa"]`) and include the subentry-related functions in `__init__.py`.

#### Scenario: Manifest fields are correct
- **WHEN** a reader checks the `manifest.json` row in Important Files
- **THEN** it states version 2.2.2 and `requirements: ["ecdsa"]`, not version 1.0.0 or `requirements: []`

#### Scenario: __init__.py row covers subentry lifecycle
- **WHEN** a reader checks the `__init__.py` row in Important Files
- **THEN** it mentions `async_setup_entry`, `_async_subentry_listener`, `_async_forward_subentry_setup`, `_async_unload_subentry`, `async_unload_entry`, and `async_migrate_entry`

### Requirement: Unique-id convention verified from code
The documented subentry entity unique-id convention MUST be verified by reading the platform files' `async_setup_subentry` during implementation, not guessed.

#### Scenario: Unique-id format matches code
- **WHEN** the documented unique-id format is compared against the actual `async_setup_subentry` code in any platform file
- **THEN** they match exactly

### Requirement: No code changes
This change MUST NOT modify any file under `custom_components/`, `manifest.json`, or any runtime/config file. Only `AGENTS.md` is modified.

#### Scenario: Diff is docs-only
- **WHEN** the change's diff is inspected
- **THEN** the only modified file is `AGENTS.md`
- **AND** no `.py`, `.json`, `.yaml`, or `.toml` file is changed

### Requirement: Tooling sections cross-reference, not duplicate
The Key Directories and Testing & QA sections MUST cross-reference the `add-dev-tooling-tests` change for `tests/`, `pyproject.toml`, `pyrightconfig.json`, `.github/workflows/` and the test suite, rather than duplicating that change's content.

#### Scenario: Tooling additions are cross-referenced
- **WHEN** a reader checks Key Directories or Testing & QA
- **THEN** those sections describe the current (pre-tooling) state and note that `add-dev-tooling-tests` adds the dev tooling, tests, and CI
- **AND** they do not redundantly specify the tooling contents owned by the other change