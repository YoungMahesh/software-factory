# Spec: Factory Studio Feature Pull Request Visibility and In-Studio Merge Controls

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When using Factory Studio, developers collaborate with an autonomous software assembly line that implements frontend applications in TanStack Start. The underlying assembly line harness automatically creates a Draft Feature Pull Request on GitHub when work begins, updates it as tickets resolve, and marks it "Ready for Review" once all acceptance tests pass.

However, Factory Studio provides zero Pull Request UI or lifecycle visibility:
1. **Context Fragmentation & Lost Flow**: There is no link to the opened Feature Pull Request anywhere in the Factory Studio top control bar, chat timeline, or issue drawer. Developers must leave Factory Studio, open GitHub in a separate browser tab, locate the repository, and hunt for the active pull request.
2. **Missing Delivery Gate State**: Developers cannot see the current review status (`Draft`, `Ready for Review`, `Merged`, or `Conflict`) from within Studio. They have no immediate indication whether tests are still validating or if the feature is ready to land on `main`.
3. **No Direct Merge Capability**: Even after all deterministic tests pass and the pull request is marked Ready for Review, developers cannot merge the pull request into `main` from Factory Studio. They must navigate GitHub's pull request interface to execute the merge manually.
4. **Desynchronized Live Preview**: After a developer manually merges a pull request on GitHub, the running Unified Studio Sandbox remains stuck on the old feature branch until manually reconfigured, breaking the live "app builder" experience.

## Solution

Implement native **Feature Pull Request Visibility** and **In-Studio Merge Controls** in Factory Studio:

1. **Top Control Bar PR Pill & Action**:
   - A dedicated Pull Request button/badge in the Studio top control bar displaying the live status of the active feature pull request (`Draft`, `Ready for Review`, `Merged`, or `Conflict`).
   - Clicking the pill opens a quick action popover showing the PR title, number, target branch, a direct link to GitHub, and a guarded "Merge into main" action when ready.

2. **Conversational Delivery Gate Card**:
   - A reactive Delivery Gate Card rendered directly within the Studio Chat History.
   - Pinned to the active milestone or feature run, summarizing the pull request title, resolved work items, verifier test status, and an inline "Merge into main" control.
   - Updates reactively as the PR progresses from Draft to Ready for Review and Merged.

3. **In-Studio Squash Merge & Branch Deletion**:
   - Clicking "Merge into main" triggers a confirmation popover ("Merge {pr_title} into main?").
   - Upon confirmation, Factory Studio delegates a squash merge to GitHub's REST API, passing a clean commit title (`${pr.title} (#${pr.number})`) and formatted commit body containing `Fixes #<id>` directives for all resolved tickets.
   - Automatically deletes the remote feature branch (`factory/<feature>`) via GitHub Git Refs API to keep repository branches clean.
   - GitHub natively auto-closes all resolved tickets linked via `Fixes #` directives.

4. **Automated Live Preview & Sandbox Synchronization**:
   - Upon a successful merge, Factory Studio automatically issues an in-sandbox command (`git reset --hard && git clean -fd && git checkout main && git pull origin main`) inside the active Unified Studio Sandbox via process execution.
   - The Vite development server seamlessly hot-reloads the merged application without restarting the container, and Studio's active preview branch indicator updates to `main`.

5. **Safety Guards & Conflict Alerts**:
   - Merging is strictly disabled while the pull request is in `Draft` state or while the Assembly Line is actively executing.
   - If GitHub reports merge conflicts (`mergeable: false` or `mergeable_state: "dirty"`), Studio displays an amber/red `Conflict` status badge with an alert linking directly to GitHub's conflict resolution interface.

6. **Real-Time Telemetry & Durable Persistence**:
   - The in-sandbox assembly line pipeline emits structured `delivery_gate` telemetry events over the Agent Event Stream when initializing or finalizing delivery gates, providing immediate real-time UI updates without polling lag.
   - TanStack Query caches and refetches PR state on window focus, drawer open, and job completion, while SQLite Studio Database persists the Delivery Gate Card across browser refreshes.

## User Stories

1. As a developer using Factory Studio, I want to see a Pull Request indicator in the top control bar when a Feature Pull Request exists for the selected repository, so that I have persistent visibility into delivery status.
2. As a developer observing a running job, I want the Pull Request indicator to display a `Draft` badge while the assembly line is implementing tickets, so that I know the work is in progress and not yet ready to merge.
3. As a developer whose feature implementation has completed all verifier checks, I want the Pull Request indicator to transition to `Ready for Review`, so that I know the feature is verified and ready to land on `main`.
4. As a developer clicking the Pull Request button in the control bar, I want a popover showing the pull request number, title, source and target branches, and an external link to GitHub, so that I can inspect details on GitHub if desired.
5. As a developer viewing the chat timeline after an assembly line run, I want to see a prominent Delivery Gate Card summarizing resolved tickets and verifier outcomes, so that I have a clear conversational record of what was completed.
6. As a developer reviewing a verified feature, I want an "In-Studio Merge Control" button in the Delivery Gate Card and Control Bar popover, so that I can merge the code into `main` without leaving Factory Studio.
7. As a developer clicking "Merge into main", I want to see a confirmation dialog summarizing the merge action and target branch, so that I do not accidentally trigger a production merge.
8. As a developer confirming a merge, I want Factory Studio to execute a squash merge on GitHub, so that intermediate agent commits are squashed into a single clean commit on `main`.
9. As a developer confirming a merge, I want the squash commit message to include `Fixes #<id>` for each resolved issue, so that GitHub automatically closes the corresponding milestone issues upon merge.
10. As a developer confirming a merge, I want Factory Studio to automatically delete the remote feature branch on GitHub, so that obsolete factory branches do not accumulate.
11. As a developer whose pull request has been merged, I want the Pull Request indicator to display a purple `Merged` badge, so that I have immediate visual confirmation of success.
12. As a developer with an active Live Preview running in the Unified Studio Sandbox, I want the preview container to automatically checkout and pull `main` upon merge, so that my live preview continues running and immediately displays the merged state.
13. As a developer whose pull request is still in `Draft` state, I want the "Merge into main" button to be disabled with an explanatory tooltip, so that unverified work cannot be merged prematurely.
14. As a developer with an assembly line job actively running, I want the "Merge into main" button to be disabled, so that concurrent git operations and race conditions are prevented.
15. As a developer encountering a pull request with merge conflicts against `main`, I want to see a `Conflict` badge and an alert linking to GitHub's web conflict editor, so that I can resolve the conflict cleanly.
16. As a developer opening the Studio Issue Drawer, I want to see Pull Request status badges on milestone headers, so that I can track PR delivery alongside issue backlogs.
17. As a developer reloading the browser or returning to Factory Studio, I want the Pull Request status and Delivery Gate Card to persist and rehydrate from the database and GitHub API, so that my context is never lost.
18. As a developer executing a standalone issue dispatch (`factory/issue-<id>`), I want the same Pull Request visibility and merge controls as milestone feature dispatches, so that single-issue fixes enjoy the same seamless experience.
19. As a developer observing the Agent Event Stream, I want instant updates when the draft PR is created or marked ready for review without waiting for background HTTP polling, so that the UI feels snappy and responsive.
20. As a developer whose GitHub API request encounters a network error or rate limit, I want non-blocking error notifications with retry capability, so that temporary network blips do not crash the Studio workspace.

## Implementation Decisions

- **Domain Model Vocabulary**:
  All documentation and user interfaces strictly adhere to the domain glossary in `CONTEXT.md`:
  - **Feature Pull Request** (never "PR review", "factory PR", or "merge request").
  - **Delivery Gate Card** for the conversational card in the chat history.
  - **In-Studio Merge Control** for the interactive merge action.
  - **Feature Branch** (`factory/<feature>`) for the working branch.
  - **Unified Studio Sandbox** for the persistent preview container.

- **Backend REST Seams (`factory/ui/github.py` and `factory/ui/app.py`)**:
  - `GET /api/studio/repos/{repo}/pulls`: Fetches open and recently closed pull requests for the repository from GitHub. Supports optional query parameter `branch` to target a specific feature branch. Normalizes pull request status into `draft`, `ready_for_review`, `merged`, or `conflict` (when `mergeable` is false).
  - `POST /api/studio/repos/{repo}/pulls/{pull_number}/merge`: Executes a GitHub squash merge via `PUT /repos/{owner}/{repo}/pulls/{number}/merge`. Automatically constructs `commit_title` (`${title} (#${number})`) and derives `commit_body` containing `Fixes #<id>` lines parsed from the PR description. Upon successful merge, executes `DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}` to delete the feature branch.
  - Live sandbox sync hook: When the merge succeeds, if the target repository has an active Unified Studio Sandbox running in the Preview Registry, invokes `sandbox.exec("git", "reset", "--hard")`, `sandbox.exec("git", "clean", "-fd")`, `sandbox.exec("git", "checkout", "main")`, and `sandbox.exec("git", "pull", "origin", "main")`, updating the preview registry branch state to `main`.

- **In-Sandbox Telemetry Emitter (`sandbox/factory/pipeline.ts`)**:
  - Emits a structured telemetry event `delivery_gate` when `tracker.initializeDeliveryGate` succeeds (providing PR number, URL, branch, and `draft: true`).
  - Emits an updated `delivery_gate` event when `tracker.finalizeDeliveryGate` succeeds (providing PR number, URL, branch, and `ready_for_review: true`).
  - Transmitted through standard output via `__SF_EVENT__:` and broadcasted over the Job SSE stream to Factory Studio.

- **Frontend Component Architecture**:
  - **Top Control Bar Pull Request Pill**: A new button added to the header of `StudioView.tsx` displaying the current state badge. Clicking opens a dropdown popover with PR details, link to GitHub, and the In-Studio Merge Control.
  - **Delivery Gate Card Component**: A dedicated component rendered within the chat history for delivery gate events and persistent message records. Features an expandable summary of resolved issues, links to GitHub, and a guarded "Merge into main" button with confirmation state.
  - **Studio Context & Queries**: A new TanStack Query hook `useStudioPullRequestQuery(repo, branch)` providing cached PR state with automatic cache invalidation on job transitions and manual refresh.

- **Database Persistence (`factory/ui/db.py`)**:
  - Structured Delivery Gate cards are persisted to the `chat_messages` table with `role: "assistant"` and typed turn data `{"type": "delivery_gate", ...}`, ensuring durable display across sessions.

- **Squash Merge Commit Format Shape**:
  ```typescript
  interface SquashMergePayload {
    commit_title: string; // e.g. "feat(inventory-v1): Implement inventory dashboard (#4)"
    commit_message: string; // e.g. "Resolved work items:\n- Fixes #1: Setup layout\n- Fixes #2: Add metrics"
    merge_method: "squash";
  }
  ```

## Testing Decisions

- **What makes a good test**:
  Tests must exercise real external contracts (HTTP endpoints, database persistence, rendered user interfaces, and telemetry event parsing) rather than asserting internal private variables or mock mechanics.
- **Backend API & Service Testing (`tests/test_ui.py`)**:
  - Test `GET /api/studio/repos/{repo}/pulls` returns normalized pull request payloads with accurate status (`draft`, `ready_for_review`, `merged`).
  - Test `POST /api/studio/repos/{repo}/pulls/{number}/merge` executes squash merge with properly formatted commit title and `Fixes #` directives.
  - Test that branch deletion is invoked upon merge completion.
  - Test that in-sandbox git sync (`git checkout main && git pull`) is triggered on the active preview sandbox.
  - Test error handling when GitHub returns 409 conflict or mergeable is false.
- **Frontend Component & Integration Testing (`factory/ui/frontend/src/`)**:
  - Test `StudioView.test.tsx` renders the top bar PR pill with correct status badges.
  - Test `DeliveryGateCard` renders resolved issues and enables the merge button only when status is `ready_for_review`.
  - Test that clicking merge displays confirmation before dispatching the API request.
  - Test that merged status updates the live preview branch indicator to `main`.
- **Pipeline Telemetry Testing (`sandbox/factory/pipeline.test.ts`)**:
  - Test that `runAssemblyLinePipeline` emits `delivery_gate` telemetry events upon initializing and finalizing the delivery gate.
- **Prior Art**:
  - `tests/test_ui.py` for FastAPI Starlette `TestClient` API testing.
  - `factory/ui/frontend/src/views/StudioView.test.tsx` for React component and context integration tests.
  - `sandbox/factory/pipeline.test.ts` for in-sandbox assembly line pipeline verification.

## Out of Scope

- Merging non-feature pull requests (e.g. pull requests opened manually by external contributors outside the factory harness).
- Autonomous rebase conflict resolution: if merge conflicts exist, Studio displays a conflict alert linking to GitHub rather than attempting autonomous resolution.
- Pull request code review commenting from within Factory Studio: code review comments are performed on GitHub; Studio acts as the delivery and merge gate.

## Further Notes

- Documented in Architectural Decision Record `docs/adr/0047-factory-studio-pull-request-visibility-and-merge-controls.md`.
- Conforms to canonical glossary in `CONTEXT.md`.
