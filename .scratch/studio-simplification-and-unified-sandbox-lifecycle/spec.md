# Spec: Studio Simplification and Unified Sandbox Lifecycle

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

The Software Factory web interfaces (Factory Studio and Factory Testing Console) have accumulated vestigial mechanisms, redundant container lifecycles, and brittle prompt guards that degrade developer experience, add container startup latency, and introduce architectural drift:

1. **Vestigial Cloudflare Ingress in Factory Sandboxes**: Although Modal Application Tunnels (`https://<sandbox-id>-3000.modal.host`) were established as the collision-free standard for application preview, the factory container entrypoint still retains complex routines for decrypting Cloudflare credentials, registering system services, and running a continuous port-watcher loop parsing `/proc/net/tcp`. In dev preview mode, this logic executes unconditionally despite Cloudflare being disabled, creating container startup overhead, polluting container logs, and risking port conflicts with singleton Cloudflare tunnel configurations.
2. **Brittle Regex Intent Guarding**: Studio user prompts are currently intercepted by a rigid regular expression guard that checks for keywords like "database", "backend", "redis", or "postgres". This heuristic produces frequent false positives—rejecting legitimate frontend prompts (such as storing data in browser `localStorage` instead of an external database)—and bypasses the Grilling Assistant, which is already equipped with prompt archetype classification and codebase grounding capable of steering architectural scope conversationally.
3. **Legacy Local Markdown Issue Tracker Paths in Web Interfaces**: Following the adoption of GitHub Issues and Milestones for target projects in the Test Organization, target repositories no longer maintain `.scratch/` task trees. Yet preview branch resolution and repository query endpoints continue making redundant recursive Git Tree API calls to search for `.scratch/` directories, adding network latency to Studio interactions and maintaining multiple conflicting sources of truth across the web UI.
4. **Dual Container Lifecycle in Job Registry**: The background job worker maintains two divergent execution paths: delegating in-sandbox execution via `sandbox.exec()` if a Unified Studio Sandbox is currently active, or falling back to spawning an ephemeral factory sandbox if preview is not active. This creates divergent execution environments where code verification, tool configurations, and dev server behavior differ between live preview interactions and batch dispatch.

## Solution

Simplify Factory Studio and the testing web interfaces by standardizing on a single container lifecycle, retiring brittle regex guards in favor of conversational grilling boundary steering, removing legacy `.scratch/` tracker paths from all web interfaces, and excising vestigial Cloudflare ingress from the factory container entrypoint:

1. **Complete Excision of Cloudflare Ingress from Factory Sandboxes**:
   - Remove Cloudflare token decryption, system service installation, and the background port watcher script from the factory container entrypoint.
   - Rely solely on Modal Application Tunnels for application preview and Vite Hot Module Replacement (HMR).
   - Preserve Cloudflare Ingress in the standard sandbox startup script exclusively for developer interactive sessions (OpenCode, SSH, T3).

2. **Retirement of Regex Intent Guard & Conversational Boundary Steering**:
   - Remove the blocking regex intent guard from the Studio prompt ingestion pipeline.
   - Instruct the Grilling Assistant in its system instructions that target projects are strictly client-side TanStack Start applications.
   - Guide developers conversationally during interview rounds when persistence or backend requests are detected, steering requirements toward browser-based storage (`localStorage`, `sessionStorage`, `IndexedDB`) or client mock stores.
   - Allow downstream quality gates (Pre-flight Guard and Planner Agent) to evaluate architectural feasibility for direct dispatch workflows.

3. **Universal Deprecation of `.scratch/` in Web Interfaces**:
   - Eliminate `.scratch/` metadata discovery from preview branch resolution so active branches are resolved exclusively from GitHub Milestones, GitHub Issues, or default trunk (`main`).
   - Remove the repository `.scratch/` inspection endpoint from the backend API.
   - Remove unused scratch query hooks and scratch selection tabs from both Factory Studio and Factory Testing Console, standardizing all UI workflows onto GitHub Issues & Milestones.

4. **Unified Container Lifecycle in Job Registry**:
   - Eliminate the fallback path that spawns ephemeral factory sandboxes in the UI job registry.
   - Auto-provision the Unified Studio Sandbox on demand if a job is launched when no sandbox is currently serving, awaiting readiness before executing the Assembly Line Pipeline via in-sandbox process execution (`sandbox.exec`).
   - Preserve the ephemeral factory spawner strictly for headless CLI runs and serverless orchestrator batch workflows.

5. **Domain Architecture and Glossary Synchronization**:
   - Record Architectural Decision Record 0052 documenting the unification of the container lifecycle, the retirement of regex intent filtering, the excision of factory Cloudflare ingress, and the UI deprecation of `.scratch/` tracking.
   - Update the domain glossary in `CONTEXT.md` to formally deprecate Dedicated Preview Sandboxes in favor of Unified Studio Sandboxes.

## User Stories

1. As a frontend developer submitting a prompt in Factory Studio, I want my prompt to be evaluated by the Grilling Assistant rather than blocked by hardcoded regexes, so that phrasing like "save user preferences in localStorage instead of a database" is never rejected as an invalid database request.
2. As a frontend developer asking for persistent storage, I want the Grilling Assistant to explain that the target app is a client-side TanStack Start application, so that I can choose appropriate browser storage solutions like `localStorage` or `IndexedDB` during the interview.
3. As a developer launching a preview sandbox, I want the container to initialize without running Cloudflare setup or port watcher loops, so that container startup time is reduced and container logs remain clean.
4. As a developer running parallel jobs, I want preview environments to use isolated Modal Application Tunnels exclusively, so that my previews never collide with singleton Cloudflare ingress tunnels.
5. As an interactive developer launching an exploratory sandbox via `sandbox/main.py`, I want Cloudflare Tunnel ingress to remain fully functional, so that my OpenCode and SSH remote tunnels continue working as expected.
6. As a Studio user selecting an active repository, I want the active preview branch to resolve instantly without recursive Git Tree API queries for `.scratch/` folders, so that repository switching is fast and responsive.
7. As a developer navigating Factory Studio, I want GitHub Issues and Milestones to be the single source of truth for work items, so that I do not encounter confusing references to missing `.scratch/` folders.
8. As a developer using the Factory Testing Console, I want the job configuration panel to list GitHub Milestones and Issues without presenting redundant `.scratch/` feature selectors, so that testing configurations reflect the canonical issue tracker model.
9. As a developer dispatching an assembly line job when the preview container is stopped or timed out, I want the registry to automatically provision the Unified Studio Sandbox, so that my job always runs in an HMR-enabled environment.
10. As a developer dispatching a job from either Studio or the Testing Console, I want all code modifications to run via in-sandbox process execution inside the Unified Studio Sandbox, so that live preview reflects changes immediately without environment divergence.
11. As a developer dispatching batch pipelines via the CLI Dispatcher or serverless Factory Orchestrator, I want headless ephemeral sandboxes to remain supported, so that automated batch jobs run efficiently without lingering dev servers.
12. As an AI agent or engineer reading domain documentation, I want `CONTEXT.md` to clearly indicate that Dedicated Preview Sandboxes are superseded by Unified Studio Sandboxes, so that I do not design features around obsolete container topologies.
13. As an engineer reviewing architectural history, I want an ADR documenting the rationale for retiring regex guards and dual container lifecycles, so that future contributors understand why these constraints were simplified.
14. As a developer whose preview server encounters an unhandled runtime error, I want the supervisor to keep the Unified Studio Sandbox running, so that subsequent agent jobs can still attach via `sandbox.exec()`.
15. As a developer dispatching an issue directly without grilling, I want the Pre-flight Guard to validate repository prerequisites before agent execution begins, so that architectural boundaries are enforced even when conversational grilling is bypassed.
16. As a frontend developer reviewing candidate components in Studio, I want the Grilling Assistant's interview questions to be grounded in existing repository component code, so that recommendations target actual component files instead of inventing unnecessary route hierarchies.
17. As a developer testing web API contracts, I want the backend API to return consistent error structures when a repository cannot be found or provisioned, so that client error handling remains predictable.
18. As a developer monitoring job logs in real time, I want the log stream to indicate whether the job is delegating to an existing warm sandbox or provisioning a fresh Unified Studio Sandbox, so that container bootstrapping progress is transparent.
19. As a developer viewing chat history after an interview round, I want the assistant's recommended answers to be cleanly selectable as prompt responses, so that I can rapidly confirm the implementation plan.
20. As a developer reviewing pull requests generated by the assembly line, I want the commits to accumulate cleanly on the feature branch, so that the diff can be reviewed and merged directly via In-Studio Merge Controls.

## Implementation Decisions

- **Container Ingress Module Simplification**:
  - Excise Cloudflare secret decryption, daemon installation, and `/proc/net/tcp` watcher routines from the factory entrypoint script.
  - Rely exclusively on Modal Application Tunnels for port 3000 exposure in all factory and studio preview containers.
  - Retain Cloudflare ingress configuration in the general sandbox startup script for developer interactive tooling.

- **Studio Prompt Evaluation & Grilling Interface**:
  - Remove the fast intent classification guard from the Studio prompt ingestion pipeline.
  - Update the Grilling Assistant system instruction builder to incorporate the client-side TanStack Start boundary rule, steering data storage requests toward browser-native persistence options.
  - Retire the intent guard module and clean up legacy regex patterns and refusal formatting helpers.

- **Issue Tracking & Repository Inspection Interfaces**:
  - Update preview branch resolution logic to query GitHub Milestones, GitHub Issues, and fallback to `main`, removing the fallback query for `.scratch/` feature metadata.
  - Remove the `.scratch/` repository inspection endpoint from the web route registry.
  - Update the GitHub client module to eliminate recursive Git tree inspection for `.scratch/` tickets.
  - Remove scratch queries from frontend API clients and hooks.
  - Refactor the Testing Console job configuration panel to operate exclusively with GitHub Milestones and Issues.

- **Job Registry Execution Lifecycle**:
  - Add synchronous wait-for-serving capabilities to the preview registry to support thread-safe container readiness checks from background job workers.
  - In the job registry worker, detect whether an active preview sandbox exists for the target repository; if absent, automatically invoke preview launching and wait for serving before dispatching in-sandbox execution.
  - Remove all fallback branches that provision ephemeral factory sandboxes from the job registry worker, ensuring all UI-initiated executions use in-sandbox process execution.
  - Remove factory spawner imports from the UI registry package, maintaining factory spawner routines strictly for headless CLI and orchestrator callers.

- **Documentation & Architectural Records**:
  - Create ADR 0052 detailing the context, options, decisions, and consequences of excising vestigial Cloudflare logic, retiring regex intent guards, deprecating `.scratch/` tracking in web interfaces, and unifying registry job execution onto the Unified Studio Sandbox.
  - Update the language and glossary section in `CONTEXT.md`, marking Dedicated Preview Sandbox as deprecated and superseded by Unified Studio Sandbox, and establishing GitHub Issue Tracker as the sole convention for web UI operations.

## Testing Decisions

- **High Seam Testing**:
  - Test external behavior at the highest applicable architectural seam: HTTP route endpoints for web interactions, container startup script execution for entrypoint behavior, and registry worker orchestration for job lifecycle.
  - Avoid testing internal regex matches or private helper implementations.
- **Entrypoint Container Seam**:
  - Assert that executing the factory entrypoint in dev preview mode starts the dev server and exports the necessary Vite allowed hosts without invoking Cloudflare binaries or spawning watcher loops.
  - Prior art: existing entrypoint tests in `tests/test_entrypoint.py`.
- **Studio Chat Ingestion Seam**:
  - Assert that prompts mentioning database or backend terminology are accepted for processing rather than refused with intent errors.
  - Assert that system instructions passed to the Grilling Assistant include the client-side TanStack Start architectural constraints.
  - Prior art: conversational grilling and studio chat tests in `tests/test_ui.py`.
- **Branch Resolution & Repository API Seam**:
  - Assert that preview branch resolution returns milestone or issue branches without executing Git Tree API calls.
  - Assert that the Testing Console renders milestone and issue options cleanly without attempting to query `.scratch/` metadata.
  - Prior art: branch resolution and repository tests in `tests/test_ui.py` and `tests/test_preview.py`.
- **Job Registry Execution Seam**:
  - Assert that starting a job without an active preview sandbox automatically launches the Unified Studio Sandbox and executes via `sandbox.exec()`.
  - Assert that the job registry worker never calls the ephemeral factory sandbox spawner.
  - Prior art: job execution and delegation tests in `tests/test_preview.py`.

## Out of Scope

- Modifying the general sandbox startup script (`shared/startup.sh`) or altering Cloudflare Tunnel ingress for `sandbox/main.py`.
- Altering the core Assembly Line Pipeline stages (Planner, Coder, Verifier, Reviewer) executed inside the sandbox.
- Retiring `.scratch/` from the Software Factory hub's own internal development tracking (`software-factory/.scratch/`).
- Modifying the CLI Dispatcher (`factory/run.py`) or headless serverless Factory Orchestrator (`factory/orchestrator.py`).

## Further Notes

- All modified production files (`.py`, `.ts`, `.tsx`, `.js`) must adhere strictly to the repository line budget of <= 500 lines per ADR 0051.
- Removing `.scratch/` metadata inspection eliminates unnecessary GitHub API rate limit consumption on target repositories during Studio navigation.
