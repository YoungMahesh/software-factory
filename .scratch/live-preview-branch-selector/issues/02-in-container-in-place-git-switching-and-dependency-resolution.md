# 02: In-Container In-Place Git Switching and Diff-Aware Dependency Resolution

**What to build:**
Enable developers to switch Git branches inside an actively serving Unified Studio Sandbox in place without restarting or tearing down the container. Factory Studio issues in-container git commands via `sandbox.exec` to perform a clean working tree reset (`git reset --hard && git clean -fd`), fetch remote changes, and checkout the target branch. If `package.json` or `pnpm-lock.yaml` changed between revisions, the container automatically executes `pnpm install --prefer-offline` before dev server reloads, streaming logs to the dev server drawer. The preview registry broadcasts SSE `branch` and `preview_refresh` events to update the UI and trigger live preview iframe refreshes. If in-container checkout fails, the container is preserved safely on its current branch with diagnostic logs appended.

**Blocked by:** 01: Remote Branch Discovery and Idle Target Selection

**Status:** resolved

- [x] `PreviewRegistry` implements `switch_preview_branch(repo, branch)` using `sandbox.exec` in the active Unified Studio Sandbox.
- [x] Working tree is cleaned (`git reset --hard && git clean -fd`) before running `git checkout <branch> && git pull origin <branch>`.
- [x] Diffs in `package.json` or `pnpm-lock.yaml` between previous and target revisions automatically trigger in-container `pnpm install --prefer-offline`.
- [x] `POST /api/studio/repos/{repo}/preview/branch` accepts `{"branch": string}`, triggers the switch, and returns updated branch state.
- [x] Preview SSE stream broadcasts `branch` update and `preview_refresh` event upon successful switch.
- [x] If checkout or install fails, error output is appended to preview dev logs drawer, container is kept running on current branch, and an error response is returned.
- [x] Automated tests verify successful in-place switching, diff-aware package installation, SSE event emissions, and non-destructive failure recovery.
