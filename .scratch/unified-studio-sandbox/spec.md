# Spec: Unified Studio Sandbox for In-Sandbox Live Preview and Agent Execution

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

In Factory Studio, developers currently experience a disconnected two-sandbox workflow. When a developer clicks "Preview App", a Dedicated Preview Sandbox is provisioned running only the development server (`pnpm dev`) on port 3000 behind a Modal Application Tunnel. However, when the developer subsequently chats with that application in Factory Studio to request changes, the system does not modify code within that running preview sandbox. Instead, it dispatches an entirely new, separate Software Factory Sandbox that executes the multi-agent assembly line in isolation.

As a result:
1. The active preview sandbox continues to serve stale, unmodified code while the assembly line executes in the other sandbox.
2. The developer loses the immediate visual feedback of Hot Module Replacement (HMR) while the agent is editing files.
3. Spawning a brand-new container for every chat prompt incurs substantial provisioning latency (30–60 seconds of container boot, cloning, and package installation overhead per turn).
4. Multiple uncoordinated sandboxes compete for cloud resources and create confusing disconnects between the conversational chat interface and the live application preview.

## Solution

Unify preview serving and agent assembly line execution into a single **Unified Studio Sandbox** per repository in Factory Studio:

1. **Single Container Execution Model**: Maintain at most one active sandbox per repository in Factory Studio. The sandbox starts the background development server immediately on port 3000 with a unique Modal Application Tunnel URL (`https://<sandbox-id>-3000.modal.host`).
2. **In-Sandbox Process Execution via `sandbox.exec()`**: When the developer submits a prompt in Factory Studio, the backend executes the Assembly Line Pipeline directly inside the already-running container using Modal's `sandbox.exec()` API against the live repository working directory, streaming logs into the existing Agent Event Stream.
3. **Live Hot Module Replacement (HMR)**: As the Coder Agent modifies frontend files in the live workspace, the development server's file watcher immediately detects the edits and pushes hot updates to the preview iframe in real time.
4. **Resilient Dev Server Supervision**: Run the development server inside an automated auto-restart loop in the container startup entrypoint so that transient syntax errors introduced during agent code generation do not crash the container.
5. **Container-Local Credential Isolation**: Decrypt repository and LLM provider credentials at container boot into a protected, container-local environment file (`/root/.factory.env`, mode 0600) so subsequent `sandbox.exec()` invocations source credentials locally without passing secrets through host memory.
6. **Non-Colliding Deterministic Verification**: In Studio mode, configure the Deterministic Verifier stage to run unit tests and typechecking (`pnpm test` and `pnpm typecheck`), avoiding full build cache collisions with the concurrently active development server.
7. **In-Place Branch Transitions**: When switching or creating feature branches, the in-sandbox execution transitions branches dynamically within the working directory (`git checkout -B factory/<feature>`), allowing the dev server to detect file updates instantly without container recreation.
8. **Explicit Disconnect & Reconnection**: When a sandbox reaches its idle timeout (30 minutes), display an explicit "Sandbox Disconnected" dialog in the UI. Clicking "Reconnect Environment" retains full chat conversation history and provisions a fresh Unified Studio Sandbox directly tracked to the active remote feature branch.
9. **Iframe Resynchronization**: Provide a manual refresh control in the preview header and emit an SSE reload signal upon assembly line completion to recover from any client-side HMR desynchronization.

## User Stories

1. As a developer using Factory Studio, I want my chat prompts to modify code in the exact same sandbox currently running my live preview, so that I can see changes reflected immediately without container fragmentation.
2. As a developer watching the agent build my application, I want Vite's Hot Module Replacement to reload components in the live preview iframe in real time as the Coder Agent writes code, so that I get instant visual feedback.
3. As a developer interacting with Factory Studio, I want prompt submission to begin executing immediately without waiting 30–60 seconds for a brand-new container to clone the repo and reinstall dependencies, so that iteration cycles are fast.
4. As a developer sending a prompt before clicking "Preview App", I want Factory Studio to automatically provision the Unified Studio Sandbox and launch the preview in one unified flow, so that I don't have to perform redundant setup clicks.
5. As a developer waiting for an agent turn to complete, I want the prompt input to be temporarily locked, so that I cannot inadvertently send overlapping prompts that cause Git index locks or file conflicts.
6. As a developer whose code synthesis temporarily produces invalid syntax during an intermediate edit step, I want the in-sandbox dev server to automatically restart rather than crashing the container, so that transient syntax errors self-heal.
7. As a security-conscious engineer, I want repository and LLM credentials to be decrypted once into a protected container-local file (`/root/.factory.env`) rather than transmitted from host memory on each `sandbox.exec()` call, so that secret lifecycles remain contained within the sandbox.
8. As a developer running tests during verification, I want the Deterministic Verifier to run unit tests and typechecks without triggering a full build that competes for Vite's cache directories, so that verification runs reliably alongside the dev server.
9. As a developer initiating a new feature in a freshly scaffolded repository, I want the sandbox to transition in place from `main` to `factory/<feature>`, so that branch creation is instantaneous.
10. As a developer stepping away from Factory Studio until the sandbox times out, I want to see an explicit "Sandbox Disconnected" dialog when I return, so that I am clearly aware of the connection state.
11. As a developer reconnecting after a timeout, I want to click "Reconnect Environment" and have the container resume on the active feature branch with my conversation history preserved, so that I don't lose my context or previous commits.
12. As a developer inspecting a complex UI change where client-side HMR might miss deep module renames, I want a manual "Refresh" button in the preview toolbar, so that I can force-reload the preview iframe at any time.
13. As a developer reviewing completed changes, I want the backend to emit an SSE preview refresh signal when the assembly line finishes, so that the live preview iframe is guaranteed to display the final verified state.
14. As an operator monitoring Factory Studio, I want the web control plane to manage at most one active sandbox per repository, so that server resources and Modal concurrency limits are efficiently conserved.
15. As a developer reviewing changes, I want every completed assembly line turn to continue pushing verified commits to `factory/<feature>` on GitHub, so that Git auditability and Draft Feature PR delivery are preserved.

## Implementation Decisions

- **Single Container Lifecycle per Repository**:
  The web control plane maintains a single active sandbox reference per repository. The preview dev server runs on port 3000 via a Modal Application Tunnel (`https://<sandbox-id>-3000.modal.host`), and all subsequent prompt jobs target this container instance.

- **Decoupled Job and Preview Registry Coordination**:
  The preview management tier owns the container lifecycle and tunnel URL for each repository. When a chat prompt creates a work item, the job execution harness queries the preview registry for the running sandbox and invokes `sandbox.exec()` directly on it, streaming chunks into the Agent Event Stream.

- **In-Sandbox Process Execution Interface**:
  Assembly line execution inside the container uses Modal's `sandbox.exec()` API to run the TypeScript pipeline harness. Execution is wrapped in a shell script invocation that sources `/root/.factory.env`, ensuring access to Git authentication and LLM inference keys.

- **Automated Dev Server Process Supervision**:
  The container entrypoint executes `pnpm dev --port 3000 --host 0.0.0.0` inside a resilient shell restart loop. If the development process terminates due to syntax or bundler errors, it sleeps briefly and restarts automatically.

- **In-Place Branch Checkout**:
  The in-sandbox pipeline creates or switches to the target branch (`factory/<feature>`) in place within the working directory. The file watcher on the running development server picks up the changes across branch transitions without requiring a server reboot.

- **Test-Focused Deterministic Verification in Studio Mode**:
  When executing inside the Unified Studio Sandbox, the Deterministic Verifier stage runs `pnpm test` and `pnpm typecheck` (`tsc --noEmit`), avoiding full production builds that write to conflicting output directories while Vite is actively serving.

- **Protected Container-Local Environment Bootstrap**:
  During sandbox initialization, decrypted environment variables (`GH_TOKEN`, `OPENCODE_API_KEY`) are written to `/root/.factory.env` with restricted file permissions (`0600`). Raw secret files are purged immediately after decryption per standard SOPS bootstrap rules.

- **Explicit Disconnect UI State & Reconnection Workflow**:
  The frontend monitors preview status over Server-Sent Events. If the container terminates or reaches its idle timeout, the UI transitions to a disconnected state displaying a reconnection dialog. Submitting prompts is disabled until the user clicks "Reconnect Environment", which provisions a fresh Unified Studio Sandbox tracked to `origin/factory/<feature>`.

- **Iframe Resynchronization via Toolbar Action & SSE Signal**:
  The LivePreview header provides a refresh action button that reloads the embedded iframe DOM. Additionally, the backend emits a `preview_refresh` event over the SSE telemetry stream upon assembly line completion, prompting the frontend to reload the iframe.

## Testing Decisions

- **What makes a good test**:
  Tests must exercise public module interfaces and externally observable behaviors (HTTP status codes, SSE event formats, process execution arguments, environment file creation, and container state transitions) rather than private loop counters or mock timing internals.

- **Highest Testing Seam (HTTP API & Registry Seam)**:
  The primary seam for automated testing is the FastAPI REST and SSE interface backed by the registry layer:
  1. Submitting a prompt via `/api/studio/prompt` when a sandbox is already active calls `sandbox.exec()` on the existing container rather than creating a new sandbox.
  2. Submitting a prompt when no sandbox is active triggers unified sandbox provisioning and subsequent in-container execution.
  3. Preview endpoints report unified sandbox state and broadcast log deltas and refresh events over SSE.
  4. Termination and idle timeout events transition the repository state to `STOPPED`/`DISCONNECTED`, and the reconnect action provisions a replacement sandbox on the target branch.

- **Secondary Seams**:
  - Container Entrypoint Script Seam: Unit/integration tests verifying that the startup script writes `/root/.factory.env` with mode `0600` and configures the dev server supervisor loop.
  - Frontend Component Seam: Unit tests verifying that `StudioView` locks input while a job is running, displays the disconnect modal when the sandbox stops, and triggers iframe reload on the refresh action and SSE refresh event.

- **Prior art**:
  - `tests/test_preview.py`: Existing Dedicated Preview Sandbox argument inspection, tunnel retrieval, and registry test patterns.
  - `tests/test_ui.py`: Existing FastAPI prompt dispatch and job lifecycle test patterns.
  - `factory/ui/frontend/src/views/StudioView.test.tsx`: Existing Studio split-pane UI and preview component tests.

## Out of Scope

- Disabling Git commits or Feature PR generation (every completed assembly line turn continues to accumulate commits on `factory/<feature>`).
- Rewriting the TypeScript assembly line pipeline agents (Planner, Coder, Verifier, Reviewer retain their existing prompts and tools).
- Multi-user collaborative simultaneous editing on the same sandbox (one unified sandbox per repository is strictly single-tenant).
- Supporting non-Vite development servers in Factory Studio (TanStack Start with Vite remains the canonical stack).

## Further Notes

- Implements the decisions established in ADR 0038 (`docs/adr/0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md`).
- Adheres strictly to the domain glossary in `CONTEXT.md` (Unified Studio Sandbox, Factory Studio, Modal Application Tunnel).
