# Contributing to Software Factory

Thank you for your interest in contributing to Software Factory! We welcome contributions to improve the developer experience, expand agent tooling support, and streamline cloud execution environments on Modal.

---

## 1. Development Setup

### Prerequisites

- Python 3.11+
- [Modal CLI](https://modal.com/docs/guide) installed and authenticated (`modal setup`)
- Git

### Initializing the Workspace

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/sFactory0/software-factory.git
cd software-factory

python3 -m venv .venv
source .venv/bin/activate

# Install the package, test tools, and documentation dependencies:
python -m pip install -r requirements.txt
```

Verify your installation:

```bash
modal-sandbox --help
```

---

## 2. Configuration (`.env`)

For local runs or deploying the hosted control plane, copy the environment template:

```bash
cp .env.example .env
```

Configure the environment variables relevant to your workflow (e.g., `GH_TOKEN`, `GH_ORG_NAME`, `WEB_UI_USERNAME`, `WEB_UI_PASSWORD`). Standalone sandboxes without a target repository require only an authenticated Modal client (`modal setup`).

---

## 3. Code Standards & Architectural Rules

To maintain long-term maintainability and readability, every contributor and agent must uphold the following codebase standards:

### Universal File Line Budget (ADR 0027 / AGENTS.md)

- **Strict Limit**: Every production code file and executable Python test file in `sandboxes/` must **not exceed 500 physical lines** (`wc -l`).
- **Enforcement**: Validated automatically by `sandboxes/tests/test_standards.py`.
- **Decomposition Pattern**: When a module approaches 500 lines, decompose it into a deep directory module with internal private helpers behind a concise public interface (`__init__.py`). Do not introduce shallow or pass-through abstractions.
- **Exemptions**: Shell scripts (`.sh`), external static fixtures, environment templates, and `resource-plane/` are exempt.

### Deep Module Boundaries

Modules should have small, simple interfaces that hide complex internal mechanisms (e.g. `sandbox.launcher.launch_sandbox` handles image resolution, credential binding, network configuration, and volume mounts behind a clean dataclass interface).

### Hermetic Unit Tests

- Automated test suites must run without requiring live external network access, paid cloud services, or real credentials.
- Mock all Modal cloud calls (`modal.Sandbox.create`, `modal.App.spawn`) in unit tests.

---

## 4. Testing Your Changes

Before submitting a Pull Request, run the automated test suite locally:

```bash
# Run standards check and line budget ratchet:
pytest sandboxes/tests/test_standards.py

# Run the complete hermetic test suite:
pytest

# Build and validate documentation:
zensical build --strict
```

The manually dispatched docs CI workflow installs the documentation extras and runs the site build and reference contract checks, so missing Zensical cannot silently skip the build there.

All tests must pass cleanly without regressions.

---

## 5. Live Sandbox Verification (Optional)

If your changes alter container startup routines, base image definition, or SSH connectivity, verify against the minimal testing baseline:

```bash
# Verify against the canonical test fixture repository:
modal-sandbox --testing --repo software-factory

# Or test a standalone clean sandbox:
modal-sandbox --name test-verify-box
```

> [!IMPORTANT]
> Ensure any live test sandboxes are terminated immediately after verification to prevent unnecessary cloud resource consumption:
> ```bash
> python sandboxes/scripts/manage_sandboxes.py --all-apps --terminate <sandbox-id>
> ```

---

## 6. Pull Request Guidelines

1. **Branching**: Create feature branches from `main` using descriptive names (e.g., `feat/add-provider-x`, `fix/ssh-config-parsing`).
2. **Commit Messages**: Use conventional commits (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
3. **Architecture Decisions**: If introducing architectural changes, new dependencies, or irreversible trade-offs, record an Architecture Decision Record under `docs/adr/` following the existing format.
4. **Documentation**: Keep `readme.md`, `GLOSSARY.md`, and inline docstrings updated alongside code modifications.

## Subsystem development

Install JavaScript dependencies with `pnpm install` from the monorepo root.

- **Sandbox Dashboard (`dashboard/`)**: Run local development with `pnpm --dir dashboard dev` (requires `SANDBOX_CONTROL_PLANE_URL`, `WEB_UI_USERNAME`, and `WEB_UI_PASSWORD`). Validate with `pnpm --dir dashboard test`, `pnpm --dir dashboard typecheck`, and `pnpm --dir dashboard build`. See `dashboard/README.md`.
- **Resource Plane (`resource-plane/`)**: Run local development with `pnpm --dir resource-plane dev`; configure its web-local environment and Docker access as described in `resource-plane/README.md`. Run its tests with `pnpm --dir resource-plane test`.

`app-template/` is a blueprint excluded from this workspace. Generate a temporary app with `create-app` to run its app commands. The root Python requirements include documentation tools; runtime-only installations can still use `python -m pip install -e .`.

Keep current guides aligned with CLI parsers, environment resolution, MCP registrations, and startup behavior. Historical ADRs describe past decisions and should retain their context; current guides should link to later amendments when behavior has changed.
