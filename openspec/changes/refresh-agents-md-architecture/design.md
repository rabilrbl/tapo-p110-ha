## Context

`AGENTS.md` is the repo's sole architecture reference and the context file auto-loaded for every agent session. It was written against v1.0.0 (single config entry per plug, `requirements: []`, blanket `UpdateFailed` on any error, 27 entities per device). The code is now v2.2.2: hub+subentry model, `ConfigEntryAuthFailed`/`UpdateFailed` split, `async_migrate_entry`, `_async_subentry_listener`, `async_setup_subentry` platform handlers, `requirements: ["ecdsa"]`. The drift is not subtle — every architecture section is wrong. This is a documentation-only change; the "system" being specified is the documentation's accuracy contract.

## Goals / Non-Goals

**Goals:**
- Make every architecture-level claim in `AGENTS.md` verifiable against the current code on a spot-check.
- Document the hub+subentry model, per-subentry coordinator storage on `runtime_data`, the subentry reconciliation listener, and the v1→v2 migration accurately.
- Document the current coordinator error-mapping contract (`TapoAuthError`→`ConfigEntryAuthFailed`, transient→`UpdateFailed`, `shutdown()` on every error path, empty-data→`UpdateFailed` without shutdown).
- Cross-reference the `add-dev-tooling-tests` change for tooling sections rather than duplicating or pre-empting them.

**Non-Goals:**
- No code changes of any kind.
- No tooling documentation (owned by `add-dev-tooling-tests`).
- No README changes (README is user-facing install/setup; architecture internals belong in AGENTS.md).
- No new doc files (no `CONTRIBUTING.md`, `ARCHITECTURE.md`); single source of truth stays `AGENTS.md`.
- No backfilling the full entity-by-entity platform table beyond what already exists — only correcting entries that are now wrong (e.g., subentry unique-id convention, coordinator count).

## Decisions

### D1: Rewrite in place, preserve section structure
**Choice:** Keep the existing `AGENTS.md` section headings (Project Overview, Architecture & Data Flow, Key Directories, Development Commands, Code Conventions, Important Files, Runtime/Tooling, Testing & QA, Quirks) and rewrite their contents to match the code.
**Why:** The structure is sound and is what agents/contributors expect; churning the headings adds review noise without value. Only the content is wrong.
**Alternatives:** Restructure into a new layout — no benefit, breaks any external references and muscle memory.

### D2: Cross-reference, don't duplicate, the tooling change
**Choice:** In Key Directories and Testing & QA, state the current (pre-tooling) reality and add a one-line note that `add-dev-tooling-tests` adds `tests/`, `pyproject.toml`, `pyrightconfig.json`, `.github/workflows/` and the test suite.
**Why:** This change and the tooling change may land in either order. Duplicating the tooling content here risks immediate drift; cross-referencing keeps each change self-contained and lets whichever lands second update the shared sections without conflict.
**Alternatives:** Fully write the tooling sections now — risks drift and scope-creep into the other change. Leave tooling sections stale silently — the current "no tests exist" text is accurate until the other change lands, so this is acceptable, but a cross-reference is clearer.

### D3: Verify the subentry unique-id convention from code before writing it
**Choice:** During implementation, read the platform files' `async_setup_subentry` to confirm the exact unique-id format (the proposal hedges on `f"{entry_id}:{subentry_id}_{key}"` vs. another form), then document whatever the code actually does.
**Why:** Documenting a guessed convention re-introduces the exact drift this change is fixing. The unique-id format is load-bearing for entity identity across reloads.
**Alternatives:** Guess — defeats the purpose.

### D4: Document the migration as a clean-start, not data migration
**Choice:** Describe `async_migrate_entry` truthfully: v1 entries are removed (not transformed), users re-add plugs as subentries; the v2→v2.1 device-registry re-key is explicitly NOT migrated (orphaned rows cleaned via UI once).
**Why:** This is what the code does (`_safe_remove_entry` + the docstring at `__init__.py:196-210`). Documenting a data migration that doesn't exist would be a new inaccuracy.
**Alternatives:** Omit migration — leaves a gap agents will fill with wrong assumptions.

### D5: Update the data-flow ASCII diagram
**Choice:** Replace the single-coordinator diagram with a hub→N-subentries→N-coordinators diagram showing `runtime_data` storage and the listener reconciliation path.
**Why:** The diagram is the most-scanned part of AGENTS.md; a wrong diagram propagates wrong mental models faster than prose.
**Alternatives:** Drop the diagram — loses the fastest on-ramp for new readers.

## Risks / Trade-offs

- **Risk: Residual inaccuracy if code changes between landing and a future code change.** Mitigation: this is inherent to any living doc; landing it now is strictly better than leaving it wrong. Treat AGENTS.md as code-adjacent and update alongside future changes.
- **Risk: The subentry unique-id convention is documented wrong.** Mitigation: D3 — verify from code during implementation; the tasks file makes this an explicit step.
- **Trade-off: Cross-referencing the tooling change leaves a temporary seam.** Accepted per D2; cleaner than duplicating and drifting.
- **Trade-off: No automated check that AGENTS.md stays in sync.** Out of scope; a future change could add a doc-lint or a test that parses AGENTS.md claims, but that's larger than this change.