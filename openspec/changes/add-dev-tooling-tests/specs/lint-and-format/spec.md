## ADDED Requirements

### Requirement: Ruff lint baseline
The repository MUST configure `ruff` with a rule set aligned to Home Assistant core style and establish a clean lint baseline on the existing source.

#### Scenario: Ruff check passes on existing source
- **WHEN** `ruff check custom_components/tapo_p110/ tests/` is run in the dev environment
- **THEN** it exits 0 with no lint violations on the existing (behavior-preserved) source

#### Scenario: Ruff format check passes
- **WHEN** `ruff format --check custom_components/tapo_p110/ tests/` is run
- **THEN** it exits 0 indicating no formatting changes are required

### Requirement: Ruff config location
The `ruff` configuration MUST live in `pyproject.toml` under `[tool.ruff]` (and sub-tables), not in a separate `ruff.toml` or `.ruff.toml`, to keep tooling config centralized.

#### Scenario: Single config source
- **WHEN** the repository is inspected
- **THEN** no `ruff.toml` or `.ruff.toml` file exists
- **AND** ruff configuration is present in `pyproject.toml`

### Requirement: Behavior-preserving lint fixes
Any source edits made to satisfy `ruff` MUST NOT change observable runtime behavior. Edits are limited to mechanical transformations (unused import removal, import sorting, style-only reformatting).

#### Scenario: Lint cleanup does not alter behavior
- **WHEN** the diff of lint-driven source edits is reviewed
- **THEN** every changed line is a mechanical/style transformation with no logic change
- **AND** the integration's entity behavior, coordinator update flow, and protocol client outputs are unchanged