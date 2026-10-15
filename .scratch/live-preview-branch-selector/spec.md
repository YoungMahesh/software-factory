# Spec: Live Preview Branch Selector and In-Place Container Switching

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

In Factory Studio, developers can launch a Live Preview of their frontend application running inside a Unified Studio Sandbox. Currently, the active branch indicator in the preview toolbar is a static, read-only text badge (`preview-branch-badge`) displaying `factory/<feature>`.

When a developer finishes implementing a feature, merges a Feature Pull Request into `main`, or wants to compare the live application on the feature branch against `main`, there is no mechanism to toggle branches in the preview toolbar. To view a different branch, developers are forced to manually terminate the preview sandbox and wait for automatic branch resolution or re-provisioning. This introduces 30–60 seconds of cold-start container latency, breaks developer flow, and prevents fast visual verification across branches.

## Solution

Transform the read-only branch badge into an interactive **Live Preview Branch Selector**:

1. **Branch Discovery & Filtering**:
   - Query remote branches via GitHub API through a dedicated endpoint (`GET /api/studio/repos/{repo}/branches`).
   - Filter branches strictly to the default branch (`main`) and active feature branches (`factory/<slug>` and `factory/issue-<id>`).
   - Sort the active branch first, with clear visual indicators for `main` vs. feature branches.

2. **Interactive Dropdown in Live Preview Toolbar**:
   - Upgrade `#preview-branch-badge` in the `LivePreview` toolbar into an interactive trigger with a `GitBranch` icon, branch label, and `ChevronDown`.
   - Clicking opens a dark-mode popover menu listing available branches with checkmarks for the active branch.
   - Displays a smooth loading spinner and disables interaction while a branch switch is executing.

3. **In-Place Container Git Orchestration**:
   - When a developer selects a branch and the Unified Studio Sandbox is actively serving, Factory Studio executes in-place Git commands inside the container via `sandbox.exec`:
     - Clean reset (`git reset --hard && git clean -fd`) to eliminate dirty working tree artifacts.
     - Remote fetch and checkout (`git fetch origin && git checkout <branch> && git pull origin <branch>`).
     - In-container dev server hot-reloads the application via Vite's file watcher without restarting the container.
   - If the preview sandbox is currently idle or stopped, updating the branch records the target branch so subsequent preview launches start directly on that branch.

4. **Diff-Aware Automated Dependency Installation**:
   - If `package.json` or `pnpm-lock.yaml` changed between the previous and target branch commits, the container automatically executes `pnpm install --prefer-offline` before dev server reloads, streaming progress to the dev server logs drawer.

5. **Concurrency & Execution Safety Guards**:
   - The branch selector is strictly disabled with a visual lock icon and explanatory tooltip whenever an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`), preventing git race conditions and file collisions while agents are generating code.

6. **Fault-Tolerant Non-Destructive Failure Recovery**:
   - If in-container checkout or package installation fails, stderr is logged to the preview dev server logs drawer, the container is safely retained on its current working branch without termination, and an actionable error toast alert is surfaced in the UI.

## User Stories

1. As a developer using Factory Studio, I want to see the currently checked-out Git branch displayed clearly in the Live Preview toolbar, so that I always know which branch my preview reflects.
2. As a developer inspecting a live preview, I want to click the branch badge in the toolbar to reveal a dropdown menu of available branches, so that I can easily browse branch options.
3. As a developer viewing the branch dropdown, I want to see the default trunk branch (`main`) alongside all active feature branches (`factory/*`), so that I only see branches relevant to the software factory delivery lifecycle.
4. As a developer viewing the branch dropdown, I want the currently active branch to be marked with a distinct checkmark, so that I can confirm my current selection at a glance.
5. As a developer selecting a different branch from the dropdown, I want the branch switch to execute in place inside the running preview container, so that I do not have to wait 30–60 seconds for a full container cold start.
6. As a developer initiating a branch switch, I want the branch badge to display a loading spinner while the switch is in progress, so that I receive immediate feedback that the operation is running.
7. As a developer initiating a branch switch, I want the dropdown to close immediately and disable further branch switching while the transition is processing, so that conflicting concurrent git operations are prevented.
8. As a developer observing a branch switch, I want Vite's development server inside the sandbox to hot-reload the application immediately upon git checkout, so that the live preview iframe reflects the target branch within seconds.
9. As a developer whose branch switch has completed, I want the Live Preview iframe to automatically resynchronize or refresh, so that I don't have to manually click refresh to view the updated code.
10. As a developer with the preview sandbox stopped or idle, I want to be able to select a branch in the selector, so that when I click "Preview App", the container launches directly on my chosen branch.
11. As a developer observing an active Assembly Line Pipeline job, I want the branch selector in the Live Preview toolbar to be strictly disabled with a lock icon and tooltip, so that I cannot inadvertently mutate the working tree while agents are writing code.
12. As a developer switching to a branch that added new npm dependencies, I want the sandbox to automatically detect changes in `package.json` and execute `pnpm install`, so that the dev server does not crash with missing module errors.
13. As a developer with the Dev Server Logs drawer open, I want to see real-time output from the in-sandbox checkout and package installation, so that I can diagnose any build or dependency issues.
14. As a developer encountering a git or dependency failure during a branch switch, I want the container to remain alive on the previous branch rather than crashing or terminating, so that my active preview session is not lost.
15. As a developer encountering a branch switch failure, I want an error toast alert detailing the failure reason and pointing to the dev server logs, so that I can take corrective action.
16. As a developer who just merged a Feature Pull Request into `main`, I want to switch the preview to `main` via the selector, so that I can visually verify the merged trunk state.
17. As a developer working on a single-issue fix (`factory/issue-<id>`), I want the issue branch to appear in the branch dropdown alongside milestone feature branches, so that single-issue tasks enjoy identical preview capabilities.
18. As a developer switching repositories in Factory Studio, I want the branch selector to automatically refresh its branch list for the newly selected repository, so that I never see stale branches from a previous project.
19. As a developer using keyboard navigation, I want the branch dropdown to support standard keyboard traversal (`Escape` to close, `ArrowDown`/`ArrowUp` to navigate, `Enter` to select), so that the toolbar remains accessible.
20. As a developer returning to Factory Studio or reloading the browser, I want the active preview branch to persist and rehydrate from the preview registry, so that my selected branch state is preserved.

## Implementation Decisions

- **Domain Model Vocabulary**:
  Strict adherence to canonical terms in `CONTEXT.md`:
  - **Live Preview Branch Selector** for the interactive toolbar dropdown.
  - **Unified Studio Sandbox** for the persistent container running the Vite dev server and in-sandbox processes.
  - **Feature Branch** (`factory/<feature>`) for feature deliverables.
  - **In-Studio Merge Control** for pull request merging.

- **Backend REST Seams**:
  - `GET /api/studio/repos/{repo}/branches`: Fetches remote branch references from GitHub REST API (`GET /repos/{owner}/{repo}/branches`). Filters results to `main` (or repo default branch) and branches with prefix `factory/`.
  - `POST /api/studio/repos/{repo}/preview/branch`:
    - Request payload: `{"branch": string}`.
    - If a Unified Studio Sandbox is active (`SERVING`), executes in-sandbox git orchestration via `sandbox.exec`.
    - Slices `/root/.factory.env` credentials to authenticate git operations.
    - Commands executed:
      ```bash
      cd /root/<repo> && \
      git fetch origin && \
      OLD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "") && \
      git reset --hard && \
      git clean -fd && \
      git checkout <branch> && \
      git pull origin <branch> && \
      if [ -n "$OLD_SHA" ] && git diff --name-only "$OLD_SHA" HEAD | grep -E '^(package\.json|pnpm-lock\.yaml)$' >/dev/null; then \
        pnpm install --prefer-offline; \
      fi
      ```
    - Updates `PreviewRegistry` state (`preview.branch = branch`).
    - Emits SSE events: `{"event": "branch", "branch": branch}` and `{"event": "preview_refresh", "repo": repo}` over `/api/studio/repos/{repo}/preview/stream`.
    - If no sandbox is currently serving, updates `preview.branch` in registry and database so subsequent preview launches use the selected branch.

- **Frontend Component Architecture**:
  - `LivePreview.tsx`:
    - Replaces `#preview-branch-badge` with an interactive menu component.
    - Receives new props: `availableBranches?: string[]`, `isSwitchingBranch?: boolean`, `onSwitchBranch?: (branch: string) => void`, `isJobActive?: boolean`.
    - When `isJobActive` is true, displays lock icon and disables dropdown trigger with tooltip.
    - When `isSwitchingBranch` is true, renders loading spinner inside the badge and disables clicks.
  - `StudioView.tsx`:
    - Uses TanStack Query to fetch branches for the active repository (`queryKey: ["studio", "branches", selectedRepo]`).
    - Invalidates branch cache on repository change, job completion, and drawer open.
    - Houses the `handleSwitchBranch` callback that dispatches `POST /api/studio/repos/{repo}/preview/branch` and triggers visual feedback.

- **Error Resilience Strategy**:
  - Non-destructive execution: Errors in `sandbox.exec` return HTTP 400/500 with stderr diagnostics without altering `PreviewStatus` to `FAILED`.
  - Stderr is captured and appended to `preview.logs` with `❌ [BRANCH SWITCH ERROR]` prefix.
  - UI displays an error toast notification and leaves active branch state unmodified.

## Testing Decisions

- **What makes a good test**:
  Tests must exercise observable external contracts (HTTP responses, SSE broadcast envelopes, rendered DOM elements, disabled states, and error alerts) without coupling to internal private methods.
- **Backend API & Service Testing (`tests/test_ui.py`)**:
  - Test `GET /api/studio/repos/{repo}/branches` returns filtered list containing `main` and `factory/*` branches while excluding unrelated branches.
  - Test `POST /api/studio/repos/{repo}/preview/branch` on an idle repository updates the target branch for subsequent launches.
  - Test `POST /api/studio/repos/{repo}/preview/branch` on an active sandbox invokes in-container git checkout, pulls latest commits, and broadcasts `branch` and `preview_refresh` SSE events.
  - Test that `pnpm install` execution is triggered when package dependencies differ between revisions.
  - Test error handling when in-sandbox execution fails, verifying non-destructive retention of container state.
- **Frontend Component & Integration Testing (`factory/ui/frontend/src/`)**:
  - Test `LivePreview.test.tsx` renders static branch pill when no switch handler is provided, and renders interactive dropdown when available branches are supplied.
  - Test that selecting a branch from the dropdown invokes `onSwitchBranch`.
  - Test that active job disables the selector and displays tooltip explaining the concurrency lock.
  - Test that loading state renders spinner during active branch switch.
  - Test `StudioView.test.tsx` integration with TanStack Query and branch switching callbacks.
- **Prior Art**:
  - `tests/test_ui.py` for FastAPI Starlette test client API testing.
  - `factory/ui/frontend/src/components/LivePreview.test.tsx` for LivePreview toolbar rendering and interaction tests.
  - `factory/ui/frontend/src/views/StudioView.test.tsx` for StudioView integration tests.

## Out of Scope

- Arbitrary branch creation from the Live Preview toolbar (new branches remain governed by the Grilling Assistant and Issue Drawer).
- Manual in-container git conflict resolution or 3-way merge tools in the preview toolbar.
- Switching to non-factory experimental branches created outside the software factory ecosystem.

## Further Notes

- Documented in Architectural Decision Record `docs/adr/0048-live-preview-branch-selector-and-in-place-switching.md`.
- Conforms to canonical glossary in `CONTEXT.md`.
