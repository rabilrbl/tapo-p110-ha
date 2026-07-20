## ADDED Requirements

### Requirement: Basedpyright type-check baseline
The repository MUST configure `basedpyright` scoped to `custom_components/tapo_p110/` and `tests/`, with `reportMissingImports` enabled, and establish a type-clean baseline on existing source.

#### Scenario: Pyright resolves all imports
- **WHEN** `basedpyright` runs in the dev environment (after `uv sync`)
- **THEN** no "Import could not be resolved" errors are reported for `homeassistant.*`, `cryptography`, `ecdsa`, or `passlib` imports

#### Scenario: Type-check passes on existing source
- **WHEN** `basedpyright` runs against `custom_components/tapo_p110/` and `tests/`
- **THEN** it exits with no errors, or with only narrowly-scoped `# type: ignore` suppressions on HA dynamic APIs that are documented in the design

### Requirement: Pyrightconfig scope
A `pyrightconfig.json` MUST exist at the repository root scoping `include` to `custom_components/tapo_p110` and `tests`, with `reportMissingImports: true`.

#### Scenario: Config scopes checking
- **WHEN** `pyrightconfig.json` is inspected
- **THEN** `include` lists exactly `custom_components/tapo_p110` and `tests`
- **AND** `reportMissingImports` is `true`

### Requirement: Behavior-preserving type fixes
Any source edits made to satisfy `basedpyright` MUST NOT change observable runtime behavior. Type annotations are additive; logic changes are out of scope.

#### Scenario: Type cleanup does not alter behavior
- **WHEN** the diff of type-driven source edits is reviewed
- **THEN** every changed line is an annotation addition or mechanical type fix with no logic change