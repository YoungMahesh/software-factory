# In-Studio Code and Diff Viewer with In-Sandbox Interactive Terminal

**Status**: Accepted

To empower developers to inspect generated project files, review side-by-side git diffs before merging, and troubleshoot sandbox builds or execute ad-hoc commands without leaving Factory Studio, we decided to:
1. Introduce the **In-Studio Code Viewer** and **Pre-Merge Diff Viewer** accessible via a top-level tab switcher on the right canvas header (`[Live Preview] [Files & Code] [Git Diff]`) inside `StudioPreviewPane.tsx` and `StudioView.tsx`.
2. Implement a hybrid backend file retrieval pipeline for `GET /api/repos/{repo}/tree` and `GET /api/repos/{repo}/files?path=...` that queries the Unified Studio Sandbox via `sandbox.exec()` when running (capturing uncommitted agent edits), falling back to the GitHub Git Database API when the container is idle or stopped, with server-side ignore filtering (`node_modules`, `.git`, `.venv`, `dist`, build caches) and a 500KB inspection ceiling.
3. Provide a dual-scope Pre-Merge Diff Viewer supporting toggles between "Working Tree Changes" (`git diff HEAD`) and "Branch Changes" (`origin/main...HEAD`), with toggleable unified hunk and split two-column views.
4. Embed an **In-Sandbox Interactive Terminal** powered by xterm.js as a dedicated tab in `ActivityDrawer.tsx`, decomposed into `InteractiveTerminalTab.tsx` to maintain the Universal File Line Budget (<= 500 lines).
5. Connect the interactive terminal over a full-duplex WebSocket (`/api/repos/{repo}/terminal/ws`) wired directly to Modal's `sandbox.exec(pty=True)` API, anchoring in `/root/{repo}` with an interactive login bash shell, terminating the container process immediately on WebSocket disconnect, and allowing concurrent subshells alongside active assembly line jobs with a warning indicator.

## Considered Options

- **Ephemeral Container-Only vs Hybrid File Retrieval**: Container-only required auto-provisioning stopped sandboxes just to browse code files; hybrid retrieval provides instantaneous browsing via the GitHub Git Database API when the sandbox is stopped, seamlessly switching to live container inspection when the sandbox is active.
- **WebSocket vs Server-Sent Events (SSE) + REST POST for Terminal**: SSE is strictly unidirectional; sending keystrokes, escape sequences, and resize signals over discrete HTTP POST calls introduces unacceptable typing latency, buffering glitches, and PTY echo artifacts. Full-duplex WebSockets provide native PTY streaming with xterm.js.
- **Blocking vs Concurrent Terminal Subshells**: Blocking terminal interaction during autonomous agent runs prevented developers from inspecting container state, logs, or server health (`curl localhost:3000`) during long runs. Because Modal's container runtime supports concurrent process execution, running an independent subshell with a prominent warning badge enables non-destructive diagnosis without lock contention.

## Consequences

- The canonical terms **In-Studio Code Viewer**, **Pre-Merge Diff Viewer**, and **In-Sandbox Interactive Terminal** are recorded in `CONTEXT.md`.
- **Universal File Line Budget Compliance**:
  - `ActivityDrawer.tsx` decomposes the terminal tab into `factory/ui/frontend/src/components/activity-drawer/InteractiveTerminalTab.tsx`.
  - Backend endpoints are organized into dedicated route modules (`factory/ui/routes/files.py` and `factory/ui/routes/terminal.py`) to prevent route files from exceeding 500 lines.
- **Frontend Dependencies**:
  - `factory/ui/frontend` adds `xterm` and `@xterm/addon-fit` for terminal emulation and dynamic canvas resizing.
