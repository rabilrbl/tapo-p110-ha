## 1. Dev environment (uv + pyproject + pyrightconfig)

- [x] 1.1 Create `pyproject.toml` with PEP 621 project metadata (name `tapo-p110-ha`, no `[build-system]` producing a wheel; integration stays HACS source-distributed)
- [x] 1.2 Add `[tool.uv]` dev-dependency group pin `homeassistant==2026.7.*`, plus `ecdsa`, `cryptography`, `passlib`, `pytest`, `pytest-asyncio`, `aiohttp`, `ruff`, `basedpyright`
- [x] 1.3 Run `uv sync` and verify `python -c "import homeassistant"` succeeds in the venv
- [x] 1.4 Create `pyrightconfig.json` at repo root: `include = ["custom_components/tapo_p110", "tests"]`, `reportMissingImports = true`, venv on path
- [x] 1.5 Verify the `Import "homeassistant.*" could not be resolved` LSP error is gone when the editor uses the project venv
- [x] 1.6 Update `.gitignore` to ignore `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.pyright/` (keep existing `__pycache__/`, `*.pyc`, `*.pyo`, `.DS_Store`)

## 2. Lint and format (ruff)

- [x] 2.1 Add `[tool.ruff]` config to `pyproject.toml`: line-length 120, target Python 3.14, rule families E/F/I/UP/B/SIM/ASYNC/RUF
- [x] 2.2 Run `uv run ruff check custom_components/tapo_p110/` and capture the baseline violations
- [x] 2.3 Apply behavior-preserving fixes only (unused imports, import sorting, style); review each diff to confirm no logic change
- [x] 2.4 Run `uv run ruff format custom_components/tapo_p110/ tests/` and verify `ruff format --check` passes
- [x] 2.5 Confirm `uv run ruff check` exits 0 on the full source tree

## 3. Static type-check (basedpyright)

- [x] 3.1 Run `uv run basedpyright custom_components/tapo_p110/` and capture the baseline errors
- [x] 3.2 Apply additive type annotations and mechanical fixes only; add narrowly-scoped `# type: ignore` with a comment for HA dynamic APIs that cannot be typed
- [x] 3.3 Confirm `uv run basedpyright` exits clean (or with only documented suppressions) on `custom_components/tapo_p110/` and `tests/`
- [x] 3.4 Verify no `Import could not be resolved` errors remain for `homeassistant`, `cryptography`, `ecdsa`, or `passlib`
## 4. Unit tests — tpap_client.py

- [x] 4.1 Create `tests/conftest.py` with shared fixtures (mock `urllib.request.urlopen` factory, recorded SPAKE2+ vector loader)
- [x] 4.2 Capture one real SPAKE2+ handshake vector (client keypair, server public, `w`/`h`, `L`/`Z`/`V`, confirmation keys, session key, base nonce) into `tests/fixtures/spake2_vector.json` — no credentials, only ephemeral artifacts
- [x] 4.3 `tests/test_tpap_client.py`: test SPAKE2+ derivation reproduces the recorded vector
- [x] 4.4 Test AES-CCM nonce sequencing: request nonce = `base_nonce[:-4] + pack(">I", seq)`, `seq` increments per success, response nonce from response's leading 4 bytes
- [x] 4.5 Test 403 → single re-handshake retry (mock 403 then success); assert `_retried=True` on the retry and session cleared before retry
- [x] 4.6 Test repeated 403 (`_retried=True`) → `TapoConnectionError`, no further recursion
- [x] 4.7 Test decrypt failure → single re-handshake retry; repeated decrypt failure → `TapoConnectionError`
- [x] 4.8 Test `error_code` `-2202` and `-2203` → `TapoAuthError`; `error_code` 0 → returns `result`
- [x] 4.9 Test no-session (`_ds_url`/`_seq` is None after `_ensure_session`) → `TapoConnectionError` without encryption
- [x] 4.10 Test `get_all_data`: `device_info` failure aborts (no partial dict); best-effort endpoint non-auth exception is swallowed (key omitted); best-effort `TapoAuthError` is re-raised
- [x] 4.11 Test `set_auto_update` re-reads `get_auto_update_info` and preserves `time`/`random_range` (fallback 180/120)
- [x] 4.12 Test `set_auto_off_enabled` preserves `delay_min` (fallback 120); `set_auto_off_minutes` preserves `enable` (fallback False)
- [x] 4.13 Test `set_power_protection_enabled(True)` with threshold 0 → calls `get_max_power`, defaults to `max_power` (fallback 3580); `set_power_protection_enabled(False)` preserves threshold
- [x] 4.14 Test `set_power_protection_threshold(0)` → `{"enabled": False, "protection_power": 0}`; `set_power_protection_threshold(500)` → `{"enabled": True, "protection_power": 500}`
- [x] 4.15 Run `uv run pytest tests/test_tpap_client.py` and confirm all pass offline with network disabled

## 5. Unit tests — coordinator error mapping

- [x] 5.1 Add a `MockTapoP110Client` fixture in `tests/conftest.py` whose `get_all_data` and `shutdown` are controllable
- [x] 5.2 `tests/test_coordinator.py`: test `TapoAuthError` from `get_all_data` → coordinator raises `ConfigEntryAuthFailed` and `shutdown()` called
- [x] 5.3 Test `TapoConnectionError` → `UpdateFailed` and `shutdown()` called
- [x] 5.4 Test unknown `Exception` → `UpdateFailed` and `shutdown()` called
- [x] 5.5 Test empty dict (`{}`) → `UpdateFailed` ("No data returned") and `shutdown()` NOT called
- [x] 5.6 Test non-empty dict → returned as `data` without raising
- [x] 5.7 Run `uv run pytest tests/test_coordinator.py` and confirm all pass offline

## 6. CI pipeline

- [x] 6.1 Create `.github/workflows/ci.yml` triggering on push and pull_request
- [x] 6.2 Job steps: `uv sync`, `uv run ruff check`, `uv run ruff format --check`, `uv run basedpyright`, `uv run pytest`
- [x] 6.3 Use `astral-sh/setup-uv@v6` action; cache the uv env for speed
- [x] 6.4 Verify the workflow runs green on a push to a branch (or via `act` locally if GitHub is unavailable)

## 7. Optional pre-commit hooks

- [x] 7.1 Create `.pre-commit-config.yaml` with `ruff` (check + format) and `basedpyright` hooks using the local venv
- [x] 7.2 Document `uv run pre-commit install` in AGENTS.md (optional contributor step)

## 8. Documentation

- [x] 8.1 Update `AGENTS.md` Development Commands: document `uv sync`, `uv run ruff check`, `uv run ruff format`, `uv run basedpyright`, `uv run pytest`
- [x] 8.2 Update `AGENTS.md` Testing & QA: replace "no tests exist" with the new suite, fixtures, and how to run them offline
- [x] 8.3 Update `AGENTS.md` Key Directories: add `tests/`, `pyproject.toml`, `pyrightconfig.json`, `.github/workflows/`
- [x] 8.4 Update `AGENTS.md` Code Conventions: note the line-length 120 divergence from HA core (see design D4)
- [x] 8.5 Verify `openspec validate add-dev-tooling-tests` passes

## 9. Final verification

- [x] 9.1 Full local run: `uv sync && uv run ruff check && uv run ruff format --check && uv run basedpyright && uv run pytest` — all green
- [x] 9.2 Confirm no runtime behavior change: diff `custom_components/tapo_p110/*.py` is limited to mechanical/style/annotation edits; entity behavior, coordinator flow, and protocol outputs unchanged
- [x] 9.3 Confirm `manifest.json` `requirements` is unchanged (still `["ecdsa"]`)