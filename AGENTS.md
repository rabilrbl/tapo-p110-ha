# Repository Guidelines

## Project Overview

Custom Home Assistant integration for the TP-Link **Tapo P110** smart plug, speaking the **TPAP protocol** (TP-Link Adaptive Protocol) directly. Firmware 1.4.0+ deprecated the KLAP protocol in favor of TPAP (SPAKE2+ P-256 key exchange + AES-128-CCM encrypted data channel); existing integrations (`tplink`/python-kasa, `tapo`/plugp100) did not support TPAP, so this is a dedicated, vendored implementation. Distributed via HACS. Cloud credentials are required only for the initial SPAKE2+ handshake; polling is fully local.

- **Domain**: `tapo_p110`
- **Integration type**: `device`, `iot_class: local_polling`, 15s poll interval
- **Target**: HA 2026.7+
- **Runtime deps**: `ecdsa` + `cryptography` (assumed bundled with HA; `manifest.json` declares `requirements: []`)
- **Repo**: github.com/rabilrbl/tapo-p110-ha

## Architecture & Data Flow

Single integration under `custom_components/tapo_p110/`. No external TPAP library — the protocol client is vendored in `tpap_client.py`.

```
Config Flow (user/reconfigure)            HA setup
  TapoP110Client.discover_and_handshake      async_setup_entry
  (executor; SPAKE2+ over HTTP)                │
        │                                       ▼
        ▼                              TapoP110DataCoordinator
  unique_id = MAC (sanitized)          (DataUpdateCoordinator[dict], 15s)
  title = base64(nickname)                     │
        │                                       ▼  hass.async_add_executor_job
        ▼                              client.get_all_data()  (atomic device_info,
  config entry stored                     best-effort 9 other endpoints)
        │                                       │
        └─► hass.data[DOMAIN][entry_id]         ▼
                 = coordinator            coordinator.data (dict)
                          │                     │
                          ▼                     ▼
            async_forward_entry_setups    TapoP110Entity(CoordinatorEntity)
            [SENSOR, SWITCH, BINARY_SENSOR,   │  x6 platform subclasses
             BUTTON, NUMBER, SELECT]         │  unique_id = f"{entry_id}_{key}"
                                            ▼
                                     27 entities per device
```

**Setup** (`__init__.py`): `async_setup_entry` **lazily imports** `TapoP110DataCoordinator` (keeps `cryptography`/`ecdsa` out of HA's import graph until an entry exists), constructs it, awaits `async_config_entry_first_refresh()`, stores it in `hass.data.setdefault(DOMAIN, {})[entry.entry_id]`, then forwards setups to the 6 platforms. `async_unload_entry` unloads platforms, pops the coordinator, and calls `coordinator.async_shutdown()` → `client.shutdown()`.

**Config flow** (`config_flow.py`): `TapoP110ConfigFlow(ConfigFlow, domain=DOMAIN)`, `VERSION=1`. `async_step_user` reuses credentials from any existing entry (shows host-only form via `_get_existing_credentials()`) or shows the full host+username+password form. Validation = construct `TapoP110Client` and run `discover_and_handshake` in executor. Error mapping: `TapoAuthError`→`invalid_auth`, `TapoConnectionError`→`cannot_connect`, other→`unknown`. Unique id = MAC with `:`/`-` stripped; title = base64-decoded `nickname`. `async_step_reconfigure` re-validates and calls `async_update_reload_and_end`, updating host/username/password in place.

**Coordinator** (`coordinator.py`): `TapoP110DataCoordinator(DataUpdateCoordinator[dict[str, Any]])`, `update_interval=timedelta(seconds=15)`. `_async_update_data` runs `client.get_all_data()` via `hass.async_add_executor_job`. **On ANY exception** it calls `client.shutdown()` (drops the session) and raises `UpdateFailed` — forces a full SPAKE2+ re-handshake on the next 15s poll (robust but not free; a transient blip re-handshakes). Empty data → `UpdateFailed("No data returned from device")`.

**TPAP client** (`tpap_client.py`, vendored, synchronous, stdlib `urllib.request` + 10s timeout):
- `TapoAuthError`, `TapoConnectionError` (subclasses of `Exception`).
- `discover_and_handshake()`: 4-step flow — `login`/`discover`, `login`/`pake_register` (SPAKE2+ P-256 suite-1, cipher `aes_128_ccm`; credentials per `passwd_id`: 2→sha1(pw), 1→passlib md5_crypt, else raw), SPAKE2+ derivation (PBKDF2-HMAC-SHA256 with device iterations → `w`,`h`; `L=x·G+w·M`; `Z`,`V`; SHA256 transcript → HKDF-Expand ConfirmationKeys(64B)+SharedKey(32B); HMAC confirm), `login`/`pake_share` (verifies `dev_confirm`, derives AES-128 session key + 12-byte base nonce, 24h expiry).
- `_ensure_session` re-handshakes if `_ds_url is None` or session expired (monotonic +86400s).
- `_send_request(method, params)`: JSON wrapped, nonce = `base_nonce[:-4] + pack(">I", seq)`, AES-128-CCM (tag_length=16) encrypt, prepend `pack(">I", seq)`, POST `application/octet-stream` to `_ds_url`. **Auto-retries once** on HTTP 403 or decrypt failure by clearing the session + re-handshaking. Error codes `-2202`/`-2203` → `TapoAuthError`.
- `get_all_data()`: **atomic** on `device_info` (failure aborts), **best-effort** on 9 other endpoints (per-call exceptions swallowed) → partial data is possible. Returns dict keyed: `device_info`, `energy_usage`, `emeter_data`, `device_usage`, `device_time`, `led_info`, `auto_update_info`, `auto_off_config`, `protection_power`, `max_power`.
- Setters: `set_device_on`, `set_led_rule`, `set_default_state`, `set_led_on`, `set_auto_update` (re-reads info first to preserve time+random_range), `set_auto_off`/`set_auto_off_enabled`/`set_auto_off_minutes` (re-read config to preserve the other field), `set_power_protection_threshold` (0 disables), `set_power_protection_enabled` (preserves threshold; defaults to `get_max_power().max_power`=3580 if enabling with 0), `reboot()`.

**Entity hierarchy** (`entity.py`): single base `TapoP110Entity(CoordinatorEntity[TapoP110DataCoordinator])` builds `DeviceInfo` from `coordinator.data["device_info"]` (base64-decoded `nickname`, `identifiers={(DOMAIN, device_id or entry_id)}`, manufacturer "TP-Link", model `f"P110 ({specs})"`). Each platform mixes in its HA entity class:

| Platform file | Class | EntityDescription tuple |
|---|---|---|
| `sensor.py` | `TapoP110Sensor(TapoP110Entity, SensorEntity)` | `SENSORS` (16) |
| `binary_sensor.py` | `TapoP110BinarySensor(TapoP110Entity, BinarySensorEntity)` | `BINARY_SENSORS` (4) |
| `switch.py` | `TapoP110BaseSwitch(TapoP110Entity, SwitchEntity)` + 4 concrete | `SWITCHES` (4) |
| `number.py` | `TapoP110Number(TapoP110Entity, NumberEntity)` | `NUMBERS` (2) |
| `button.py` | `TapoP110Button(TapoP110Entity, ButtonEntity)` | `BUTTONS` (1) |
| `select.py` | `TapoP110Select(TapoP110Entity, SelectEntity)` | `SELECTS` (2) |

Platform `async_setup_entry` pulls `coordinator = hass.data[DOMAIN][entry.entry_id]` and instantiates one entity per description in the module-level tuple. **Unique id convention**: `f"{entry.entry_id}_{description.key}"`. All command methods wrap synchronous `coordinator.client.*` via `hass.async_add_executor_job` and call `coordinator.async_request_refresh()` after success — **except** `button.py` (`reboot` does not refresh). Command methods catch `TapoAuthError`/`TapoConnectionError`.

**Services**: none. `services.yaml` is a stub (`# Tapo P110 services (none yet)`). All controllable features are entities.

**Diagnostics** (`diagnostics.py`): `async_get_config_entry_diagnostics` returns `coordinator.data` with `_redact` recursively replacing keys `{device_id, mac, hw_id, fw_id, oem_id, ssid, owner, ip}` with `***REDACTED***`. Notably leaves `nickname`, `fw_ver`, `specs` exposed.

## Key Directories

```
.
├── README.md                 # sole docs; install, setup, supported devices
├── hacs.json                 # {"name":"Tapo P110","render_readme":true}
├── icon.png                  # HACS display icon
├── .gitignore                # __pycache__/, *.pyc, *.pyo, .DS_Store only
├── brand/icon.png            # brand asset (not under custom_components)
└── custom_components/
    └── tapo_p110/            # the integration (see Important Files)
        ├── translations/en.json
        ├── icon.png, dark_icon.png
        └── *.py, manifest.json, strings.json, services.yaml
```

No `tests/`, `docs/`, `scripts/`, `.github/`, `pyproject.toml`, `setup.py`, `requirements*.txt`, `ruff.toml`, `tox.ini`, `Makefile`, or `.pre-commit-config.yaml` exist.

## Development Commands

There is **no build, test, lint, or CI pipeline**. The repo ships source + manifest + translations + icons only. Validation is done by running Home Assistant with the integration installed:

```bash
# Manual install for local dev: copy the integration into an HA config dir
cp -r custom_components/tapo_p110 /path/to/ha/config/custom_components/
# then restart HA and add the "Tapo P110" integration via Settings → Devices & Services

# HACS dev install: add this repo as a custom repository (category: Integration)
#   https://github.com/rabilrbl/tapo-p110-ha
```

If you add a dev toolchain (pytest, ruff, pre-commit), this section should be updated. Until then, there are no automated quality gates.

## Code Conventions & Common Patterns

- **Async**: All HA-facing code is `async`. All TPAP I/O is **synchronous** (`tpap_client.py` uses stdlib `urllib.request`) and must be offloaded via `hass.async_add_executor_job(...)` — never call `client.*` methods directly from the event loop.
- **State access is defensive**: because `get_all_data` is best-effort for 9 of 10 endpoints, entity `native_value`/`available`/`is_on` properties use `.get()` with `None`/`False` fallbacks. `available` is `False` when `coordinator.data is None`. Follow this pattern for any new entity.
- **Entity registration**: define a module-level tuple of `*EntityDescription` (e.g. `SENSORS`), iterate it in `async_setup_entry`, set `unique_id = f"{entry.entry_id}_{description.key}"`. Do not invent a second convention.
- **Command pattern**: `_async_turn(...)` / `async_set_native_value` / `async_select_option` / `async_press` wrap the setter via executor, then `await coordinator.async_request_refresh()` (except `reboot`), catching `TapoAuthError`/`TapoConnectionError` and logging.
- **Coordinator reset on error**: `_async_update_data` calls `client.shutdown()` on **any** exception before raising `UpdateFailed`. This intentionally drops the session to force a fresh handshake. Preserve this when modifying the update path.
- **Lazy import**: `__init__.async_setup_entry` imports `TapoP110DataCoordinator` inside the function so `cryptography`/`ecdsa` load only when an entry is added. Keep heavy/optional imports lazy in `__init__.py`.
- **Base64 nickname decode** happens independently in `entity.py` and `config_flow.py` (with fallback to raw on error). `ssid` is also base64-decoded in `sensor.py`.
- **Unit conversions live in `sensor.py` `native_value`**: power mW→W (`/1000`, r2), energy Wh→kWh (`/1000`, r3; total from `emeter_data.energy_wh`), voltage mV→V (`/1000`, r1), current mA→A (`/1000`, r3). `_format_duration(seconds)` (sensor.py L24) renders `today_runtime`/`month_runtime`/`on_time` as human strings (top-3 non-zero units: 30d/mo, 12mo/y) — these are **non-numeric** state strings despite being plain `SensorEntityDescription`.
- **Config flow reuses existing credentials** across entries (`_get_existing_credentials`); a second device added to the same account shows a host-only form.
- **Naming**: domain `tapo_p110`; classes `TapoP110*`; constants `UPPER_SNAKE`; description tuples `UPPER_PLURAL` (`SENSORS`, `SWITCHES`, …).
- **Manifest**: `manifest.json` `requirements: []` is intentional — TPAP is vendored. Do not add `cryptography`/`ecdsa` there unless you also confirm HA's bundled versions are insufficient; README states they ship with HA.

## Important Files

| Path | Role |
|---|---|
| `custom_components/tapo_p110/manifest.json` | HA manifest: domain `tapo_p110`, `iot_class: local_polling`, `integration_type: device`, `config_flow: true`, `requirements: []`, zeroconf `_http._tcp.local.` name `tplink*`, version `1.0.0`, codeowners `["@rabilrbl"]` |
| `custom_components/tapo_p110/__init__.py` | Setup entry point; `PLATFORMS` list; lazy coordinator import; `hass.data[DOMAIN][entry_id]` storage; unload + shutdown |
| `custom_components/tapo_p110/const.py` | `DOMAIN`, `CONF_HOST/USERNAME/PASSWORD`, `DEFAULT_UPDATE_INTERVAL = 15` |
| `custom_components/tapo_p110/config_flow.py` | `TapoP110ConfigFlow`; user + reconfigure steps; MAC unique id; base64 nickname title; error mapping |
| `custom_components/tapo_p110/coordinator.py` | `TapoP110DataCoordinator`; 15s poll; shutdown-on-error; `get_all_data` keys |
| `custom_components/tapo_p110/tpap_client.py` | **Vendored TPAP protocol** (SPAKE2+, AES-128-CCM); the core reverse-engineered logic; 489 lines; all getters/setters |
| `custom_components/tapo_p110/entity.py` | `TapoP110Entity` base; `DeviceInfo` builder |
| `custom_components/tapo_p110/{sensor,binary_sensor,switch,number,button,select}.py` | Platform implementations + `EntityDescription` tuples |
| `custom_components/tapo_p110/diagnostics.py` | Diagnostics dump with PII redaction |
| `custom_components/tapo_p110/services.yaml` | Stub (no services) |
| `custom_components/tapo_p110/strings.json` + `translations/en.json` | Config-flow UI strings (identical content) |
| `hacs.json` | HACS repo manifest: `{"name":"Tapo P110","render_readme":true}` |
| `README.md` | Sole docs: install, setup, supported devices (P110 IN 1.4.3; P110 EU/UK/AU ≥1.4.0) |

## Runtime/Tooling Preferences

- **Runtime**: Home Assistant 2026.7+ (Python 3.x as bundled by HA). This is an HA custom integration — it is not run standalone.
- **Required Python packages at runtime**: `ecdsa` and `cryptography` (per README, bundled with HA). `passlib` is conditionally imported by `tpap_client.py` only for `passwd_id == 1` (md5_crypt credentials). None are listed in `manifest.json` `requirements`.
- **Package manager / build**: none. No `pyproject.toml`, `setup.py`, `requirements.txt`, or lockfiles. Distribution is HACS-only.
- **Discovery**: zeroconf `_http._tcp.local.` with name `tplink*`.
- **No external services/cloud after setup**: polling is local; cloud credentials are used solely for the SPAKE2+ handshake.

## Testing & QA

**No tests exist** and **no test framework is configured**. Confirmed absent: `tests/`, `test_*.py`, `conftest.py`, `pytest.ini`, `pyproject.toml`, `tox.ini`, `requirements*.txt`, `unittest`/`pytest` imports anywhere in `custom_components/`. There is no CI (no `.github/`), no lint config (`ruff.toml`/`.ruff.toml`/`setup.cfg`), and no pre-commit hook.

When adding tests, follow the [Home Assistant test conventions](https://developers.home-assistant.io/docs/development_testing/) (`pytest`, `pytest-asyncio`, `aiohttp` test harness, `homeassistant.test`); add a `pyproject.toml`/`requirements_test.txt` and update this section. If you add CI, place workflows under `.github/workflows/` and update `.gitignore` (currently minimal: only `__pycache__/`, `*.pyc`, `*.pyo`, `.DS_Store`).

### Quirks to keep in mind when changing code

- Partial coordinator data is normal — entities must tolerate missing keys.
- A network blip triggers a full SPAKE2+ re-handshake on the next poll (by design).
- `today_runtime`/`month_runtime`/`on_time` sensors return human-readable strings, not numeric values.
- `set_auto_update` and the auto-off setters re-read device config first to preserve unchanged fields — mirror this when adding paired setters.
- Diagnostics redacts PII but intentionally exposes `nickname`, `fw_ver`, `specs`.