# 03: Factory Testing Console Discovery and Dispatch

**What to build:** An enhanced Factory Testing Console discovery service and web interface that queries the GitHub API directly for open Milestones and associated Issues across member repositories in the canonical Test Organization (`software-factory-09-test`), auto-populating interactive controls and enabling one-click test dispatches for milestones and single issues without requiring remote `.scratch/` trees.

**Blocked by:** 02: Assembly Line Lifecycle and Feature Pull Request Gate

**Status:** resolved

- [x] The testing console GitHub discovery service queries GitHub REST endpoints for repository milestones and issues using ephemerally decrypted organization credentials in memory.
- [x] Backend API endpoints expose discovered milestones and candidate issues for selected test repositories.
- [x] The web UI replaces static `.scratch/` tree expectations with dynamic milestone selectors and display badges for issue dependencies and labels.
- [x] Users can launch tests by selecting a milestone, selecting a specific issue within a milestone, or entering an ad-hoc single issue ID directly.
- [x] Host-side CLI and testing console dispatches pass parameters cleanly to the sandbox entrypoint.
- [x] Unit and integration tests verify repository milestone discovery, fallback behavior on missing milestones, and FastAPI endpoint contracts.

## Comments

### Quality Gate Audit

- GitHub discovery service in `factory/ui/github.py` implemented (`fetch_repo_milestones`, `fetch_repo_issues`, `fetch_repo_milestones_and_issues`, `fetch_repo_issue`, `parse_github_blocked_by`, `map_github_issue_status`).
- Ephemeral in-memory decryption of organization credentials via host SOPS preserved.
- FastAPI endpoints `/api/repos/{repo}/milestones`, `/api/repos/{repo}/issues`, and `/api/repos/{repo}/issues/{issue_number}` exposed.
- Interactive Testing Console UI in `factory/ui/templates/index.html` updated with dynamic milestone dropdown, issue dropdown, badge preview card for dependencies and statuses, and ad-hoc single issue dispatch.
- CLI Dispatcher (`factory/run.py`), Spawner (`factory/spawner.py`), and Orchestrator (`factory/orchestrator.py`) updated to support `--issue <id>` directly, defaulting feature to `issue-<id>` and passing parameters cleanly to the sandbox entrypoint.
- All 75 Python tests pass (`python3 -m unittest discover tests`).
- All 113 TypeScript tests in `sandbox/factory` pass (`pnpm --prefix sandbox/factory test`).
- TypeScript typecheck (`tsc --noEmit`) passes with zero errors.
- Python compilation check (`py_compile`) passes with zero errors.
