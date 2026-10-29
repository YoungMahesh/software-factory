# Retire Factory Studio and In-Container Assembly Line to Focus on Modal Sandboxes

**Status**: Accepted (Amends [ADR 0016](0016-unified-sandbox-runner.md), [ADR 0032](0032-factory-testing-console.md), [ADR 0034](0034-factory-studio-and-live-preview-workspace.md), [ADR 0036](0036-vite-spa-for-factory-studio.md), [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md), [ADR 0052](0052-unified-studio-sandbox-and-simplified-web-lifecycle.md), and [ADR 0059](0059-consolidate-testing-console-into-factory-studio-and-canonicalize-api-routes.md))

## Context
Previously, the repository maintained a large full-stack application layer comprising **Factory Studio** (FastAPI backend and Vite React SPA), the **Factory Orchestrator and Spawner**, and an in-container TypeScript multi-agent assembly line (**Pi Agent Harness** executing Planner, Coder, Verifier, and Reviewer stages). Over time, this application layer grew to account for >85% of the codebase (~48,000 physical lines of code and extensive Node/Python dependencies) while providing limited utility compared to native developer and agent interfaces already integrated directly into the sandboxes (SSH, T3 Code Server, OpenCode, and Antigravity).

## Decision
We decided to retire and excise the entire Factory Studio web interface, the host factory spawner/orchestrator, and the in-container Pi Agent assembly line, refocusing the repository strictly on its core competency: the **Modal Cloud Sandbox Platform**.

1. **Excise Application Layer**:
   - Delete `factory/` (FastAPI backend, Vite React SPA, spawner, and orchestrator).
   - Delete `sandbox/factory/` (in-container TypeScript Pi Agent harness and assembly line).
   - Delete `shared/factory_entrypoint.sh` and `shared/target_template_skills/`.
   - Delete web/pipeline test suites (`tests/test_ui/`, `tests/test_ui_events/`, `tests/test_grill/`, `tests/test_preview/`, and factory runner tests).
   - Delete factory-specific live scripts and Node configuration (`skills-lock.json`).

2. **Preserve and Reinforce the Core Sandbox Platform**:
   - **Unified Sandbox Runner** (`sandbox/main.py`, `sandbox/cli.py`, `sandbox/config.py`): The canonical CLI entrypoint for launching Standard Container and Linux VM Sandboxes on Modal with SSH, Cloudflare Tunnel ingress, and filesystem snapshots.
   - **Sandbox Management** (`scripts/manage_sandboxes.py` and `scripts/list-sandboxes.py`): Command-line tools to inspect, filter, and terminate active Modal sandboxes.
   - **Tooling Setup** (`scripts/setup.sh`): Ephemeral and local credential decryption wizard.
   - **Shared Infrastructure** (`shared/image.py`, `shared/startup.sh`, `shared/ssh-key.pub`, `shared/aliases.bash`, `shared/gitconfig*`): Base image definitions, SOPS decryption bootstrap, and user configuration.
   - **Core Test Suite** (`tests/test_sandbox/` and `tests/test_manage_sandboxes.py`): Comprehensive test coverage verifying CLI parsing, volume staging, runtime invariants, and sandbox management.

3. **Dependency and Runtime Simplification**:
   - Purge `fastapi`, `uvicorn`, `jinja2`, `httpx`, and `libsql-experimental` from `requirements.txt`, leaving only `modal`, `qrcode`, and `pytest`.
   - Eliminate Node/pnpm build tooling and lockfiles from the repository root.

## Consequences
- The repository is completely decoupled from web servers, database persistence, and Node runtimes on the host, transforming into a lightweight, 100% pure Python and shell repository.
- Codebase volume is reduced by ~85%, eliminating the cognitive burden and maintenance overhead of custom web UI components, Vite HMR proxying, and build artifact freshness ratchets.
- Developers interact with cloud sandboxes via industry-standard interfaces: SSH / VS Code Remote, T3 Code Server (`--t3`), OpenCode (`--opencode`), or Antigravity (`--agy`), backed by Modal's native snapshotting and container virtualization.
- `CONTEXT.md` is pruned to remove deprecated web studio and autonomous assembly line terms.
