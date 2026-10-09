# 02: Assembly Line Lifecycle and Feature Pull Request Gate

**What to build:** An end-to-end assembly line execution loop and delivery gate that updates GitHub issue statuses (`factory:claimed`, `factory:resolved`, `factory:ready-for-human`), posts detailed audit comments to issues upon quality gate completion, establishes a Draft Feature Pull Request (`factory/<feature>` -> `main`) on the first resolved ticket, accumulates incremental commits with `Fixes #<id>` references, and converts the PR to "Ready for Review" once the milestone batch is complete (or targets `factory/issue-<id>` for single-issue dispatches).

**Blocked by:** 01: In-Sandbox GitHub Issue Tracker Provider and Pre-Flight Guard

**Status:** ready-for-agent

- [ ] When the assembly line claims a work item, the GitHub issue is marked with `factory:claimed`.
- [ ] After deterministic verification and code review pass, the ticket commit is pushed to the feature branch and an audit comment containing the plan, test outputs, reviewer verdict, and commit SHA is posted to the GitHub issue with label `factory:resolved`.
- [ ] If a ticket fails after exhausting retries, it is labeled `factory:ready-for-human`, diagnostic logs are posted to the issue, an alert is added to the pull request, and execution halts safely.
- [ ] The assembly line automatically creates a Draft Feature Pull Request targeting `main` upon the first resolved ticket of a feature, linking `Fixes #<id>`.
- [ ] Each subsequent ticket in the autonomous batch pushes to the branch and updates the PR description with its respective issue link.
- [ ] When all frontier tickets in the milestone are resolved, the harness automatically marks the Feature Pull Request as "Ready for Review" (`draft: false`) and posts an overall summary table.
- [ ] When dispatched with a single ad-hoc issue ID without a milestone, the harness operates on branch `factory/issue-<id>` and opens an isolated pull request.
- [ ] Automated integration tests verify the multi-ticket batch lifecycle, PR creation, incremental updates, and finalization against a mock GitHub API boundary.
