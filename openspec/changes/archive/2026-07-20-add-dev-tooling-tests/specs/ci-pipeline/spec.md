## ADDED Requirements

### Requirement: CI workflow runs all quality gates
The repository MUST have a GitHub Actions workflow that runs lint, format-check, type-check, and unit tests on every push and pull request.

#### Scenario: CI runs on push and PR
- **WHEN** a commit is pushed or a pull request is opened
- **THEN** the CI workflow triggers and runs all four gates: `ruff check`, `ruff format --check`, `basedpyright`, and `pytest`

#### Scenario: CI fails on any gate failure
- **WHEN** any of the four gates exits non-zero
- **THEN** the CI workflow job fails and the failing gate's output is visible in the run log

### Requirement: CI uses the pinned dev environment
The CI workflow MUST install dependencies via the same `uv sync` command used locally, using the pinned Home Assistant version from `pyproject.toml`, so CI validates the same environment contributors use.

#### Scenario: CI reproduces local env
- **WHEN** the CI workflow runs
- **THEN** it uses `uv sync` to create the environment
- **AND** the installed `homeassistant` version matches the pinned floor declared in `pyproject.toml`

### Requirement: Fast CI feedback
The CI workflow MUST complete in under 90 seconds on a cache-hit run to keep feedback tight.
#### Scenario: CI runtime target
- **WHEN** the CI workflow runs with dependencies cached
- **THEN** the full job (install + lint + format + type-check + tests) completes in under 90 seconds