# Unified Studio Sandbox and Simplified Web Lifecycle

**Status**: Accepted (Amends [ADR 0034](0034-factory-studio-and-live-preview-workspace.md), [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md), [ADR 0041](0043-factory-studio-grilling-codebase-grounding-and-error-resilience.md), and [ADR 0050](0050-studio-turn-rollback-and-in-place-reversion.md))

To eliminate cognitive friction, false-positive prompt rejections, vestigial ingress complexity, and dual-container lifecycle divergence in Factory Studio and the Factory Testing Console, we decided to:
1. Excise vestigial Cloudflare ingress logic (`cloudflared`, token decryption, port watcher loops) from the factory container entrypoint, relying solely on Modal Application Tunnels (`sandbox.tunnels()[3000].url`) for dev server preview exposure.
2. Retire the fast regex intent guard (`factory/ui/guard.py`), shifting architectural boundaries conversationally to the Grilling Assistant to guide persistence requests toward browser-native storage (`localStorage`, `sessionStorage`, `IndexedDB`) or client mock stores.
3. Universally deprecate `.scratch/` metadata tracking in web interfaces (branch resolution, backend `/api/repos/{repo}/scratch` route, GitHub tree queries, frontend hooks, and Testing Console selectors), establishing GitHub Issues and Milestones as the sole convention for web UI operations.
4. Unify the container lifecycle in Job Registry (`factory/ui/registry/_dispatch.py`): eliminate the fallback that provisions ephemeral factory sandboxes for UI jobs; auto-provision the Unified Studio Sandbox on demand via synchronous `wait_for_serving_sync` and execute the pipeline exclusively via in-sandbox process execution (`sandbox.exec()`).

## Considered Options

- **Retaining Ephemeral Fallback in Job Registry**: Spawning standalone factory containers when preview containers were stopped or absent. Rejected because ephemeral containers lack dev servers, causing live preview drift, requiring duplicate bootstrapping, and maintaining two divergent execution paths in the UI registry.
- **Retaining Regex Guard**: Maintaining rigid regex filters on user prompts. Rejected because regexes frequently triggered false-positive refusals on legitimate questions mentioning storage, databases, or APIs, whereas conversational guidance in the Grilling Assistant achieves architectural alignment without friction.
- **Retaining Dual `.scratch/` Tracking in Web Interfaces**: Querying Git Tree APIs for `.scratch/` tickets in web interfaces alongside GitHub Milestones. Rejected because it consumed excessive GitHub API rate limits, added latency to repository switching, and caused confusion between local filesystem and cloud issue tracking.
- **Retaining Cloudflare Ingress in Factory Entrypoint**: Decrypting Cloudflare credentials and running background port watcher loops in dev preview containers. Rejected because Modal Application Tunnels provide clean, collision-free HTTPS URLs per sandbox without external daemon management.
- **Unified Studio Sandbox with Synchronous Auto-Provisioning & In-Sandbox Execution**: Accepted.

## Consequences

- The terms **Dedicated Preview Sandbox** (marked deprecated and superseded by Unified Studio Sandbox) and **GitHub Issue Tracker** (sole convention for web UI operations) are synchronized in `CONTEXT.md`.
- **Factory Entrypoint Simplification (`shared/factory_entrypoint.sh`)**:
  - Excised Cloudflare token decryption, daemon installation, and `/proc/net/tcp` watcher loop routines.
  - Relies solely on Modal Application Tunnels for port 3000 preview exposure.
  - `tests/test_entrypoint.py` asserts clean dev server startup without Cloudflare secrets or background loops.
- **Conversational Grilling Boundary (`factory/ui/guard.py` & `factory/ui/grill/_inference.py`)**:
  - Retired and deleted `factory/ui/guard.py`.
  - Removed fast intent rejection guard from `factory/ui/routes/studio_chat.py`.
  - Added Rule 4 to Grilling Assistant system instructions defining target apps as client-side TanStack Start applications and steering persistence toward browser storage or mock stores.
- **Deprecation of `.scratch/` in Web Interfaces**:
  - Removed `/api/repos/{repo}/scratch` endpoint from `factory/ui/routes/repos.py`.
  - Excised recursive Git tree inspection for `.scratch/` tickets from `factory/ui/github/_branches.py`.
  - Updated `resolve_active_preview_branch` to resolve via Milestones, Issues, and fallback to `main`.
  - Cleaned frontend API (`api.ts`), React Query hooks (`useStudioQueries.ts`), and Testing Console (`JobConfigPanel.tsx`) to derive available features exclusively from GitHub Milestones.
- **Unified Job Execution (`factory/ui/registry/`)**:
  - Added thread-safe `wait_for_serving_sync` to `PreviewRegistry` in `_preview.py`.
  - Excised `create_factory_sandbox` and `FactorySpawnConfig` imports from `_dispatch.py` and `__init__.py`.
  - Refactored `_run_job_worker` in `_dispatch.py` to auto-provision Unified Studio Sandbox on demand if stopped, waiting for serving status before executing the pipeline via `sandbox.exec()`.
- **Preserved Headless CLI & Interactive Tooling**:
  - Headless batch pipelines (`factory/run.py`, `factory/orchestrator.py`) continue using ephemeral sandboxes via `factory.spawner`.
  - Interactive exploratory sandboxes (`sandbox/main.py`, `shared/startup.sh`) retain Cloudflare Tunnel ingress for SSH and OpenCode tooling.
