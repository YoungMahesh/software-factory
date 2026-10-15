# 01: Remote Branch Discovery and Idle Target Selection

**What to build:**
Enable Factory Studio to discover remote branches for a repository and allow developers to pre-select a target branch when the preview sandbox is idle or stopped. The system queries GitHub's REST API for remote branches, filters results strictly to the default branch (`main`) and active feature branches (`factory/*`), and returns them via a dedicated backend endpoint. When the preview sandbox is not actively running, selecting a branch updates the repository's preview state so subsequent container launches immediately boot on that chosen branch.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `fetch_repo_branches(repo_name)` queries GitHub REST API `GET /repos/{owner}/{repo}/branches` and returns candidate branches.
- [x] Remote branches are filtered to include only `main` (or default branch) and branches with prefix `factory/`, sorted with default branch first.
- [x] `GET /api/studio/repos/{repo}/branches` endpoint returns the filtered list of available branches.
- [x] When the preview sandbox is stopped or idle, updating the target branch persists the selection so subsequent launches start on that branch.
- [x] API handles unauthorized or network errors from GitHub gracefully with non-blocking diagnostic responses.
- [x] Automated tests verify branch filtering, API endpoint responses, and idle preview branch persistence.
