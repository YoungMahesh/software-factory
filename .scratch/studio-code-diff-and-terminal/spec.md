# Spec: In-Studio Code and Diff Viewer with In-Sandbox Interactive Terminal

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When building and testing web applications in Factory Studio, developers currently experience two significant visibility and interaction gaps:

1. **Blindness to Generated Code and Pre-Merge Diffs**: Developers are restricted to observing either the rendered Live Preview iframe or raw streaming console logs. To inspect generated project files (such as route definitions, component trees, or configuration manifests) or to review a complete side-by-side Git diff before triggering the In-Studio Merge Control, developers must abandon Factory Studio and navigate to the GitHub web interface. This context switching disrupts focus and obscures what changes autonomous agents actually introduced.
2. **Passive Telemetry Without Container Intervention**: When a container build fails, dependencies have peer conflicts, or a developer wants to inspect live container network services (e.g. executing `curl localhost:3000` or checking environment variables), they can only observe passive stdout logs. There is no mechanism to run ad-hoc bash commands or troubleshoot inside the Unified Studio Sandbox without opening external SSH tunnels or local terminal sessions.

## Solution

Introduce two integrated developer productivity surfaces in Factory Studio:

1. **In-Studio Code Viewer & Pre-Merge Diff Viewer**:
   - A top-level tab switcher on the right canvas header (`[Live Preview] [Files & Code] [Git Diff]`) providing direct access to the target repository's file tree, source code viewer, and Git diff comparisons.
   - A hybrid retrieval backend that inspects live files directly within the Unified Studio Sandbox when running (surfacing uncommitted or in-memory agent edits) and falls back cleanly to the GitHub Git Database API when the container is idle or stopped.
   - A Pre-Merge Diff Viewer supporting a dual-scope toggle between "Working Tree Changes" (uncommitted edits inside the sandbox) and "Branch Changes" (accumulated feature branch commits against the main trunk), toggleable between unified hunk diffs and two-column split side-by-side diffs.
2. **In-Sandbox Interactive Terminal**:
   - A dedicated "Interactive Terminal" tab in the Activity Drawer powered by xterm.js.
   - A full-duplex WebSocket connection bridging the browser terminal directly to an interactive pseudo-terminal (`pty=True`) in the Unified Studio Sandbox.
   - Automatic execution in the target repository root directory with an interactive login bash shell, immediate process teardown upon disconnect, and non-blocking concurrency alongside active Assembly Line Pipeline jobs with a prominent warning badge.

## User Stories

1. As a developer using Factory Studio, I want a tab switcher in the right canvas header so that I can switch between Live Preview, Files & Code, and Git Diff without leaving the workspace.
2. As a developer inspecting a generated project, I want to browse a hierarchical file tree of the target repository so that I can easily locate and review generated route components and configuration files.
3. As a developer navigating the file tree, I want standard build artifacts and dependency folders (such as `node_modules`, `.git`, `.venv`, and `dist`) to be filtered out automatically so that the file tree remains uncluttered.
4. As a developer clicking a file in the tree, I want to inspect its source code in a syntax-highlighted viewer so that I can verify code structure and logic before running or merging.
5. As a developer viewing files while the Unified Studio Sandbox is actively running, I want the file contents to reflect the live sandbox filesystem so that I can see intermediate, uncommitted edits made by the Coder Agent.
6. As a developer viewing files when the Unified Studio Sandbox is stopped, I want the file viewer to fall back to the remote GitHub repository so that I can inspect the codebase without having to spin up cloud compute.
7. As a developer opening very large files, I want files exceeding 500KB or binary assets to display a clear notice with a download option so that the browser does not freeze.
8. As a developer preparing to merge a feature branch, I want a dedicated Git Diff view in the right canvas so that I can review all code changes before triggering the In-Studio Merge Control.
9. As a developer reviewing diffs, I want a scope toggle between "Working Tree Changes" and "Branch Changes" so that I can distinguish uncommitted working-directory modifications from committed pull request changes.
10. As a developer reviewing multi-file changes, I want an expandable list of modified file cards showing addition and deletion counters so that I can quickly assess the blast radius of changes.
11. As a developer reading complex diffs, I want to toggle between a unified hunk view and a two-column split side-by-side diff view so that I can choose the comparison format best suited to the modification.
12. As a developer troubleshooting a broken build, I want an Interactive Terminal tab in the Activity Drawer so that I can run diagnostic commands directly inside the Unified Studio Sandbox container.
13. As a developer opening the Interactive Terminal, I want an xterm.js terminal instance that automatically resizes to fit the drawer dimensions so that terminal output renders cleanly without line-wrapping glitches.
14. As a developer typing in the terminal, I want full-duplex WebSocket communication so that keystrokes, tab autocompletion, arrow keys, and ANSI escape codes are handled with sub-second latency.
15. As a developer executing commands in the terminal, I want the shell to initialize directly in the target repository directory with an interactive login bash session so that all project tooling and aliases are immediately available.
16. As a developer running terminal commands while an autonomous agent job is active, I want to see a clear warning badge indicating that an Assembly Line Pipeline job is executing so that I avoid conflicting file mutations.
17. As a developer running ad-hoc commands concurrently with an agent, I want my subshell to execute independently without blocking the background dev server or verifier so that I can inspect logs or query endpoints concurrently.
18. As a system operator, I want the backend terminal process to terminate immediately when the WebSocket connection closes so that orphaned bash processes do not leak container memory or CPU.
19. As a developer using keyboard navigation, I want standard terminal shortcuts (such as Ctrl+C, Ctrl+L, and Ctrl+D) to work seamlessly inside the web terminal so that the experience mirrors a native local shell.
20. As a developer reviewing the UI, I want the In-Studio Code Viewer, Pre-Merge Diff Viewer, and Interactive Terminal to adhere strictly to the Cohere Editorial Design System so that the visual experience feels polished and unified.

## Implementation Decisions

- **Canvas View Switcher Architecture**:
  - The right-hand studio canvas container introduces a view mode state supporting three primary views: `preview`, `files`, and `diff`.
  - When `preview` is active, the container displays the standard Live Preview toolbar and application iframe.
  - When `files` is active, the container displays the In-Studio Code Viewer consisting of a collapsible directory tree navigation panel and a code viewing panel.
  - When `diff` is active, the container displays the Pre-Merge Diff Viewer with scope selectors, view mode toggles, and expandable file diff cards.

- **Hybrid File Retrieval Pipeline**:
  - File tree discovery and file content retrieval are managed through dedicated backend endpoints under the repository routes.
  - When the Unified Studio Sandbox is in a running or serving state, the backend executes read-only inspection commands within the container (`find`/`cat`) to expose uncommitted working-tree modifications.
  - When the sandbox is stopped, provisioning, or absent, the backend queries the GitHub Git Database API (recursive tree queries and raw blob fetches) for the active branch reference.
  - Server-side path filtering unconditionally excludes `node_modules`, `.git`, `.venv`, `.next`, `dist`, and common cache directories.
  - File payloads enforce a 500KB size limit; binary files are detected via MIME/null-byte heuristics and return metadata flags rather than raw text.

- **Pre-Merge Diff Viewer Dual-Scope Semantics**:
  - The diff viewer exposes two comparison scopes:
    - *Working Tree Changes*: Compares the active container filesystem against the current branch HEAD commit (`git diff HEAD`), exposing uncommitted changes made during active agent iterations.
    - *Branch Changes*: Compares the target feature branch against the default trunk branch (`git diff origin/main...HEAD` or GitHub comparison API), exposing the complete change set intended for merge.
  - The viewer provides a layout toggle between Unified diff hunks and Split two-column diffs with synchronized line scrolling and syntax token styling.

- **Activity Drawer Decomposition and Universal File Line Budget**:
  - To respect the Universal File Line Budget constraint (<= 500 lines per production file), the Activity Drawer does not embed terminal implementation logic inline.
  - A modular, private child component (`InteractiveTerminalTab`) encapsulates xterm.js instantiation, WebSocket connection handling, resize listeners, and disconnect cleanup.
  - Backend route logic for file inspection and terminal WebSockets are partitioned into separate, focused route modules rather than inflating existing route files.

- **Interactive Terminal WebSocket Protocol and Concurrency**:
  - A dedicated WebSocket route at `/api/repos/{repo}/terminal/ws` establishes a full-duplex bridge to Modal's pseudo-terminal process execution (`sandbox.exec(pty=True)`).
  - The backend subshell launches as `bash --login` with working directory set to `/root/{repo}`, sourcing standard environment paths and sandbox shell aliases.
  - A background reader thread consumes stdout chunks and pushes text frames across the WebSocket; incoming WebSocket text messages are written directly to the container process stdin stream and flushed immediately.
  - When the client disconnects or closes the drawer, the WebSocket disconnect handler immediately terminates the container process handle.
  - Terminal subshell execution runs concurrently with background dev servers and autonomous pipeline stages; when an agent job is actively running on the repository, an alert badge in the terminal header informs the developer of concurrent agent activity.

## Testing Decisions

- **Testing Principles**:
  - Only test observable external behavior, contract adherence, and failure modes; avoid asserting internal implementation variables or scraping source files.
  - Test at the highest available seam in each environment.

- **Backend Seam (pytest + FastAPI TestClient & WebSocket TestClient)**:
  - Test file inspection endpoints with mock sandbox execution when running, verifying correct file trees, ignore filtering, and 500KB truncation.
  - Test file inspection fallback to the GitHub Git Database API when the sandbox is stopped.
  - Test the terminal WebSocket endpoint using Starlette's WebSocket test client, verifying connection establishment, bidirectional text message relaying to stdin/stdout, and graceful process termination on disconnect.

- **Frontend Seam (Vitest + React Testing Library via `renderWithProviders`)**:
  - Test canvas view mode switching between Live Preview, In-Studio Code Viewer, and Pre-Merge Diff Viewer.
  - Test file tree expansion, file selection, and code viewer rendering.
  - Test diff viewer scope toggle ("Working Tree Changes" vs "Branch Changes") and layout toggle (Unified vs Split).
  - Test the Interactive Terminal tab in the Activity Drawer, verifying xterm mounting, WebSocket connection initiation, and rendering of the concurrent agent execution warning badge.

- **Prior Art**:
  - Backend FastAPI endpoint testing patterns in existing route tests (`test_fastapi_preview.py`, `test_bottlenecks_api.py`, `test_pull_requests_endpoints.py`).
  - Frontend component and drawer test patterns in existing Vitest suites (`ActivityDrawer.test.tsx`, `DiffViewer.test.tsx`, `LivePreview.controls.test.tsx`).

## Out of Scope

- In-browser code editing or file creation with write-back to the sandbox or repository (all code edits remain mediated through the Assembly Line Pipeline or terminal commands).
- Full multi-tab terminal sessions or persistent tmux session multiplexing across browser reloads.
- Standalone file download manager or zip archive exporter.
- Web-based graphical debugger integration (e.g. Chrome DevTools protocol inspection over WebSockets).

## Further Notes

- Architectural context and rationale are formally documented in ADR 0069 (`docs/adr/0069-in-studio-code-and-diff-viewer-with-in-sandbox-interactive-terminal.md`).
- Domain terms `In-Studio Code Viewer`, `Pre-Merge Diff Viewer`, and `In-Sandbox Interactive Terminal` are canonically recorded in `CONTEXT.md`.
- Requires adding `xterm` and `@xterm/addon-fit` to `factory/ui/frontend/package.json` and compiling the frontend bundle into `factory/ui/static/dist/` upon implementation.
