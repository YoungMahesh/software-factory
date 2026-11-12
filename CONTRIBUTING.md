# Contributing to Modal Sandboxes

Thank you for your interest in contributing to Modal Sandboxes! We welcome contributions to improve the developer experience, expand agent tooling support, and streamline cloud execution environments on Modal.

---

## 1. Development Setup

### Prerequisites

- Python 3.11 or 3.12
- [Modal CLI](https://modal.com/docs/guide) installed and authenticated (`modal setup`)
- Git

### Initializing the Workspace

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/<your-org>/modal-sandboxes.git
cd modal-sandboxes

python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode with development dependencies:
pip install -e ".[dev]"
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

- **Strict Limit**: Every production Python file and automated test file (`.py`) must **not exceed 500 physical lines** (`wc -l`).
- **Enforcement**: Validated automatically by `tests/test_standards.py`.
- **Decomposition Pattern**: When a module approaches 500 lines, decompose it into a deep directory module with internal private helpers behind a concise public interface (`__init__.py`). Do not introduce shallow or pass-through abstractions.
- **Exemptions**: Shell scripts (`.sh`), JSON fixtures, and environment templates are exempt.

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
pytest tests/test_standards.py

# Run the complete hermetic test suite:
pytest
```

All tests must pass cleanly without regressions.

---

## 5. Live Sandbox Verification (Optional)

If your changes alter container startup routines, base image definition, or SSH connectivity, verify against the minimal testing baseline:

```bash
# Verify against the canonical test fixture repository:
python sandbox/main.py -r live-test1 --testing

# Or test a standalone clean sandbox:
modal-sandbox --name test-verify-box
```

> [!IMPORTANT]
> Ensure any live test sandboxes are terminated immediately after verification to prevent unnecessary cloud resource consumption:
> ```bash
> python scripts/manage_sandboxes.py
> ```

---

## 6. Pull Request Guidelines

1. **Branching**: Create feature branches from `main` using descriptive names (e.g., `feat/add-provider-x`, `fix/ssh-config-parsing`).
2. **Commit Messages**: Use conventional commits (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
3. **Architecture Decisions**: If introducing architectural changes, new dependencies, or irreversible trade-offs, record an Architecture Decision Record under `docs/adr/` following the existing format.
4. **Documentation**: Keep `readme.md`, `GLOSSARY.md`, and inline docstrings updated alongside code modifications.
