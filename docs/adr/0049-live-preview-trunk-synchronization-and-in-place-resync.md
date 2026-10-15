# Live Preview Trunk Synchronization and In-Place Resync

**Status**: Accepted (Amends [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md) and [ADR 0048](0048-live-preview-branch-selector-and-in-place-switching.md))

To ensure that the running Unified Studio Sandbox can update when changes land on the default trunk branch (`main`) without requiring container termination or cold-start re-provisioning, we decided to implement **Trunk Synchronization** via an on-demand toolbar sync action and automatic upstream pulling whenever `main` is selected in the Live Preview Branch Selector.

## Considered Options

- **Background GitHub API Polling Daemon**: Running a 15–20s periodic background polling loop in the Factory Studio backend to query GitHub commits on `main`. Rejected because it introduces unnecessary background network traffic, risks GitHub API rate-limit exhaustion, creates background container churn while the developer may be reading or testing, and is unnecessary since developers know when a PR has merged.
- **In-Container Git Watcher Loop**: Running a background bash loop in `factory_entrypoint.sh` executing `git fetch` every 20s. Rejected because constant git fetching consumes container CPU cycles, creates git index lock contention (`index.lock`), and risks race conditions with in-sandbox agents.
- **Inbound GitHub Webhooks**: Registering a webhook endpoint on Factory Studio for GitHub `push` events. Rejected because Factory Studio runs as a local web service on developer workstations (`http://127.0.0.1:3010`) without static inbound public ingress or automated webhook provisioning.
- **On-Demand Toolbar Sync Action & Auto-Pull on Branch Selection**: Providing a dedicated sync icon button directly in the Live Preview toolbar, coupled with automatic in-container fetch and reset to `origin/main` whenever `main` is selected in the Live Preview Branch Selector. Accepted because it gives developers immediate control, guarantees freshness when inspecting merged code, consumes zero background rate-limit quota, and uses proven in-place `sandbox.exec` orchestration without container restart latency.

## Consequences

- The canonical term **Trunk Synchronization** is recorded in `CONTEXT.md`.
- **Backend Sync REST Seam (`factory/ui/app.py` & `factory/ui/registry.py`)**:
  - `POST /api/studio/repos/{repo}/preview/sync`:
    - Validates target branch (defaults to active branch or `main`).
    - Executes in-container clean fetch and reset via `sandbox.exec`:
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
    - Streams stdout/stderr to preview dev server logs drawer.
    - Emits SSE `preview_refresh` event to reload the preview iframe if needed.
    - Returns `{success: true, branch: "<branch>", commit: "<sha>", updated: true}`.
    - If the sandbox is stopped or idle, updates the preview registry branch state so subsequent launches boot on the latest ref.
- **Branch Selector Auto-Pull Behavior**:
  - Selecting `main` in the Live Preview Branch Selector (`POST /api/studio/repos/{repo}/preview/branch`) always executes the remote fetch and hard reset to `origin/main`, guaranteeing that switching to `main` displays the newest commits.
- **Execution & Concurrency Safety Guards**:
  - Trunk Synchronization is strictly disabled (with visual lock and tooltip) whenever an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`) to prevent dirty working tree collisions during agent execution.
- **Frontend Reactive UI (`factory/ui/frontend/src/components/LivePreview.tsx`)**:
  - Adds a dedicated sync button (`RefreshCw` icon) adjacent to the `#preview-branch-badge` / Branch Selector.
  - Renders a loading spinner and disables clicks while synchronization is in flight.
  - Emits toast notifications on completion (`Preview synchronized with main`).
