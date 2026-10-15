# 01: Backend Pull Request Discovery and In-Studio Squash Merge API

**What to build:** Implement backend endpoints and GitHub client methods for discovering repository Feature Pull Requests and executing in-Studio squash merges with remote branch deletion and live preview sandbox synchronization to `main`.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Add `fetch_repo_pull_requests` to `factory/ui/github.py` querying GitHub API for active and recent pull requests, normalizing status (`draft`, `ready_for_review`, `merged`, `conflict`).
- [x] Add `merge_repo_pull_request` to `factory/ui/github.py` executing a GitHub squash merge (`merge_method: "squash"`), formatting `commit_title` as `${pr.title} (#${pr.number})`, extracting `Fixes #<id>` directives for `commit_message`, and deleting the remote feature branch (`DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}`).
- [x] Implement `GET /api/studio/repos/{repo}/pulls` in `factory/ui/app.py` returning active and recent pull requests with branch filtering support.
- [x] Implement `POST /api/studio/repos/{repo}/pulls/{pull_number}/merge` in `factory/ui/app.py` invoking squash merge, remote branch cleanup, and triggering post-merge sandbox synchronization.
- [x] Implement `sync_sandbox_to_main` on `PreviewRegistry` in `factory/ui/registry.py` executing `git reset --hard && git clean -fd && git checkout main && git pull origin main` in running sandbox via `sandbox.exec`, updating preview registry branch state to `main`.
- [x] Record a structured delivery gate merge card in SQLite `chat_messages` table upon successful merge.
- [x] Full backend test coverage in `tests/test_ui.py` asserting PR fetching, squash merge parameter formatting, remote branch deletion, conflict error handling, and preview sandbox checkout.
