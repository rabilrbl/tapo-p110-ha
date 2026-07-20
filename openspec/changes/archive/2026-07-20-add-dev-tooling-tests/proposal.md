## Why

The integration ships 2341 lines with a vendored SPAKE2+/AES-CCM protocol client and a multi-device subentry lifecycle, but has no lint, type-check, tests, or reproducible dev environment. LSP cannot resolve `homeassistant.*` imports locally (no HA package installed), and a crypto regression in `tpap_client.py` would only surface against a real device. This closes the quality-gate gap to bring the repo from "works on my pi5" to a standard, contributor-friendly HA integration.

## What Changes

- Add `pyproject.toml` (PEP 621) declaring dev dependencies and tool config; no runtime packaging — the integration stays HACS-distributed source.
- Adopt `uv` for the dev environment: pinned Home Assistant version (target floor 2026.7), `ecdsa`, `cryptography`, `passlib`, plus dev deps `pytest`, `pytest-asyncio`, `aiohttp`, `ruff`, `basedpyright`.
- Add `pyrightconfig.json` scoping type-checking to `custom_components/tapo_p110/` and `tests/`, resolving against the pinned HA install. This eliminates the `Import "homeassistant.*" could not be resolved` LSP error as a side effect.
- Add `ruff` config (in `pyproject.toml`) with HA-aligned rules; run via `uv run ruff check` and `uv run ruff format`.
- Add `tests/` with `pytest` + `pytest-asyncio` targeting the highest-risk, offline-testable surfaces:
  - `tpap_client.py`: SPAKE2+ derivation correctness, AES-CCM nonce sequencing, session expiry/re-handshake, `_send_request` 403/decrypt-failure auto-retry, error-code mapping (`-2202`/`-2203` → `TapoAuthError`), `get_all_data` atomic-vs-best-effort semantics, setter preservation re-reads (auto-update, auto-off, power-protection).
  - `coordinator.py`: error-mapping invariants — `TapoAuthError` → `ConfigEntryAuthFailed`, `TapoConnectionError`/unknown → `UpdateFailed`, empty-data → `UpdateFailed`, `client.shutdown()` called on every error path.
- Add `.github/workflows/ci.yml` running `ruff check`, `ruff format --check`, `basedpyright`, and `pytest` on push/PR.
- Add `.pre-commit-config.yaml` for local ruff + pyright hooks (optional, low cost).
- Update `AGENTS.md` Testing & QA and Development Commands sections to reflect the new toolchain.
- Update `.gitignore` to ignore `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.pyright/`, `__pycache__/` (already present).
- **No runtime behavior changes.** No changes to `manifest.json` `requirements`, no changes to integration logic. Tests and tooling only.

## Capabilities

### New Capabilities
- `dev-environment`: Reproducible local dev environment via `uv` with pinned Home Assistant and runtime deps; `pyproject.toml` declaring dev dependencies; `pyrightconfig.json` enabling LSP/type-check resolution of `homeassistant.*`.
- `lint-and-format`: `ruff` configuration and run targets (`ruff check`, `ruff format`) aligned with Home Assistant core style; clean baseline on existing source.
- `static-type-check`: `basedpyright` scoped to `custom_components/tapo_p110/` and `tests/`; resolves the unresolved-import LSP error; establishes a type-clean baseline (baseline may allow narrow ignores for HA dynamic APIs).
- `unit-tests`: `pytest` + `pytest-asyncio` suite covering `tpap_client.py` (protocol/crypto/setters, HTTP mocked) and `coordinator.py` error-mapping invariants; offline, deterministic, no real device required.
- `ci-pipeline`: GitHub Actions workflow running lint, format-check, type-check, and tests on push and pull request.

### Modified Capabilities
<!-- None. No existing specs; this change introduces the above capabilities. -->

## Impact

- **Affected files (new):** `pyproject.toml`, `pyrightconfig.json`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `tests/conftest.py`, `tests/test_tpap_client.py`, `tests/test_coordinator.py`, `tests/requirements_test.txt` (or deps in `pyproject.toml`).
- **Affected files (modified):** `AGENTS.md` (Testing & QA, Development Commands, Key Directories), `.gitignore` (venv/caches).
- **Affected files (unchanged at runtime):** all `custom_components/tapo_p110/*.py` — no behavior change. If `ruff`/`basedpyright` surface real issues, those are fixed as part of this change but must not alter observable behavior.
- **Private APIs touched:** none. `tpap_client.py` internals (`_send_request`, `_ensure_session`, SPAKE2+ helpers) are accessed in tests via the module's public surface where possible, or via direct import of private helpers (acceptable in same-package tests).
- **Rollback:** remove the new files and revert `AGENTS.md`/`.gitignore`; integration runtime is untouched.
- **Risk:** low. Tooling is additive. The only behavioral risk is if lint/type-check fixes touch integration code — constrained to behavior-preserving edits.