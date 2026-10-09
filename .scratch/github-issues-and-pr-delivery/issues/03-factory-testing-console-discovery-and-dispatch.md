# 03: Factory Testing Console Discovery and Dispatch

**What to build:** An enhanced Factory Testing Console discovery service and web interface that queries the GitHub API directly for open Milestones and associated Issues across member repositories in the canonical Test Organization (`software-factory-09-test`), auto-populating interactive controls and enabling one-click test dispatches for milestones and single issues without requiring remote `.scratch/` trees.

**Blocked by:** 02: Assembly Line Lifecycle and Feature Pull Request Gate

**Status:** ready-for-agent

- [ ] The testing console GitHub discovery service queries GitHub REST endpoints for repository milestones and issues using ephemerally decrypted organization credentials in memory.
- [ ] Backend API endpoints expose discovered milestones and candidate issues for selected test repositories.
- [ ] The web UI replaces static `.scratch/` tree expectations with dynamic milestone selectors and display badges for issue dependencies and labels.
- [ ] Users can launch tests by selecting a milestone, selecting a specific issue within a milestone, or entering an ad-hoc single issue ID directly.
- [ ] Host-side CLI and testing console dispatches pass parameters cleanly to the sandbox entrypoint.
- [ ] Unit and integration tests verify repository milestone discovery, fallback behavior on missing milestones, and FastAPI endpoint contracts.
