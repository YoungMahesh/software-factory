# Unified Studio Sandbox for Live Preview and In-Sandbox Agent Execution

**Status**: Accepted (Amends ADR 0034 and ADR 0037)

To eliminate container fragmentation and provide instant Hot Module Replacement (HMR) during conversational frontend development in Factory Studio, we decided to unify preview serving and agent assembly line execution into a single **Unified Studio Sandbox** per repository, driving in-sandbox modifications via `modal.Sandbox.exec`.

## Considered Options

- **Dual Sandboxes (Dedicated Preview Sandbox + Ephemeral Factory Sandbox)**: Retaining the existing pattern where launching a preview creates a Dedicated Preview Sandbox, while each chat prompt creates a new Software Factory Sandbox that pushes to GitHub. Rejected because the preview sandbox sits stale on old code, missing live HMR feedback as the agent works, and spawning new sandboxes per prompt incurs 30–60 seconds of container initialization overhead.
- **Dual Sandboxes with Periodic Branch Pulling**: Spawning separate factory sandboxes to commit changes, while the preview sandbox runs a periodic `git pull` loop. Rejected because it introduces git synchronization lag, potential merge conflicts, and completely misses real-time HMR as files are written.
- **Unified Studio Sandbox with In-Sandbox `sandbox.exec`**: Provisioning a single persistent Modal sandbox per repository that runs a supervised background Vite dev server on port 3000 with a Modal Application Tunnel, and executing the multi-agent assembly line directly in `/root/<repo>` via `modal.Sandbox.exec()`. Accepted because Vite HMR instantly reloads the preview iframe as the Coder Agent writes files, drastically reduces prompt turnaround time, and preserves the full quality gate and Git accumulation model.

## Consequences

- The canonical term **Unified Studio Sandbox** is recorded in `CONTEXT.md`.
- **Single Container Lifecycle**: Factory Studio maintains at most one active sandbox per repository. The preview dev server runs on port 3000 via a Modal Application Tunnel (`https://<sandbox-id>-3000.modal.host`).
- **In-Sandbox Process Execution**: When a user submits a chat prompt, `JobRegistry` invokes the Assembly Line Pipeline (`pipeline.ts`) inside the running sandbox using `sandbox.exec()`, streaming stdout/stderr back into the `Agent Event Stream`.
- **Environment & Credential Isolation**: Decrypted credentials (`GH_TOKEN`, `OPENCODE_API_KEY`) are written during container boot to `/root/.factory.env` (mode `0600`). Every `sandbox.exec()` invocation sources this file to authenticate Git operations and LLM inference without passing credentials through host memory.
- **Supervised Dev Server**: The container entrypoint runs `pnpm dev --port 3000 --host 0.0.0.0` in an auto-restart loop so transient syntax errors during agent editing do not crash the container.
- **Test-Focused Deterministic Verification**: In Studio mode, the Deterministic Verifier runs tests (`pnpm test`) and typechecking (`pnpm typecheck`), avoiding full `pnpm build` output cache collisions with the active Vite server.
- **In-Place Branch Transitions**: When switching or creating a feature branch, `sandbox.exec` checks out `factory/<feature>` in place within `/root/<repo>`; Vite automatically detects the changed files and hot-reloads the preview.
- **Explicit Disconnect & Resumption**: When a sandbox times out after 30 minutes of inactivity, the UI presents an explicit "Sandbox Disconnected" dialog. Clicking "Reconnect Environment" retains the conversation history, provisions a fresh sandbox tracking `origin/factory/<feature>`, and resumes serving.
- **Preview Resynchronization**: LivePreview includes a manual reload button, and the backend emits an SSE reload signal upon assembly line completion to recover from any HMR desynchronization.
