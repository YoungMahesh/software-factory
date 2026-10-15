# Spec: Live Preview Trunk Synchronization and In-Place Resync

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

In Factory Studio, developers iterate on frontend web applications running inside a persistent Unified Studio Sandbox with a live preview dev server. When a developer finishes implementing a feature and merges a Feature Pull Request into `main` (either on GitHub or via Factory Studio), the running sandbox has no mechanism to know that `main` has advanced.

Because there is no background webhook or polling mechanism, the Vite development server in the container keeps serving the previous commit until the container is manually stopped or times out after 30 minutes of inactivity. To see the merged application on `main`, developers are forced to manually terminate the preview container and wait 30–60 seconds for a full container cold start, breaking developer flow and making rapid visual verification of merged changes painful.

## Solution

Implement **Trunk Synchronization** in Factory Studio, enabling developers to update their running preview container to the latest commits on `main` on demand without container restart:

1. **Dedicated Sync Button in Live Preview Toolbar**:
   - Add a dedicated Trunk Synchronization icon button (`RefreshCw`) directly in the `LivePreview` toolbar, placed adjacent to the Live Preview Branch Selector and iframe refresh button.
   - Hovering displays a tooltip (`"Pull latest from remote"` or `"Sync with origin/main"`).
   - Clicking triggers an in-container fetch and reset to the remote tracking branch, displaying a smooth spinner and disabling clicks while the sync operation is processing.

2. **Auto-Pull on Branch Selector Switch to `main`**:
   - When a developer selects `main` in the Live Preview Branch Selector, the backend automatically performs a remote fetch and hard reset to `origin/main` as part of the branch transition.
   - Switching to `main` to inspect merged code guarantees that the preview immediately reflects the newest upstream commits without requiring a secondary click on the sync button.

3. **In-Place Git Reset and Hot Module Replacement**:
   - When synchronization is triggered, Factory Studio executes in-place git commands inside the running container via `sandbox.exec`:
     ```bash
     cd /root/<repo> && \
     git fetch origin <branch> && \
     OLD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "") && \
     git reset --hard origin/<branch> && \
     git clean -fd && \
     if [ -n "$OLD_SHA" ] && git diff --name-only "$OLD_SHA" HEAD | grep -E '^(package\.json|pnpm-lock\.yaml)$' >/dev/null; then \
       pnpm install --prefer-offline; \
     fi
     ```
   - Vite's file watcher detects the file updates and triggers Hot Module Replacement (HMR) or dev server reload without container downtime.
   - The backend broadcasts a `preview_refresh` event over SSE to reload the preview iframe if necessary.

4. **Diff-Aware Dependency Drift Resolution**:
   - If `package.json` or `pnpm-lock.yaml` changed between the previous and updated revisions, the container executes `pnpm install --prefer-offline` before reloading, streaming install progress to the preview dev server logs drawer.

5. **Execution & Concurrency Safety Guards**:
   - The synchronization button is strictly disabled with a visual lock icon and explanatory tooltip whenever an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`), preventing git race conditions and working tree corruption during autonomous agent execution.

6. **Fault-Tolerant Non-Destructive Failure Recovery**:
   - If git fetch or package installation fails inside the container, stderr is logged to the preview dev server logs drawer with an error prefix, the container is safely retained on its current working tree without crashing, and an actionable error toast is surfaced in the UI.

## User Stories

1. As a developer using Factory Studio, I want a dedicated sync button in the Live Preview toolbar, so that I can easily pull the latest remote commits into my preview environment.
2. As a developer who just merged a Feature Pull Request on GitHub, I want to click the sync button in the toolbar, so that my preview environment updates to the merged trunk without restarting the container.
3. As a developer initiating a sync, I want the sync button to display a loading spinner while the operation is executing, so that I receive immediate visual feedback that synchronization is in progress.
4. As a developer initiating a sync, I want the sync button to be temporarily disabled during execution, so that I cannot inadvertently trigger overlapping concurrent git operations.
5. As a developer whose sync completes successfully, I want to see a brief toast notification confirming that the preview is synchronized with the latest commit SHA, so that I have clear confirmation of what was pulled.
6. As a developer viewing dev server logs, I want in-container git fetch, reset, and clean output to stream to the preview dev server logs drawer, so that I can inspect the exact files and commits updated.
7. As a developer switching from a feature branch to `main` via the Live Preview Branch Selector, I want the container to automatically fetch and pull `origin/main`, so that I immediately see the latest trunk code without having to click a separate sync button.
8. As a developer re-selecting `main` in the branch selector while already on `main`, I want the branch selector to re-fetch and re-sync `origin/main`, so that I can refresh trunk from the branch menu as well.
9. As a developer observing an active Assembly Line Pipeline job, I want the sync button to be strictly disabled with a lock icon and tooltip, so that I cannot mutate the working tree while agents are generating code.
10. As a developer with the preview sandbox stopped or idle, I want clicking the sync button to record the target branch and update registry state, so that when I next launch the preview it starts on the latest remote commit.
11. As a developer syncing a branch that added new npm packages, I want the container to automatically detect changes in `package.json` or `pnpm-lock.yaml` and run `pnpm install`, so that the dev server does not crash with missing module errors.
12. As a developer syncing changes, I want the Live Preview iframe to automatically refresh via SSE signal upon completion, so that I do not have to manually click the browser iframe reload button.
13. As a developer encountering a network or git failure during sync, I want the container to remain alive on its current working state rather than crashing or terminating, so that my preview session is preserved.
14. As a developer encountering a sync failure, I want an error toast alert detailing the failure reason and pointing to the dev server logs drawer, so that I can diagnose and take corrective action.
15. As a developer using the preview toolbar, I want the sync button to be positioned consistently right beside the branch selector, so that its relationship to the active git branch is visually obvious.
16. As a developer hovering over the sync button, I want to see a descriptive tooltip explaining what clicking the button will do, so that its purpose is unambiguous.
17. As a developer using keyboard navigation, I want the sync button to be accessible via keyboard focus and triggerable with `Enter` or `Space`, so that the toolbar complies with accessibility standards.
18. As a developer working across multiple repositories, I want the sync action to target the active selected repository, so that operations are properly scoped and isolated.
19. As a developer inspecting a feature branch (`factory/<feature>`), I want the sync button to pull remote changes for the current feature branch when clicked, so that trunk synchronization and feature branch synchronization share a unified affordance.
20. As a developer returning to Factory Studio or reloading the browser, I want the synchronization state to be cleanly reflected in the UI, so that my workspace is always in a coherent state.

## Implementation Decisions

- **Domain Model Vocabulary**:
  All documentation and code strictly adhere to canonical terms in `CONTEXT.md`:
  - **Trunk Synchronization** for the on-demand toolbar resynchronization and in-place container git pull mechanism.
  - **Unified Studio Sandbox** for the persistent preview container.
  - **Live Preview Branch Selector** for the interactive branch dropdown.
  - **In-Studio Merge Control** for pull request merging.

- **Backend REST Seams (`factory/ui/app.py` & `factory/ui/registry.py`)**:
  - `POST /api/studio/repos/{repo}/preview/sync`:
    - Request payload: `{"branch": string | null}` (defaults to the currently checked-out preview branch, or `main`).
    - If a Unified Studio Sandbox is actively `SERVING`, executes in-sandbox git orchestration via `sandbox.exec`.
    - Script executed inside `/root/<repo>`:
      ```bash
      cd /root/<repo> && \
      git fetch origin <branch> && \
      OLD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "") && \
      git reset --hard origin/<branch> && \
      git clean -fd && \
      if [ -n "$OLD_SHA" ] && git diff --name-only "$OLD_SHA" HEAD | grep -E '^(package\.json|pnpm-lock\.yaml)$' >/dev/null; then \
        pnpm install --prefer-offline; \
      fi
      ```
    - Captures stdout/stderr and appends to preview dev server logs drawer with `🔄 [SYNC]` prefix.
    - Resolves updated commit SHA (`git rev-parse --short HEAD`).
    - Emits SSE `preview_refresh` event over `/api/studio/repos/{repo}/preview/stream`.
    - Returns `{"success": true, "branch": branch, "commit": commit_sha, "updated": true, "message": "Synchronized with origin/<branch>"}`.
    - If the sandbox is stopped or idle, updates the preview registry branch state so subsequent launches boot on the latest ref.
  - Enhancing `POST /api/studio/repos/{repo}/preview/branch`:
    - When `branch == "main"` or when switching to any remote branch, ensures `git fetch origin <branch> && git reset --hard origin/<branch>` is executed so the target branch always lands on the latest remote commit.

- **Frontend Component Architecture**:
  - `LivePreview.tsx`:
    - Adds a new sync button adjacent to `#preview-branch-badge` / Branch Selector.
    - Receives new props: `isSyncing?: boolean`, `onSync?: () => void`, `isJobActive?: boolean`.
    - When `isJobActive` is true, displays lock icon and disables sync button with explanatory tooltip.
    - When `isSyncing` is true, renders an animated spin icon and disables user interaction.
    - Renders accessible tooltip on hover (`"Pull latest from remote"`).
  - `StudioView.tsx`:
    - Houses the `handleSync` callback that dispatches `POST /api/studio/repos/{repo}/preview/sync`.
    - Emits success toast notification upon completion (`"Preview synchronized with <branch> [commit]"`).
    - Catches and surfaces error toasts on failure without crashing the preview.

- **Error Resilience Strategy**:
  - Non-destructive execution: Errors in `sandbox.exec` return HTTP 400/500 with stderr diagnostics without altering `PreviewStatus` to `FAILED`.
  - Stderr is captured and appended to `preview.logs` with `❌ [SYNC ERROR]` prefix.
  - Container remains alive and serving on its previous commit state.
  - UI displays an error toast notification and leaves active preview state unmodified.

## Testing Decisions

- **What makes a good test**:
  Tests must exercise observable external contracts (HTTP status codes, response payloads, SSE broadcast envelopes, rendered DOM buttons, loading states, lock tooltips, and toast alerts) without coupling to internal private implementation details.

- **Backend API & Service Testing (`tests/test_ui.py`)**:
  - Test `POST /api/studio/repos/{repo}/preview/sync` on an active sandbox invokes in-container git fetch, reset, and clean via `sandbox.exec`, and returns success with commit SHA.
  - Test `POST /api/studio/repos/{repo}/preview/sync` on an idle repository records target branch in registry for subsequent launches.
  - Test `POST /api/studio/repos/{repo}/preview/sync` broadcasts `preview_refresh` SSE event to connected listeners.
  - Test that `pnpm install` execution is triggered when package dependencies differ between revisions during sync.
  - Test error handling when in-sandbox execution fails, verifying non-destructive retention of container state and HTTP error response.
  - Test that sync is rejected or prevented when an assembly line job is actively `RUNNING`.

- **Frontend Component & Integration Testing (`factory/ui/frontend/src/`)**:
  - Test `LivePreview.test.tsx` renders sync button adjacent to branch badge.
  - Test that clicking sync button calls `onSync` handler.
  - Test that active job disables the sync button and renders tooltip explaining the concurrency lock.
  - Test that `isSyncing` renders animated spinner and disables clicking.
  - Test `StudioView.test.tsx` integration dispatching sync mutation and showing success/error toast.

- **Prior Art**:
  - `tests/test_ui.py` for FastAPI Starlette test client API testing.
  - `factory/ui/frontend/src/components/LivePreview.test.tsx` for LivePreview toolbar rendering and interaction tests.
  - `factory/ui/frontend/src/views/StudioView.test.tsx` for StudioView integration tests.

## Out of Scope

- Background cron polling loops or headless fetch daemons running inside the sandbox or backend.
- Inbound GitHub webhook endpoints requiring public internet ingress or reverse tunnels for Factory Studio.
- In-container interactive 3-way merge conflict editors in the live preview toolbar (remote tracking branch hard reset is used).
- Auto-pulling unrelated experimental branches not currently selected in the preview environment.

## Further Notes

- Documented in Architectural Decision Record `docs/adr/0049-live-preview-trunk-synchronization-and-in-place-resync.md`.
- Conforms to canonical glossary in `CONTEXT.md` under **Trunk Synchronization**.
