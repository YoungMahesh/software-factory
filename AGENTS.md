# Software Factory

Toolkit for provisioning, managing, and snapshotting isolated cloud execution environments on Modal, paired with stateful persistence infrastructure (PostgreSQL 16, SeaweedFS S3, and control console).

Software Factory is partitioned into cohesive subsystems:
- **`sandboxes/` (Execution Plane)**: Python Modal sandbox engine, CLI (`modal-sandbox`, `create-app`, `create-db`, `create-s3`, `deploy-infra`), hosted FastAPI control plane (`sandboxes/sandbox/function.py`), test suites, and agent harnesses. Consult the `modal` skill (`.agents/skills/modal/SKILL.md`) when writing or modifying Modal SDK code.
- **`dashboard/` (Sandbox Dashboard)**: Next.js 16 / React 19 web dashboard and same-origin Basic-Auth BFF proxy (`dashboard/apps/web`) deployed to `/opt/sandbox-dashboard` via `modal-sandbox infra dashboard` and backed by the Modal Control Plane API. See [`dashboard/README.md`](dashboard/README.md).
- **`resource-plane/` (Resource Plane)**: TypeScript/React 19 Next.js 16 console, PostgreSQL 16, SeaweedFS S3, and Model Context Protocol (MCP) server. See [`resource-plane/AGENTS.md`](resource-plane/AGENTS.md) for Resource Plane conventions.
- **`app-template/` (App Template)**: Canonical Next.js 16 + optional Expo React Native starter blueprint materialized by `create-app` (excluded from root `pnpm-workspace.yaml`, with allowlisted skills tracked in `app-template/skills.json`).

## Agent skills

### Issue tracker

GitHub issues on `sFactory0/software-factory` (using `gh` CLI). See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

Canonical five-role triage vocabulary. See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context layout (`GLOSSARY.md` and `docs/adr/` at repo root). See [`docs/agents/domain.md`](docs/agents/domain.md).

## Code & Verification standards

### Verification

- **Automated tests**: Run `pytest` before finalizing changes. All tests and line budgets must pass cleanly.
- **Sandbox live verification**: Target `${GH_ORG_NAME}/software-factory` with `modal-sandbox --testing --repo software-factory` or `sandboxes/scripts/test_live_sandbox.py`. Terminate test sandboxes immediately after verification.

### Universal file line budget and ratchet

- **Limit**: All production code files and executable automated test files (`.py`) in `sandboxes/` must not exceed 500 physical lines (`wc -l`), verified by `sandboxes/tests/test_standards.py`.
- **Exemptions**: Shell scripts (`.sh`), external static fixture data files (e.g. raw JSON fixtures, plain text data files, and environment templates), and `resource-plane/` are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py`), adhering to deep module principles. Test suites approaching or exceeding 500 lines must be decomposed into modular directory packages or subsystem test modules. Do not create shallow pass-through modules.
