# Packaging, Developer Experience (DX), and Open-Source Governance

**Status**: Accepted (Amends [ADR 0027](0027-universal-file-line-budget-and-test-suite-decomposition.md), the retirement of Factory Studio, and [ADR 0054](0054-codebase-de-hardcoding-and-parameterization.md))

We package the repository as a standard installable Python package via `pyproject.toml`, expose the `modal-sandbox` console CLI entrypoint, bundle critical runtime container assets and static assets, purge retired legacy database configuration, establish community governance and vulnerability disclosure standards, and restructure project onboarding around a zero-config standalone quickstart.

## Context

Prior to this work, running sandboxes required invoking raw script paths (`python sandbox/main.py`) within a virtual environment created manually from `requirements.txt`. The repository lacked standard Python packaging metadata (`pyproject.toml`), explicit package markers (`__init__.py`) in `sandbox/` and `shared/`, and installation manifests for container assets.

Additionally, dead configuration keys from the retired Factory Studio (`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`, retired in the retirement of Factory Studio) were still present in `.env.example` and forwarded by `sandbox/launcher.py`. Finally, to prepare for external developers and community adoption, the project required community health documentation (contributing rules, code of conduct, security reporting policy, issue templates) and a simplified quickstart experience that did not require SOPS decryption or GitHub tokens.

## Decisions

1. **Standard Python Packaging (`pyproject.toml`)**:
   - Adopt a PEP 621-compliant `pyproject.toml` using `setuptools` build backend.
   - Define package metadata under `[project]` with name `modal-sandboxes` (version `0.1.0`), Python requirements `>=3.11`, and core dependencies (`modal>=1.6.1`, `qrcode>=7.4.2`, `fastapi>=0.100.0`, `pydantic>=2.0.0`, `httpx>=0.27.0`).
   - Define optional test dependencies under `[project.optional-dependencies] dev = ["pytest>=8.0.0"]`.
   - Update `requirements.txt` to `-e .` (with `pytest>=8.0.0`) for backwards compatibility.

2. **Unified CLI Console Entrypoint (`modal-sandbox`)**:
   - Register console script `modal-sandbox = "sandbox.main:main"` in `pyproject.toml`.
   - Enable developers to run `modal-sandbox` directly from any terminal once installed (`pip install -e .`), while preserving direct script execution (`python sandbox/main.py`).

3. **Package Initialization and Asset Bundling**:
   - Add explicit `__init__.py` markers in `sandbox/` and `shared/` to establish them as recognized Python packages.
   - Configure `[tool.setuptools.package-data]` to bundle runtime assets, including shell scripts (`shared/startup.sh`, `shared/t3-wrapper.sh`), SSH keys (`shared/ssh-key.pub`), tool configurations (`shared/*.json`), and Web UI assets (`sandbox/static/*`).

4. **Scrub Retired Turso Database Configuration**:
   - Remove `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from `.env.example`.
   - Remove `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from `secret_keys` in `sandbox/launcher.py`.

5. **Open-Source Governance & Community Files**:
   - **`CONTRIBUTING.md`**: Document local virtual environment setup (`pip install -e ".[dev]"`), test execution (`pytest`), Universal File Line Budget rules (<= 500 lines per file, ADR 0027), and PR conventions.
   - **`CODE_OF_CONDUCT.md`**: Adopt Contributor Covenant v2.1.
   - **`SECURITY.md`**: Establish private vulnerability reporting instructions directing security researchers to GitHub Private Vulnerability Reporting.
   - **Issue & PR Templates**: Add `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`, and `.github/PULL_REQUEST_TEMPLATE.md`.
   - Defer license file and automated CI workflow per maintainer preference.

6. **README Overhaul and Zero-Config Quickstart**:
   - Position a Standalone Quickstart (`modal setup`, `modal-sandbox --name my-first-sandbox`) as the primary onboarding path, requiring zero encryption keys or GitHub tokens.
   - Structure advanced features into transparent credential tiers (Standalone, Target Repositories, Ingress, AI Agent tooling, Mobile toolchain).
   - Add a Mermaid architecture diagram illustrating control surfaces, Modal Cloud infrastructure, sandbox runtimes, and background agent tooling.

7. **Domain Model & Glossary Alignment**:
   - Register canonical terms in `GLOSSARY.md` for **Modal Sandbox CLI** and **Standalone Quickstart**.

## Consequences

- External developers can install and run `modal-sandbox` in one command without manual script path resolution.
- Onboarding is accessible to any user with a basic Modal account; credentials for private repos or external tools are strictly opt-in.
- Retired database variables no longer clutter documentation or pass through container environment variables.
- All Python files and test suites adhere strictly to the universal <= 500 lines physical budget (ADR 0027 / AGENTS.md).
