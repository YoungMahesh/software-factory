# 01: Live Preview Trunk Synchronization and In-Place Resync

**What to build:**
Implement Trunk Synchronization for Factory Studio, enabling developers to synchronize their running Unified Studio Sandbox with remote updates on `main` on demand without container restart. This encompasses the backend REST sync endpoint (`POST /api/studio/repos/{repo}/preview/sync`), in-container git fetch and reset orchestration (`sandbox.exec`) with diff-aware `pnpm install`, SSE preview refresh broadcasting, branch selector auto-pull behavior when switching to `main`, concurrency safety locking during active assembly line jobs, and the dedicated toolbar sync button UI with loading spinners, tooltips, and toast feedback in `LivePreview.tsx` and `StudioView.tsx`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Backend endpoint `POST /api/studio/repos/{repo}/preview/sync` accepts optional `{"branch": string}` (defaulting to current preview branch or `main`).
- [ ] If Unified Studio Sandbox is actively `SERVING`, executes in-place `sandbox.exec` in `/root/<repo>`:
  - `git fetch origin <branch>`
  - `git reset --hard origin/<branch> && git clean -fd`
  - Diff-aware `pnpm install --prefer-offline` if `package.json` or `pnpm-lock.yaml` changed
  - Resolves updated commit SHA and streams execution logs to the preview dev server logs drawer with `🔄 [SYNC]` prefix.
- [ ] Emits `preview_refresh` SSE event over `/api/studio/repos/{repo}/preview/stream` to reload the preview iframe upon successful synchronization.
- [ ] If preview sandbox is stopped or idle, records target branch in the preview registry so the next launch boots on the latest ref.
- [ ] Enhances branch switching (`POST /api/studio/repos/{repo}/preview/branch`) so selecting `main` automatically fetches and resets to `origin/main` in-container.
- [ ] Concurrency safety guard: strictly disables and rejects synchronization requests when an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`).
- [ ] Non-destructive failure recovery: errors during git fetch or package installation preserve the container on its current working state without termination and return descriptive error details.
- [ ] Frontend `LivePreview.tsx` renders a dedicated sync icon button (`RefreshCw`) in the preview toolbar adjacent to the branch selector with tooltip `"Pull latest from remote"`.
- [ ] Sync button shows an animated loading spinner and disables user clicks while synchronization is in flight.
- [ ] Sync button displays a lock icon and tooltip explaining the concurrency lock when an assembly line job is active.
- [ ] Frontend `StudioView.tsx` handles the sync mutation, displaying success toast notifications with commit SHA or error alerts on failure.
- [ ] Backend API tests in `tests/test_ui.py` verify in-container sync execution, idle branch persistence, dependency drift detection, concurrency locking, and non-destructive error handling.
- [ ] Frontend tests in `LivePreview.test.tsx` and `StudioView.test.tsx` verify button rendering, loading states, disabled lock tooltips, and toast notifications.
