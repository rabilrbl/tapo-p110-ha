## Context

The integration is behaviorally mature (hub/subentry model, `ConfigEntryAuthFailed`/`UpdateFailed` mapping, reauth-via-exception, diagnostics, zeroconf discovery, reconfigure) but has zero quality gates: no `pyproject.toml`, no lint, no type-check, no tests, no CI. The local dev environment has no `homeassistant` package installed, so Pyright reports `Import "homeassistant.*" could not be resolved` for every file — a purely environmental gap that blocks editor assistance and any future type-checking.

Highest-risk code is `tpap_client.py` (513 lines): vendored SPAKE2+ P-256 key exchange, AES-128-CCM encrypted channel, sequence-numbered nonces, session expiry, auto-retry on 403/decrypt-failure, and setter methods that re-read device config to preserve unchanged fields. A regression here only surfaces against a real device unless unit tests exist. The coordinator's error-mapping contract (`TapoAuthError`→`ConfigEntryAuthFailed`, transient→`UpdateFailed`, `shutdown()` on every error path) is the other load-bearing invariant.

## Goals / Non-Goals

**Goals:**
- Eliminate the unresolved-import LSP error by providing a pinned, reproducible `homeassistant` install for tooling.
- Establish `ruff` (lint + format) and `basedpyright` (type-check) baselines that pass clean on existing source (behavior-preserving fixes only).
- Add offline, deterministic unit tests for `tpap_client.py` (protocol/crypto/setters with mocked HTTP) and `coordinator.py` (error-mapping invariants).
- Add a GitHub Actions CI workflow running all four gates on push/PR.
- Document the toolchain in `AGENTS.md` so contributors reproduce the environment.

**Non-Goals:**
- No runtime behavior changes to the integration. `manifest.json` `requirements` unchanged.
- No packaging for PyPI; distribution stays HACS source-only.
- No platform/entity registration tests (high fixture cost, low signal for a custom integration).
- No end-to-end tests against a real device or real HA instance.
- No coverage threshold enforcement; tests target invariants, not line coverage.
- No migration of `tpap_client.py` to async; it stays synchronous, wrapped by `async_add_executor_job`.

## Decisions

### D1: `uv` over plain `pip` + venv
**Choice:** `uv` for environment + dependency management, via `pyproject.toml` (PEP 621) with a `[tool.uv]` dev-dependency group.
**Why:** `uv` is already installed locally (0.11.2), resolves and installs in seconds, and produces a lockfile-free reproducible env when given a pinned HA version. It removes the "which Python, which pip" variance across contributors.
**Alternatives:** `pip` + `venv` + `requirements_test.txt` — works but slower, no single command, and doesn't give `uv run` ergonomics for ruff/pyright/pytest. `poetry`/`hatch` — heavier than needed for a non-packaged integration.

### D2: Pin Home Assistant to the target floor, not latest
**Choice:** Pin `homeassistant==2026.7.*` (the documented minimum) in the dev dependency group.
**Why:** The dev env must reflect the *lowest* HA version users run, so type-checks catch APIs unavailable at the floor. `__init__.py` already uses subentries and `ConfigEntryAuthFailed`, which are present in 2026.7. Pinning latest would hide floor-compatibility regressions.
**Alternatives:** Pin latest (dev ergonomics, but misses floor breakage). Pin a matrix (correct but doubles CI time; defer until the single pin proves insufficient).

### D3: `basedpyright` over Microsoft `pyright`
**Choice:** `basedpyright` for type-checking.
**Why:** Stricter defaults, better HA compatibility (core HA uses pyright; basedpyright is a superset that surfaces more real issues), and actively maintained. Reduces silent `Any` leakage in the vendored crypto code.
**Alternatives:** Microsoft `pyright` — fewer catches. `mypy` — different plugin model, HA core standardizes on pyright.

### D4: `ruff` config in `pyproject.toml`, HA-aligned rule set
**Choice:** `ruff` with a rule set aligned to HA core's `pyproject.toml` (E/F/I/UP/B/SIM/ASYNC/RUF families), line length 120 (HA core uses 100; the existing code already exceeds 100 in places — use 120 to avoid a noisy first-pass that would force behavior-adjacent reformatting).
**Why:** One config file, millisecond runs, replaces `flake8`+`isort`+`pyupgrade`. Catches real bugs in best-effort `.get()` chains and mutable defaults.
**Alternatives:** HA core's exact 100-column config — would require reformatting nearly every line, mixing style churn into a tooling change. Defer to a separate formatting change if desired.
**Caveat:** Line length 120 is a deliberate divergence from HA core documented here; revisit if the integration is ever upstreamed.

### D5: Test `tpap_client.py` via `urllib.request.urlopen` monkeypatching
**Choice:** Mock `urllib.request.urlopen` (and `urllib.error.HTTPError`) at the module level to inject canned HTTP responses; assert on request payloads, sequence numbering, retry behavior, and crypto outputs.
**Why:** `_post_json` and `_send_request` both go through `urllib.request.urlopen` — the single I/O seam. Mocking there keeps tests offline and deterministic while exercising the real crypto/nonce/retry logic. No HTTP server fixture needed.
**Alternatives:** `responses`/`httpx` mock layer — unnecessary indirection; `urllib` isn't `requests`. A local mock HTTP server — heavier, flakier, and the protocol is binary `application/octet-stream` not JSON-over-HTTP for the data channel.

### D6: Test SPAKE2+ derivation against a recorded vector, not a live handshake
**Choice:** Capture one real handshake's intermediate values (client keypair, server public, derived `w`/`h`, `L`/`Z`/`V`, confirmation keys, session key, base nonce) as a static test fixture. Tests assert the derivation functions reproduce these from the recorded inputs.
**Why:** SPAKE2+ correctness can't be asserted without a reference vector; generating one requires a real device once. The vector locks the crypto implementation against silent drift. The vector contains no credentials (only ephemeral handshake artifacts).
**Alternatives:** Implement a second SPAKE2+ in the test to cross-check — doubles the crypto surface under test. Skip crypto tests — leaves the highest-risk code unguarded.

### D7: Coordinator tests use HA's `homeassistant.test` aiohttp harness minimally
**Choice:** Use `pytest-asyncio` with a lightweight HA fixture (the `homeassistant.test` package provides `HomeAssistant` construction helpers). Construct a `TapoP110DataCoordinator` with a mock `TapoP110Client` whose `get_all_data` raises each error class; assert the coordinator raises `ConfigEntryAuthFailed`/`UpdateFailed` and calls `client.shutdown`.
**Why:** The error-mapping contract is the load-bearing invariant; it must be defended. Full HA platform fixtures (entity setup, config flow) are out of scope (Non-Goals). A mock client avoids device I/O entirely.
**Alternatives:** Full `aioclientmock` + config-flow tests — high fixture cost, low marginal signal for this change. Test only `tpap_client` — leaves the coordinator contract undefended.

### D8: CI runs all four gates, matrix on the single pinned HA version
**Choice:** One GitHub Actions job: `uv sync` → `ruff check` → `ruff format --check` → `basedpyright` → `pytest`. No version matrix initially.
**Why:** Single pin matches D2. A matrix adds runtime without catching more until a second supported floor exists. Keep CI fast (<60s target).
**Alternatives:** Matrix across Python 3.13/3.14 — HA pins its own Python; the integration runs under HA's Python, so matrixing Python here tests the tooling, not the integration. Defer.

### D9: `pyrightconfig.json` scoped to integration + tests, `reportMissingImports` on
**Choice:** `pyrightconfig.json` with `include = ["custom_components/tapo_p110", "tests"]`, `reportMissingImports = true`, and the pinned HA on the path (via `uv` venv).
**Why:** Scoped checking avoids flagging unrelated files; `reportMissingImports` on is what makes the `homeassistant.*` resolution fail *loudly if the env is missing* and pass once `uv sync` has run — directly solving the reported LSP error.
**Alternatives:** `# type: ignore` per import — hides the real gap; anti-pattern.

## Risks / Trade-offs

- **Risk: `ruff`/`basedpyright` surface real issues in existing code.** Mitigation: fixes are constrained to behavior-preserving edits (e.g., unused import removal, `Optional`→`| None`); any change that could alter behavior is flagged in the PR for review, not auto-applied. The baseline run is captured before fixes so the diff is auditable.
- **Risk: Pinned HA 2026.7 may lack an API the code already uses.** Mitigation: the code runs on the user's pi5 today, so 2026.7 is known-sufficient; the pin validates this assumption rather than introducing it. If the pin reveals a gap, bump the floor in `manifest.json` (out of scope here — flagged).
- **Risk: SPAKE2+ test vector goes stale if TP-Link changes the protocol.** Mitigation: the vector tests *current* behavior; a protocol change requires updating the client *and* the vector together — which is the correct workflow. The vector is a regression guard, not a forward-compatibility promise.
- **Risk: `passlib` conditional import (`passwd_id==1`, md5_crypt) is unmaintained and may fail on newer Python.** Mitigation: pin `passlib` in dev deps so the import path is at least importable; add a test that the `passwd_id==1` branch is importable. If no real device uses `passwd_id==1`, flag for removal in a follow-up (out of scope).
- **Trade-off: Line length 120 diverges from HA core's 100.** Accepted to keep this change purely additive (no mass reformatting). Documented in D4; revisit on upstreaming.
- **Trade-off: No coverage threshold.** Tests target invariants, not coverage %; a coverage gate would incentivize low-value fixture tests. Accepted.
- **Trade-off: No Python-version matrix in CI.** HA bundles its Python; matrixing here tests tooling, not the integration. Accepted; revisit if the integration ever ships standalone.