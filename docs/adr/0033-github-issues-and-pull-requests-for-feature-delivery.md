# GitHub Issues and Pull Requests for Feature Delivery

**Status**: Accepted (Amends [ADR 0028](0028-target-repo-ticket-colocation-and-in-sandbox-batch-execution.md))

To transition from filesystem-based task tracking (`.scratch/`) to cloud-native GitHub collaboration, we decided to introduce an `IssueTracker` provider abstraction, adopting GitHub Issues, Milestones, Labels, and Draft Pull Requests as the primary delivery mechanism—starting with the canonical Test Organization (`software-factory-09-test`).

## Considered Options

- **Retaining `.scratch/` in Target Repositories (ADR 0028)**: Storing feature specifications and markdown tickets in Git under `.scratch/<feature>/`. Superseded for GitHub workflows because it duplicates task management across Git files and remote issue trackers, clutters repository file trees, and lacks native GitHub review integrations.
- **Host-Side GitHub API Orchestration**: Performing all GitHub Issue fetching, label toggling, and PR creation on the developer workstation or testing console before and after sandbox execution. Rejected because it introduces network coupling between the host and remote sandbox, complicates autonomous multi-ticket batch loops, and undermines crash resilience.
- **Immediate Issue Closure upon Agent Verification**: Closing the GitHub issue immediately when deterministic tests pass. Rejected because changes have not landed on `main` until human review and PR merge; linking `Fixes #<id>` in the Feature PR preserves standard GitHub trunk workflows.
- **Sandbox-Native GitHub Issue Tracker with Draft Feature PRs**: Accepted because the sandbox already receives `GH_TOKEN` via `secrets_org/software-factory-09-test/token`. Executing API operations in-sandbox via Node.js 24 native `fetch` allows autonomous batch loops to claim tickets, update audit comments, push commits to `factory/<feature>`, manage Draft PRs, and convert to Ready for Review upon completion without external host orchestration.

## Consequences

- An `IssueTracker` interface decouples the assembly line harness from storage engines, supporting both `GitHubIssueTracker` (default for `software-factory-09-test`) and `LocalScratchTracker` (legacy fallback).
- A Feature corresponds to a GitHub Milestone (or `feature:<slug>` label). Individual work items are GitHub Issues assigned to that milestone.
- An overarching feature specification is derived from the Milestone description or Epic issue body, while individual issue bodies provide ticket-level acceptance criteria.
- Ticket states are tracked via labels: `factory:ready`, `factory:claimed`, `factory:resolved`, and `factory:ready-for-human`. Dependencies between issues are declared via `Blocked by: #<id>` syntax in issue descriptions.
- The sandbox creates a Draft Feature Pull Request (`factory/<feature>` -> `main`) upon the first resolved ticket. When all frontier tickets pass verification, the PR is converted to "Ready for Review" with a summary table.
- If a ticket exhausts retries, it is labeled `factory:ready-for-human`, a detailed diagnostics comment is posted to the issue, the PR description is updated with an alert, and execution halts.
- For single-issue executions without a milestone, the sandbox operates on branch `factory/issue-<id>`.
- The Pre-flight Guard validates `GH_TOKEN`, confirms the presence of open issues in the target milestone, and verifies local domain documentation (`CONTEXT.md` or `GLOSSARY.md`), retiring `.scratch/` requirements for `software-factory-09-test`.
- The Factory Testing Console queries GitHub Milestones and Issues directly via GitHub API for `software-factory-09-test` repositories.
