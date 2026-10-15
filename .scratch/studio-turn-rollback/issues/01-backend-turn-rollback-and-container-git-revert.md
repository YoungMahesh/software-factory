# 01: Backend Turn Rollback and Container Git Revert

**What to build:**
Implement the backend REST endpoint and in-container git revert engine for Turn Rollback in Factory Studio. This includes:
- `POST /api/studio/repos/{repo}/turns/rollback` in `factory/ui/app.py`.
- Concurrency safety guard: strictly reject requests (HTTP 409) if an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`).
- Merge safety guard: strictly reject requests (HTTP 400) if the Feature Pull Request associated with the turn has already been merged into `main`.
- In-container Git revert execution via `sandbox.exec` in the Unified Studio Sandbox (`cd /root/<repo>`, `git fetch origin <branch>`, `git checkout <branch>`, `git revert --no-edit <commit_sha>`, `git push origin <branch>`).
- Non-destructive conflict handling: if `git revert` fails, immediately run `git revert --abort`, stream stderr to dev server logs, and raise HTTP 400 without corrupting the working tree.
- Diff-aware dependency synchronization: if `package.json` or `pnpm-lock.yaml` changed between old and new HEAD, execute `pnpm install --prefer-offline`.
- SSE `preview_refresh` broadcast to trigger instant Vite HMR or iframe reload.
- Auto-boot fallback: if the Unified Studio Sandbox is stopped or idle, launch it before executing the rollback.
- Issue tracker synchronization: reopen GitHub Issue, reset label to `ready-for-agent`, remove `resolved`, and post an audit comment; update Local Markdown Issue Tracker status to `ready-for-agent` and strip Commit line.
- SQLite database persistence in `factory/ui/db.py`: mark original message as reverted (`turn_data_json.reverted = true`) and append a new `turn_rollback` message.
- Unit and integration tests in `tests/test_ui.py`.

**Blocked by:** None (can start immediately)

**Status:** resolved
**Triage:** ready-for-agent

- [x] Add `mark_chat_message_reverted` and `save_rollback_message` methods in `factory/ui/db.py` to update original turn metadata and persist append-only rollback event.
- [x] Implement `POST /api/studio/repos/{repo}/turns/rollback` in `factory/ui/app.py`.
- [x] Enforce concurrency safety guard rejecting with HTTP 409 when `registry.is_job_active(repo)` is true.
- [x] Enforce merge guard rejecting with HTTP 400 when the turn's Feature PR is merged into `main`.
- [x] Implement in-container git revert execution via `sandbox.exec`, pushing the revert commit to remote.
- [x] Implement automatic `git revert --abort` on conflict, preserving clean workspace state and raising HTTP 400.
- [x] Implement diff-aware `pnpm install --prefer-offline` when dependency files differ between HEAD and parent.
- [x] Broadcast SSE `preview_refresh` to reload preview iframe.
- [x] Coordinate issue tracker: reopen GitHub Issue with label reset and comment; update local tracker if applicable.
- [x] Add comprehensive tests in `tests/test_ui.py` covering success, conflict abort, concurrency lock, merged PR rejection, and DB rehydration.
