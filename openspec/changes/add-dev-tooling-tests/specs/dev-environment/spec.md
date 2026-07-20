## ADDED Requirements

### Requirement: Reproducible dev environment
The repository MUST provide a reproducible local development environment that installs a pinned Home Assistant version and all runtime + dev dependencies via a single command, so that LSP and type-checkers can resolve `homeassistant.*` imports.

#### Scenario: Fresh contributor sets up the dev env
- **WHEN** a contributor runs the documented one-command environment setup (`uv sync`)
- **THEN** a virtual environment is created with the pinned Home Assistant version (target floor 2026.7), `ecdsa`, `cryptography`, `passlib`, and all dev dependencies (`pytest`, `pytest-asyncio`, `aiohttp`, `ruff`, `basedpyright`) installed
- **AND** `python -c "import homeassistant"` succeeds in that environment

#### Scenario: LSP resolves Home Assistant imports
- **WHEN** the dev environment is active and the editor's Python language server is pointed at the project venv
- **THEN** `homeassistant.*` imports in `custom_components/tapo_p110/` resolve without "could not be resolved" errors

#### Scenario: pyproject declares dev dependencies
- **WHEN** the repository is inspected
- **THEN** a `pyproject.toml` exists declaring the project metadata and a dev-dependency group containing the pinned Home Assistant version and all tooling
- **AND** the file contains NO runtime packaging config (no `[build-system]` producing a distributable wheel; the integration remains HACS source-distributed)

### Requirement: Pinned Home Assistant floor
The dev environment MUST pin Home Assistant to the integration's documented minimum supported version (2026.7), not the latest, so that type-checking catches APIs unavailable at the support floor.

#### Scenario: Dev env uses the floor version
- **WHEN** the dev environment is installed
- **THEN** the installed `homeassistant` version matches the `2026.7.*` release line
- **AND** any API used by the integration that is unavailable in 2026.7 is surfaced as a type-check or import error