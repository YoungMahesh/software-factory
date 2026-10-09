# Spec: GitHub Issues and Pull Requests for Feature Delivery

Status: ready-for-agent

## Problem Statement

Target repositories currently require local filesystem task tracking under `.scratch/<feature>/` (specifications in `spec.md` and work items in `issues/NN-*.md`). While functional for local development, this model:
1. Pollutes version control trees in external target repositories with internal agent planning files.
2. Disconnects feature development from standard GitHub developer workflows, where issues, milestones, and pull requests provide collaboration, code review, and tracking.
3. Obscures progress from external team members who cannot view or comment on in-progress tickets without cloning the repository or inspecting git commit logs.
4. Couples the Factory Testing Console and sandbox pre-flight checks to inspecting Git tree directories instead of native GitHub APIs.

## Solution

Replace the local `.scratch/` filesystem requirement with native GitHub Issues, Milestones, and Pull Requests for feature delivery—focusing initially on the canonical Test Organization (`software-factory-09-test`).

The solution introduces:
1. **Issue Tracker Provider Interface**: An abstraction within the assembly line harness that decouples ticket discovery, claiming, and resolution from storage engines, supporting both `GitHubIssueTracker` and `LocalScratchTracker`.
2. **GitHub-Backed Delivery Hierarchy**:
   - A **Feature** corresponds to a GitHub Milestone (or `feature:<slug>` label).
   - An overarching **Feature Specification** is read from the Milestone description or an Epic/Spec tracking issue.
   - **Tickets / Work Items** are GitHub Issues assigned to the milestone.
   - Dependencies between tickets are declared via `Blocked by: #<id>` in issue descriptions.
   - Status transitions are recorded via GitHub Labels: `factory:ready`, `factory:claimed`, `factory:resolved`, and `factory:ready-for-human`.
3. **Feature Pull Request Quality Gate**:
   - The assembly line opens a Draft Pull Request (`factory/<feature>` -> `main`) upon the first resolved ticket.
   - Each ticket commit is pushed to the feature branch and links `Fixes #<id>` in the PR description.
   - Detailed audit summaries (plan, verifier log, reviewer verdict, commit SHA) are posted directly as comments on the respective GitHub Issue.
   - On batch completion, the Draft PR is converted to "Ready for Review" with a summary table.
   - If retries are exhausted, the issue is labeled `factory:ready-for-human`, failure diagnostics are posted to the issue, an alert is appended to the PR, and the batch halts.
4. **Updated Pre-Flight Guard**:
   - Validates `GH_TOKEN` environment variable and connectivity.
   - Verifies that the target milestone/feature exists and has candidate issues.
   - Enforces local domain documentation (`CONTEXT.md` or `GLOSSARY.md`), removing `.scratch/` file requirements for `software-factory-09-test`.
5. **Factory Testing Console Enhancement**:
   - Queries GitHub Milestones and Issues directly via GitHub API for `software-factory-09-test` repositories to populate feature dropdowns and issue lists.
   - Supports dispatching by Milestone, by Feature Label, or by ad-hoc single Issue number.

## User Stories

1. As a software engineer, I want to create a GitHub Milestone to define a feature and write the overall requirements in the milestone description, so that I don't have to write local `spec.md` files.
2. As a software engineer, I want to create GitHub Issues for individual work items under a Milestone, so that my team can collaborate on and prioritize tasks using familiar GitHub workflows.
3. As a developer, I want to declare dependencies using `Blocked by: #<id>` in the issue body, so that the factory automatically executes tickets in the correct topological order.
4. As an autonomous factory harness, I want to query GitHub for unblocked issues on the frontier of a milestone, so that I can execute work items sequentially inside a warm sandbox.
5. As an autonomous factory harness, I want to mark an issue with `factory:claimed` when beginning work, so that human maintainers and other runners know the work item is in progress.
6. As a human reviewer, I want the assembly line to post planning notes, verification logs, and reviewer audit verdicts as comments on the GitHub Issue, so that the entire decision trail is visible in the issue history.
7. As a project maintainer, I want the factory to create a Draft Feature Pull Request (`factory/<feature>` -> `main`) when the first ticket is resolved, so that changes are tracked in a single cohesive review unit.
8. As a project maintainer, I want each ticket commit to push incrementally to the feature branch, so that the Draft PR reflects real-time progress.
9. As a reviewer, I want the factory to automatically convert the Draft PR to "Ready for Review" once all milestone issues are resolved, so that I am notified when the feature is ready for final sign-off.
10. As a reviewer, I want the Feature PR description to contain `Fixes #<id>` links for all resolved issues, so that merging the PR automatically closes the issues on GitHub.
11. As a developer, I want a ticket that fails after maximum retries to be labeled `factory:ready-for-human` with error diagnostics posted to the issue, so that I can inspect why the agent got stuck.
12. As a developer, I want the Feature PR to display a visible warning if a ticket halts, so that nobody merges an incomplete or broken feature.
13. As a tester using the Factory Testing Console, I want to select a repository in `software-factory-09-test` and immediately see its open Milestones and Issues, so that I can launch tests without typing manual slugs.
14. As a tester using the Factory Testing Console, I want to enter an ad-hoc single Issue number to dispatch, so that I can test isolated bug fixes on branch `factory/issue-<id>`.
15. As a sandbox runner, I want in-sandbox GitHub API requests to use Node.js 24 native `fetch`, so that no extra npm packages or CLI binaries are required in the container.
16. As a developer running local tests, I want the codebase to retain a `LocalScratchTracker` fallback, so that existing unit tests and legacy fixtures continue to pass without network calls.
17. As an operator, I want the Pre-flight Guard to verify `GH_TOKEN` and remote milestone existence before starting agent stages, so that misconfigured jobs fail immediately with clear instructions.
18. As a security engineer, I want the GitHub token to be decrypted from `secrets_org/software-factory-09-test/token` into memory and never logged or written to unencrypted storage, so that repository credentials remain protected.

## Implementation Decisions

### Architectural Seams & Modules

- **Issue Tracker Abstraction Seam (`sandbox/factory/tracker/`)**:
  Introduce an `IssueTracker` interface decoupling storage from assembly line execution:
  - Methods: `validatePreflight()`, `getFeatureSpec()`, `getFrontierTickets()`, `claimTicket()`, `resolveTicket()`, `escalateTicket()`, `initializeDeliveryGate()`, `finalizeDeliveryGate()`.
  - Implementations:
    - `GitHubIssueTracker`: Handles GitHub REST communication (Milestones, Issues, Comments, Labels, PRs).
    - `LocalScratchTracker`: Wraps existing filesystem `.scratch/` parsing and file updating logic.
  - Factory selection: When repository environment includes an organization token or `--tracker github`, use `GitHubIssueTracker`; fallback to `LocalScratchTracker` if `.scratch/` is detected.

- **In-Sandbox GitHub REST Client (`sandbox/factory/github.ts`)**:
  - Implemented using Node.js 24 native global `fetch`.
  - Authenticated via `GH_TOKEN` or `GITHUB_TOKEN`.
  - Endpoints:
    - Milestone & Issue querying: `GET /repos/{org}/{repo}/milestones`, `GET /repos/{org}/{repo}/issues`
    - Issue updates: `POST /repos/{org}/{repo}/issues/{id}/comments`, `PATCH /repos/{org}/{repo}/issues/{id}` (labels, state)
    - Pull Request operations: `POST /repos/{org}/{repo}/pulls`, `PATCH /repos/{org}/{repo}/pulls/{number}` (title, body, draft state)

- **Pre-flight Guard (`sandbox/factory/preflight.ts`)**:
  - Refactored to delegate issue tracking validation to the active `IssueTracker`.
  - For `GitHubIssueTracker`: Validates `GH_TOKEN`, confirms target milestone/issue exists, checks for `CONTEXT.md` or `GLOSSARY.md`.
  - For `LocalScratchTracker`: Retains existing `.scratch/<feature>/spec.md` and `issues/` directory checks.

- **Assembly Line Pipeline (`sandbox/factory/pipeline.ts` & `lifecycle.ts`)**:
  - Consumes `IssueTracker` instead of direct filesystem `fs.readFileSync` for tickets.
  - On first resolved ticket: Calls `tracker.initializeDeliveryGate()` to establish the Draft Feature PR.
  - On ticket resolution: Commits code, pushes branch, calls `tracker.resolveTicket()` with audit summary and commit SHA.
  - On failure/escalation: Calls `tracker.escalateTicket()` with error trace and diagnostics.
  - On batch finish: Calls `tracker.finalizeDeliveryGate()` to mark the PR Ready for Review.

- **Factory Testing Console (`factory/ui/github.py` & `app.py`)**:
  - Replaces tree-based `.scratch/` scanning for `software-factory-09-test` with direct GitHub API calls:
    - `fetch_repo_milestones_and_issues(repo, token, org)`
  - Adds endpoints: `/api/repos/{repo}/milestones` returning milestones and their associated issues.
  - Updates web UI template to populate the feature selector with milestones and display issue numbers with labels.

- **Container Entrypoint (`shared/factory_entrypoint.sh`)**:
  - Continues to decrypt `secrets_org/software-factory-09-test/token` to `GH_TOKEN` / `GITHUB_TOKEN`.
  - Passes `--feature` (milestone slug) and optional `--issue` to the pipeline harness.
  - If `--issue` is provided without a milestone, sets branch to `factory/issue-<id>`.

## Testing Decisions

- **Test Principles**:
  - Test external behavior and contracts, not internal API mock counts or helper trivia.
  - Ensure end-to-end assembly line batching works identically with both `LocalScratchTracker` and `GitHubIssueTracker`.
  - Mock external GitHub HTTP endpoints at the network boundary (e.g. global `fetch` mock or local HTTP server) rather than mocking internal class methods.

- **Modules Tested**:
  1. `GitHubIssueTracker` & `GitHubClient`: Verify fetching issues, parsing `Blocked by: #<id>`, computing the unblocked frontier, posting audit comments, creating Draft PRs, and finalizing PRs.
  2. `PreflightGuard`: Test success and failure cases with valid/missing `GH_TOKEN`, valid/empty milestones, and missing `CONTEXT.md`.
  3. `AssemblyLinePipeline`: Test full multi-ticket batch loop with simulated stages, verifying that PR creation, commit pushes, and ticket resolution comments are invoked in proper order.
  4. `FactoryTestingConsole (github.py)`: Verify GitHub milestone and issue parsing with mock responses and fallback error states.

- **Prior Art**:
  - `sandbox/factory/pipeline.test.ts`: Autonomous batch execution test suite.
  - `sandbox/factory/preflight.test.ts`: Prerequisite validation test suite.
  - `tests/test_ui.py`: FastAPI routes and GitHub client tests.

## Out of Scope

- GitHub Webhook or Event-Driven listeners (Modal continues to run on-demand via Testing Console or CLI Dispatcher).
- Automatic PR merging (PRs are marked "Ready for Review"; human maintainers perform the final merge).
- Multi-repository cross-milestone batching (sandboxes operate on a single target repository per run).
- Complete removal of `LocalScratchTracker` (retained for backward compatibility and offline testing).

## Further Notes

- Canonical domain documentation in `CONTEXT.md` and ADR `0033-github-issues-and-pull-requests-for-feature-delivery.md` govern all terminology and architectural constraints.
