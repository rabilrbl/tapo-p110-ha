# Repository Guidelines

## Project Overview

Custom Home Assistant integration for the TP-Link **Tapo P110** smart plug, speaking the **TPAP protocol** (TP-Link Adaptive Protocol) directly. Firmware 1.4.0+ deprecated the KLAP protocol in favor of TPAP (SPAKE2+ P-256 key exchange + AES-128-CCM encrypted data channel); existing integrations (`tplink`/python-kasa, `tapo`/plugp100) did not support TPAP, so this is a dedicated, vendored implementation. Distributed via HACS. Cloud credentials are required only for the initial SPAKE2+ handshake; polling is fully local.

- **Domain**: `tapo_p110`
- **Integration type**: `device`, `iot_class: local_polling`, 15s poll interval
- **Target**: HA 2026.7+
- **Version**: 2.2.2
- **Architecture**: hub+subentry model — one config entry per TP-Link account (the hub), one device subentry per plug. Each subentry has its own `TapoP110DataCoordinator`.
- **Runtime deps**: `ecdsa` (declared in `manifest.json` `requirements`), `cryptography` + `passlib` (bundled with HA; conditionally imported by `tpap_client.py` for `passwd_id==1`)
- **Repo**: github.com/rabilrbl/tapo-p110-ha

## Architecture & Data Flow

Single integration under `custom_components/tapo_p110/`. No external TPAP library — the protocol client is vendored in `tpap_client.py`.

```
Config Flow (hub entry)                HA setup
  TapoP110ConfigFlow                     async_setup_entry
  (account: username+password)              │
  unique_id = normalized username            ▼
        │                              For each device subentry:
        ▼                                TapoP110DataCoordinator
  Config Entry (hub)                     (DataUpdateCoordinator[dict], 15s)
  ┌─subentries───────────┐                     │
  │ device subentry 1     │          hass.async_add_executor_job
  │ device subentry 2     │                     │
  │ ...                   │                     ▼
  └───────────────────────┘           client.get_all_data()
        │                              (atomic device_info,
        │                               best-effort 9 others)
        │                                     │
        ▼                                     ▼
  entry.runtime_data                  coordinator.data (dict)
  = { subentry_id: coordinator }              │
                                               ▼
                              TapoP110Entity(CoordinatorEntity)
                              x6 platform subclasses per subentry
                              unique_id = f"{subentry_id}_{key}"
                              device identifiers = {(DOMAIN, subentry_id)}
```

**Setup** (`__init__.py`): `async_setup_entry` lazily imports `TapoP110DataCoordinator`, then iterates `entry.subentries` and builds one coordinator per device subentry (keyed by `subentry_id` on `entry.runtime_data`). A failed `async_config_entry_first_refresh` on one device does **not** abort hub setup — the coordinator stays in `runtime_data` with `last_update_success=False` and HA's 15s loop retries it. After all coordinators are built, `async_forward_entry_setups` registers the 6 platforms and `entry.add_update_listener(_async_subentry_listener)` registers the reconciliation listener.

**Subentry lifecycle** (`_async_subentry_listener`): Fired by add/remove/reconfigure events. Diffs `entry.subentries` against `entry.runtime_data`: new subentries get a coordinator + entities (via `_async_forward_subentry_setup`), host changes trigger a teardown + rebuild of just that subentry, deleted subentries get their entities + device-registry entries cleared (via `_async_unload_subentry`) and their coordinator shut down. Sibling subentries are never touched.

**Platform forwarding** (`_async_forward_subentry_setup`): Maps each live `EntityPlatform` to its module's `async_setup_subentry` handler by `platform.domain` (sensor/switch/…). Uses `_make_add_entities` — a factory returning an `AddConfigEntryEntitiesCallback` shim that wraps the async `platform.async_add_entities` in `hass.async_create_task`.

**Config flow** (`config_flow.py`): Two flow classes:
- `TapoP110ConfigFlow(ConfigFlow, domain=DOMAIN, VERSION=2)`: creates/reconfigures the **hub** (account) entry. `async_step_user` collects host+username+password (or host-only if credentials exist). `async_step_zeroconf` handles zeroconf discovery with a hub-picker step. `async_step_reconfigure` updates hub credentials. Hub unique_id = normalized username; title = `Tapo P110 ({username})`. Returns `async_get_supported_subentry_types` mapping `SUBENTRY_TYPE_DEVICE` → `TapoP110DeviceSubentryFlow`.
- `TapoP110DeviceSubentryFlow(ConfigSubentryFlow)`: creates/reconfigures a **device subentry** under an existing hub. Collects host only (credentials from parent hub entry). Deduplicates by MAC against existing subentries. Subentry unique_id = sanitized MAC; title = base64-decoded nickname (fallback to host). Error mapping: `TapoAuthError`→`invalid_auth`, `TapoConnectionError`→`cannot_connect`, other→`unknown`.

**Coordinator** (`coordinator.py`): `TapoP110DataCoordinator(DataUpdateCoordinator[dict[str, Any]])`, `update_interval=timedelta(seconds=15)`. `_async_update_data` runs `client.get_all_data()` via `hass.async_add_executor_job`. Error mapping:
- `TapoAuthError` → `ConfigEntryAuthFailed` (triggers HA re-auth flow) + `client.shutdown()`
- `TapoConnectionError` → `UpdateFailed` + `client.shutdown()`
- Unknown `Exception` → `UpdateFailed` + `client.shutdown()`
- Empty data (`not data`) → `UpdateFailed("No data returned from device")` **without** `shutdown()`

On success, `_async_sync_device_registry(data)` updates the device-registry row with live `device_info` fields and purges stale `device_id`-keyed rows left from v2.0.

**Migration** (`async_migrate_entry`): v1→v2 is a **clean start**: all v1 entries (one per plug) are removed via `_safe_remove_entry` (concurrency-safe; ignores already-gone entries). The v2→v2.1 entity-identifier change (`device_id`→`subentry_id`) is **not** migrated — orphaned device-registry rows are cleaned once via the UI. The new `subentry_id`-keyed rows are created automatically.

**TPAP client** (`tpap_client.py`, vendored, synchronous, stdlib `urllib.request` + 10s timeout):
- `TapoAuthError`, `TapoConnectionError` (subclasses of `Exception`).
- `discover_and_handshake()`: 4-step flow — `login`/`discover`, `login`/`pake_register` (SPAKE2+ P-256 suite-1, cipher `aes_128_ccm`; credentials per `passwd_id`: 2→sha1(pw), 1→passlib md5_crypt, else raw), SPAKE2+ derivation (PBKDF2-HMAC-SHA256 with device iterations → `w`,`h`; `L=x·G+w·M`; `Z`,`V`; SHA256 transcript → HKDF-Expand ConfirmationKeys(64B)+SharedKey(32B); HMAC confirm), `login`/`pake_share` (verifies `dev_confirm`, derives AES-128 session key + 12-byte base nonce, 24h expiry).
- `_ensure_session` re-handshakes if `_ds_url is None` or session expired (monotonic +86400s).
- `_send_request(method, params)`: JSON wrapped, nonce = `base_nonce[:-4] + pack(">I", seq)`, AES-128-CCM (tag_length=16) encrypt, prepend `pack(">I", seq)`, POST `application/octet-stream` to `_ds_url`. **Auto-retries once** on HTTP 403 or decrypt failure by clearing the session + re-handshaking. Error codes `-2202`/`-2203` → `TapoAuthError`.
- `get_all_data()`: **atomic** on `device_info` (failure aborts), **best-effort** on 9 other endpoints (per-call exceptions swallowed) → partial data is possible. Returns dict keyed: `device_info`, `energy_usage`, `emeter_data`, `device_usage`, `device_time`, `led_info`, `auto_update_info`, `auto_off_config`, `protection_power`, `max_power`.
- Setters: `set_device_on`, `set_led_rule`, `set_default_state`, `set_led_on`, `set_auto_update` (re-reads info first to preserve time+random_range), `set_auto_off`/`set_auto_off_enabled`/`set_auto_off_minutes` (re-read config to preserve the other field), `set_power_protection_threshold` (0 disables), `set_power_protection_enabled` (preserves threshold; defaults to `get_max_power().max_power`=3580 if enabling with 0), `reboot()`.

**Entity hierarchy** (`entity.py`): single base `TapoP110Entity(CoordinatorEntity[TapoP110DataCoordinator])`. Each instance receives `coordinator` + `subentry_id`. `DeviceInfo` is anchored to `subentry_id` (not `device_id`): `identifiers={(DOMAIN, subentry_id)}`, name/model/sw_version/hw_version from `coordinator.data["device_info"]` (placeholders when offline). The coordinator re-syncs the device-registry row from live data on each successful poll.

Each platform mixes in its HA entity class:

| Platform file | Class | EntityDescription tuple |
|---|---|---|
| `sensor.py` | `TapoP110Sensor(TapoP110Entity, SensorEntity)` | `SENSORS` (16) |
| `binary_sensor.py` | `TapoP110BinarySensor(TapoP110Entity, BinarySensorEntity)` | `BINARY_SENSORS` (4) |
| `switch.py` | `TapoP110BaseSwitch(TapoP110Entity, SwitchEntity)` + 4 concrete | `SWITCHES` (4) |
| `number.py` | `TapoP110Number(TapoP110Entity, NumberEntity)` | `NUMBERS` (2) |
| `button.py` | `TapoP110Button(TapoP110Entity, ButtonEntity)` | `BUTTONS` (1) |
| `select.py` | `TapoP110Select(TapoP110Entity, SelectEntity)` | `SELECTS` (2) |

Platform `async_setup_entry` iterates all device subentries and creates one entity per description per subentry. `async_setup_subentry` creates entities for a single newly-added subentry. **Unique id convention**: `f"{subentry_id}_{description.key}"`. All command methods wrap synchronous `coordinator.client.*` via `hass.async_add_executor_job` and call `coordinator.async_request_refresh()` after success — **except** `button.py` (`reboot` does not refresh). Command methods catch `TapoAuthError`/`TapoConnectionError`.

**Services**: none. `services.yaml` is a stub (`# Tapo P110 services (none yet)`). All controllable features are entities.

**Diagnostics** (`diagnostics.py`): `async_get_config_entry_diagnostics` returns `coordinator.data` with `_redact` recursively replacing keys `{device_id, mac, hw_id, fw_id, oem_id, ssid, owner, ip}` with `***REDACTED***`. Notably leaves `nickname`, `fw_ver`, `specs` exposed.

## Key Directories

```
.
├── README.md                 # sole docs; install, setup, supported devices
├── hacs.json                 # {"name":"Tapo P110","render_readme":true}
├── icon.png                  # HACS display icon
├── pyproject.toml             # dev dependencies (uv), ruff config, pytest config
├── pyrightconfig.json         # basedpyright config (scoped to integration + tests)
├── .gitignore                 # __pycache__/, *.pyc, .venv/, .pytest_cache/, .ruff_cache/, .pyright/
├── .pre-commit-config.yaml   # ruff + basedpyright hooks (optional contributor step)
├── .github/workflows/ci.yml  # lint + format-check + type-check + tests on push/PR
├── brand/icon.png             # brand asset (not under custom_components)
├── tests/
│   ├── conftest.py            # shared fixtures (mock_urlopen, mock_client, spake2_vector)
│   ├── fixtures/spake2_vector.json  # deterministic SPAKE2+ derivation test vector
│   ├── test_tpap_client.py   # protocol/crypto/setters/batch-polling tests (34 tests)
│   └── test_coordinator.py    # error-mapping invariant tests (5 tests)
└── custom_components/
    └── tapo_p110/            # the integration (see Important Files)
        ├── translations/en.json
        ├── icon.png, dark_icon.png
        └── *.py, manifest.json, strings.json, services.yaml
```

## Development Commands

```bash
# Set up the dev environment (installs HA + all dev deps into .venv/)
uv sync

# Lint
uv run ruff check custom_components/tapo_p110/ tests/

# Format check (or: uv run ruff format to auto-fix)
uv run ruff format --check custom_components/tapo_p110/ tests/

# Type-check (basedpyright, scoped to integration + tests)
uv run basedpyright

# Run tests (offline, deterministic, no real device required)
uv run pytest

# Optional: install pre-commit hooks for local lint/type-check on commit
uv run pre-commit install
```

Lint and type-check run on every push and PR via `.github/workflows/ci.yml`.

## Code Conventions & Common Patterns

- **Async**: All HA-facing code is `async`. All TPAP I/O is **synchronous** (`tpap_client.py` uses stdlib `urllib.request`) and must be offloaded via `hass.async_add_executor_job(...)` — never call `client.*` methods directly from the event loop.
- **Hub+subentry model**: One config entry (hub) per TP-Link account; one device subentry per plug. Coordinators are stored on `entry.runtime_data` keyed by `subentry_id`. Entities are per-subentry, not per-entry.
- **Subentity unique-id**: `f"{subentry_id}_{description.key}"`. Device identifiers are `{(DOMAIN, subentry_id)}` — anchored to the subentry, not `device_id` (which is absent when the plug is offline at setup).
- **Subentry reconciliation**: `_async_subentry_listener` fires on add/remove/reconfigure and diffs `entry.subentries` against `entry.runtime_data`. Only the affected subentry's coordinator + entities are touched; siblings are never disrupted.
- **State access is defensive**: because `get_all_data` is best-effort for 9 of 10 endpoints, entity `native_value`/`available`/`is_on` properties use `.get()` with `None`/`False` fallbacks. `available` is `False` when `coordinator.data is None`. Follow this pattern for any new entity.
- **Entity registration**: define a module-level tuple of `*EntityDescription` (e.g. `SENSORS`), iterate it in `async_setup_entry`/`async_setup_subentry`, set `_attr_unique_id = f"{subentry_id}_{description.key}"`. Do not invent a second convention.
- **Command pattern**: `_async_turn(...)` / `async_set_native_value` / `async_select_option` / `async_press` wrap the setter via executor, then `await coordinator.async_request_refresh()` (except `reboot`), catching `TapoAuthError`/`TapoConnectionError` and logging.
- **Coordinator error mapping**: `TapoAuthError` → `ConfigEntryAuthFailed` + `shutdown()` (triggers HA re-auth flow); `TapoConnectionError`/unknown → `UpdateFailed` + `shutdown()` (forces fresh SPAKE2+ handshake on next poll); empty data → `UpdateFailed` **without** `shutdown()`.
- **Failed first-refresh does not abort hub setup**: a device that's offline at setup time stays in `runtime_data` with `last_update_success=False` and is retried by HA's 15s update loop.
- **Lazy import**: `__init__.async_setup_entry` imports `TapoP110DataCoordinator` inside the function so `cryptography`/`ecdsa` load only when an entry is added. Keep heavy/optional imports lazy in `__init__.py`.
- **Base64 nickname decode** happens independently in `entity.py`, `coordinator.py` (`_async_sync_device_registry`), and `config_flow.py` (with fallback to raw on error). `ssid` is also base64-decoded in `sensor.py`.
- **Manifest**: `manifest.json` `requirements: ["ecdsa"]` — `ecdsa` is explicitly declared; `cryptography` is bundled with HA; `passlib` is conditionally imported by `tpap_client.py` for `passwd_id==1` (md5_crypt). TPAP is vendored.
- **Config flow has two classes**: `TapoP110ConfigFlow` for the hub entry (account), `TapoP110DeviceSubentryFlow` for device subentries (plug). Adding a second device shows a host-only form using the hub's credentials.
- **Naming**: domain `tapo_p110`; classes `TapoP110*`; constants `UPPER_SNAKE`; description tuples `UPPER_PLURAL` (`SENSORS`, `SWITCHES`, …).
- **Line length**: ruff enforces 120 columns (HA core uses 100). This divergence avoids a noisy first-pass reformat; revisit if the integration is ever upstreamed.

## Important Files

| Path | Role |
|---|---|
| `custom_components/tapo_p110/manifest.json` | HA manifest: domain `tapo_p110`, `iot_class: local_polling`, `integration_type: device`, `config_flow: true`, `requirements: ["ecdsa"]`, zeroconf `_http._tcp.local.` name `tplink*`, version `2.2.2`, codeowners `["@rabilrbl"]` |
| `custom_components/tapo_p110/__init__.py` | Hub setup: `async_setup_entry` (one coordinator per device subentry on `runtime_data`), `_async_subentry_listener` (add/remove/rebuild), `_async_forward_subentry_setup` + `_make_add_entities` (platform handler shim), `_async_unload_subentry` (entity + device registry cleanup), `async_unload_entry` (shutdown all coordinators), `async_migrate_entry` (v1→v2 clean start), `_safe_remove_entry` |
| `custom_components/tapo_p110/const.py` | `DOMAIN`, `CONF_HOST/USERNAME/PASSWORD`, `SUBENTRY_TYPE_DEVICE`, `DEFAULT_UPDATE_INTERVAL = 15` |
| `custom_components/tapo_p110/config_flow.py` | `TapoP110ConfigFlow` (hub entry: user + zeroconf + reconfigure) + `TapoP110DeviceSubentryFlow` (device subentry: add/reconfigure plug); hub unique_id = normalized username; subentry unique_id = sanitized MAC; error mapping |
| `custom_components/tapo_p110/coordinator.py` | `TapoP110DataCoordinator`; 15s poll; `TapoAuthError`→`ConfigEntryAuthFailed`+shutdown, transient→`UpdateFailed`+shutdown, empty→`UpdateFailed` (no shutdown); `_async_sync_device_registry` updates device-registry row from live data |
| `custom_components/tapo_p110/tpap_client.py` | **Vendored TPAP protocol** (SPAKE2+, AES-128-CCM); the core reverse-engineered logic; all getters/setters |
| `custom_components/tapo_p110/entity.py` | `TapoP110Entity` base; `DeviceInfo` builder anchored to `subentry_id`; `build_device_info` helper |
| `custom_components/tapo_p110/{sensor,binary_sensor,switch,number,button,select}.py` | Platform implementations + `EntityDescription` tuples; `async_setup_entry` (all subentries) + `async_setup_subentry` (single subentry) |
| `custom_components/tapo_p110/diagnostics.py` | Diagnostics dump with PII redaction |

## Testing & QA

The test suite uses `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`). Run `uv run pytest` — all tests are offline and deterministic (no real device required).

**Test structure:**
- `tests/test_tpap_client.py` (34 tests): SPAKE2+ derivation vectors, AES-CCM nonce sequencing, 403/decrypt retry logic, error-code mapping (`-2202`/`-2203` → `TapoAuthError`), `get_all_data` atomic-vs-best-effort semantics, setter preservation (auto-update, auto-off, power-protection), no-session guard.
- `tests/test_coordinator.py` (5 tests): Error-mapping invariants — `TapoAuthError` → `ConfigEntryAuthFailed` + `shutdown()`, `TapoConnectionError`/unknown → `UpdateFailed` + `shutdown()`, empty data → `UpdateFailed` without `shutdown()`, success path returns data.
- `tests/conftest.py`: shared fixtures (`mock_urlopen`, `mock_client`, `spake2_vector`).
- `tests/fixtures/spake2_vector.json`: deterministic SPAKE2+ derivation test vector (no credentials).

CI runs `ruff check`, `ruff format --check`, `basedpyright`, and `pytest` on every push and PR (`.github/workflows/ci.yml`).

### Quirks to keep in mind when changing code
- Partial coordinator data is normal — entities must tolerate missing keys.
- A network blip or auth failure triggers a full SPAKE2+ re-handshake on the next poll: `TapoAuthError` → `ConfigEntryAuthFailed` (re-auth flow) + `shutdown()`, `TapoConnectionError`/unknown → `UpdateFailed` + `shutdown()`. Empty data → `UpdateFailed` without shutdown.
- A device offline at setup does **not** abort the hub — its coordinator stays in `runtime_data` and retries via HA's 15s loop.
- v1→v2 migration is a clean start, not a data migration: all v1 entries are removed, users re-add plugs as subentries. v2→v2.1 entity-identifier change (`device_id`→`subentry_id`) is NOT migrated; orphaned device-registry rows are cleaned once via UI.
- `today_runtime`/`month_runtime`/`on_time` sensors return human-readable strings, not numeric values.
- `set_auto_update` and the auto-off setters re-read device config first to preserve unchanged fields — mirror this when adding paired setters.
- Diagnostics redacts PII but intentionally exposes `nickname`, `fw_ver`, `specs`.