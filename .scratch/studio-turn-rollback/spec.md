# Spec: Studio Turn Rollback and In-Place Reversion

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

In Factory Studio, developers explore and generate frontend user interfaces through conversational prompts evaluated and implemented by an autonomous multi-agent assembly line. Although the Coder Agent generates TypeScript and CSS code that passes deterministic verification and reviewer audit gates, it frequently makes visual, stylistic, or layout choices that take the UI in an undesirable direction (e.g. broken responsive padding, dissonant typography, or incorrect color palettes).

Currently, Studio Chat History offers no mechanism to undo a conversational turn or rewind code changes to a previous version. If a prompt results in an undesirable visual state, developers must manually prompt the agent with compensatory reverse instructions (often creating cumulative regressions) or manually clone the target repository to run git commands in a terminal. This lack of an instant rollback capability breaks frontend design velocity and discourages bold visual experimentation.

## Solution

Implement **Turn Rollback** in Factory Studio, providing developers with an instant, safe, and transparent mechanism to undo the code changes and tracking state of a completed turn:

1. **Dual UI Trigger Affordances**:
   - Provide an inline **"Undo Turn"** button on completed Assistant Response Cards and Delivery Gate Cards in Studio Chat History.
   - Provide a prominent **"Undo Last Turn"** button in the Live Preview top toolbar (adjacent to the Live Preview Branch Selector and Trunk Synchronization button) and Prompt Composer.
   - Guard every rollback trigger with a descriptive confirmation modal summarizing the target issue, commit SHA, and impacted branch.

2. **Safe Forward Git Revert**:
   - Execute a clean `git revert --no-edit <commit_sha>` on the active feature branch (`factory/<feature>`) and push to `origin/<branch>`, preserving linear Git history and PR commit auditability without destructive force-pushes.
   - If an unexpected merge conflict occurs during revert, immediately execute `git revert --abort`, preserve a clean workspace, stream diagnostic errors to dev server logs, and return an actionable HTTP 400 error.

3. **In-Place Unified Studio SandboxDev Server Synchronization**:
   - Orchestrate the revert directly inside the active Unified Studio Sandbox via in-container process execution (`sandbox.exec`).
   - Detect if `package.json` or `pnpm-lock.yaml` changed in the reverted diff and run `pnpm install --prefer-offline` automatically.
   - Emit a real-time SSE `preview_refresh` event to trigger instant Vite Hot Module Replacement (HMR) or iframe reload (0-second cold start).
   - If the sandbox is stopped or idle, automatically boot the container before executing the rollback.

4. **Issue Tracker & Pull Request Lifecycle Coordination**:
   - For GitHub Issue Tracker: Reopen the associated issue, reset its triage label to `ready-for-agent`, and append an automated audit comment explaining the rollback. The Feature Pull Request automatically reflects the revert commit in its diff.
   - For Local Markdown Issue Tracker: Reset the ticket status line to `ready-for-agent` and remove the resolved commit reference in `.scratch/<feature>/`.
   - Concurrency Guard: Strictly disable rollback (HTTP 409) while an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`).
   - Merge Guard: Strictly lock and disable rollback (HTTP 400) if the Feature Pull Request has already been merged into `main` via In-Studio Merge Control.

5. **Durable Append-Only Studio Chat History**:
   - Update the original message record in SQLite with a `reverted` metadata flag.
   - Visually mark the reverted turn card in Chat History with a distinct `Reverted` badge and disable obsolete approval/merge action buttons.
   - Append an explicit `Turn Rollback Card` in chat history ("↩️ Rolled back turn for Issue #<num> (commit `<sha>` ➔ `<revert_sha>`). Live Preview restored to previous version.") to maintain complete conversational context.

## User Stories

1. As a frontend developer using Factory Studio, I want an "Undo Last Turn" button in the Live Preview toolbar, so that I can quickly roll back a prompt that took the UI in the wrong visual direction.
2. As a frontend developer reviewing chat history, I want an inline "Undo Turn" button on the Delivery Gate Card of a completed turn, so that I can roll back a specific turn directly from its conversational card.
3. As a developer clicking an undo action, I want a confirmation modal detailing the issue title, commit SHA, and branch being reverted, so that I cannot accidentally roll back code without understanding the scope.
4. As a developer confirming a rollback, I want the system to execute a non-destructive `git revert` commit rather than a force-push reset, so that my repository maintains a clean, linear, and auditable history.
5. As a developer with a running Live Preview dev server, I want the rollback to execute in-place inside the active Unified Studio Sandbox, so that the preview updates instantly via Hot Module Replacement without a 30–60 second container restart.
6. As a developer rolling back a turn that installed an npm dependency, I want the system to detect changes in `package.json` or `pnpm-lock.yaml` and run `pnpm install`, so that the dev server does not throw missing module errors after reversion.
7. As a developer whose turn is rolled back, I want the associated GitHub Issue to be automatically reopened with a `ready-for-agent` label, so that I can refine my prompt and re-dispatch the work item.
8. As a developer whose turn is rolled back, I want an automated comment posted to the reopened GitHub Issue, so that the issue history explains why it was reopened and which commit was reverted.
9. As a developer tracking feature progress via Local Markdown Issue Tracker, I want the local ticket markdown file to update back to `ready-for-agent` and remove the resolved commit SHA, so that local tracker parity is maintained.
10. As a developer observing an active Assembly Line Pipeline job, I want the rollback controls to be strictly disabled with a lock icon and tooltip, so that I cannot mutate the working tree while agents are generating code.
11. As a developer inspecting a Feature Pull Request that has already been merged into `main`, I want the rollback button to be disabled with a notice indicating that merged turns cannot be rolled back, so that trunk integrity is protected.
12. As a developer whose rollback completes successfully, I want to see an append-only Turn Rollback Card in Studio Chat History, so that I can see the audit trail of what was attempted and rolled back.
13. As a developer reviewing past turns, I want reverted assistant cards to display a visual `Reverted` badge, so that I can distinguish active code turns from rolled-back turns at a glance.
14. As a developer viewing a reverted turn card, I want its merge and approval buttons to be permanently disabled, so that I cannot trigger conflicting operations on superseded turns.
15. As a developer with the Unified Studio Sandbox currently stopped, I want triggering a rollback to auto-boot the sandbox and execute the revert, so that I do not need to manually start the preview first.
16. As a developer encountering an unexpected git merge conflict during revert, I want the system to automatically abort the revert and keep the repository clean, so that no corrupted half-reverted state is left behind.
17. As a developer encountering a revert failure, I want an actionable error message and dev server log output, so that I can diagnose why the revert could not be cleanly applied.
18. As a developer completing a rollback, I want the Live Preview iframe to automatically refresh via Server-Sent Events, so that I do not need to manually click the browser refresh button.
19. As a developer using sequential linear rollbacks, I want to undo multiple turns step-by-step in reverse chronological order, so that I can step back through my design history incrementally.
20. As a developer reloading or re-opening Factory Studio, I want all reverted turn states and rollback cards to rehydrate durably from the SQLite database, so that session history remains persistent across browser restarts.

## Implementation Decisions

- **Domain Glossary Consistency**:
  All models, endpoints, schemas, and UI elements strictly adhere to domain terms defined in `CONTEXT.md`:
  - **Turn Rollback**: The atomic reversal of a completed code-producing conversational turn, its git commit, in-container dev server state, and tracking metadata.
  - **Unified Studio Sandbox**: The persistent Modal execution environment hosting dev server and agent processes.
  - **Studio Chat History**: The durable SQLite chronological conversation stream.
  - **Feature Branch**: The shared Git branch (`factory/<feature>`) aggregating feature commits.
  - **Delivery Gate Card**: The conversational card displaying PR status and commit verdicts.

- **Backend REST Seam (`factory/ui/app.py`)**:
  - `POST /api/studio/repos/{repo}/turns/rollback`:
    - Request Body Schema:
      `message_id`: Optional string identifying the specific assistant message to roll back. Defaults to the latest completed code-producing turn on the active branch.
      `branch`: Optional target branch string. Defaults to active preview branch.
    - Concurrency Safety Guard: Validates that no job is `RUNNING` or `QUEUED` for the repository. Returns HTTP 409 on collision.
    - Merge Guard: Checks if the Feature Pull Request associated with the turn is already `merged`. Returns HTTP 400 on collision.
    - Container Orchestration: Checks if the Unified Studio Sandbox is actively serving. If stopped/idle, calls preview launch and waits for serving. Executes in-place `git revert --no-edit <commit_sha>` and `git push origin <branch>` via container process execution.
    - Conflict Recovery: If exit code is non-zero, executes `git revert --abort` inside the container, streams stderr to preview dev server logs, and raises HTTP 400.
    - Diff-Aware Dependency Sync: Checks git diff between old and new HEAD for `package.json` or `pnpm-lock.yaml`. If detected, runs `pnpm install --prefer-offline`.
    - SSE Broadcast: Emits SSE `preview_refresh` event to reload the preview iframe.
    - Issue Tracker Update: Reopens GitHub Issue, removes `resolved` label, adds `ready-for-agent` label, and posts audit comment. For local tracker, rewrites ticket status to `ready-for-agent` and removes Commit line.
    - Response Body Schema:
      `success`: boolean
      `branch`: string
      `original_commit`: string (short SHA)
      `revert_commit`: string (short SHA)
      `issue_number`: optional integer/string
      `message`: human-readable confirmation string

- **Database Relational Schema Updates (`factory/ui/db.py`)**:
  - Add `mark_chat_message_reverted(message_id, revert_commit_sha)` method to update `turn_data_json` with `{"reverted": true, "reverted_at": time.time(), "revert_commit": revert_commit_sha}`.
  - Persist new assistant message for `turn_rollback` card with `turn_data_json` containing `{"type": "turn_rollback", "original_message_id": message_id, "original_commit_sha": original_sha, "revert_commit_sha": revert_sha, "issue_number": issue_num, "branch": branch}`.

- **Frontend Component Seams (`factory/ui/frontend/`)**:
  - `StudioView.tsx`:
    - Renders `TurnRollbackCard` for messages with `turn_data.type === "turn_rollback"`.
    - Renders visual `Reverted` badge on assistant cards where `turn_data.reverted === true`.
    - Disables approval and merge controls on reverted cards.
    - Renders "Undo Turn" button in `DeliveryGateCard` header when the turn is unmerged and no job is running.
  - `LivePreview.tsx`:
    - Renders "Undo Last Turn" action button in preview top toolbar adjacent to the branch switcher and sync button.
    - Displays confirmation dialog before dispatching the rollback mutation.
    - Shows loading spinner and disables button while rollback is in flight.
  - `PromptComposer.tsx`:
    - Renders "Undo Last Turn" shortcut action in composer bar when a completed turn is available to revert.

## Testing Decisions

- **What Makes a Good Test**:
  - Tests must assert observable external behavior through high-level system seams (HTTP endpoints, database persistence, and DOM rendering) rather than mock internal private variables.
  - Assert that a valid rollback request creates a linear revert commit, synchronizes dev server state, reopens the issue tracker work item, updates SQLite chat history, and emits real-time refresh events.
  - Assert that concurrency guards (active job running) and merge guards (already merged into main) correctly reject rollback requests with HTTP 409 and HTTP 400.
  - Assert that git revert conflicts cleanly abort without corrupting the working tree.

- **Target Modules to Test**:
  - Backend Integration (`tests/test_ui.py`):
    - Test `POST /api/studio/repos/{repo}/turns/rollback` happy path: executes container revert, updates DB message, reopens GitHub issue, emits refresh.
    - Test active job rejection (HTTP 409).
    - Test merged PR rejection (HTTP 400).
    - Test revert conflict failure and `git revert --abort` recovery.
    - Test database methods for message reverting and rehydration.
  - Frontend Component Integration (`factory/ui/frontend/src/views/StudioView.test.tsx` & `LivePreview.test.tsx`):
    - Test rendering of "Undo Last Turn" in toolbar and "Undo Turn" on Delivery Gate Card.
    - Test confirmation dialog opening, cancellation, and execution.
    - Test rendering of `TurnRollbackCard` and `Reverted` status badge.
    - Test visual disabled state when active job is running or PR is merged.

- **Prior Art**:
  - Backend: `tests/test_ui.py` tests for `POST /api/studio/repos/{repo}/preview/sync` (Trunk Synchronization, ADR 0049) and `POST /api/studio/repos/{repo}/pulls/{pull_number}/merge` (In-Studio Merge Control, ADR 0047).
  - Frontend: `StudioView.test.tsx` and `LivePreview.test.tsx` testing branch switching, sync triggers, and Delivery Gate Card interactions.

## Out of Scope

- Cherry-picking and reverting arbitrary historical turns out-of-order across intermediate code edits (strictly sequential linear rewinds to prevent merge conflicts).
- Rolling back commits directly on `main` after a Feature Pull Request has been merged via In-Studio Merge Control (post-merge rollback belongs to trunk branch management).
- Rollback of non-code conversational turns (e.g. Grilling Assistant questionnaires that were not dispatched to the assembly line pipeline).
- Interactive 3-way merge conflict editor inside the web UI (if an automated revert conflicts, it is safely aborted and surfaced as an error).

## Further Notes

- References [ADR 0050: Studio Turn Rollback and In-Place Reversion](../../docs/adr/0050-studio-turn-rollback-and-in-place-reversion.md).
- Follows the established container orchestration patterns established in [ADR 0048](../../docs/adr/0048-live-preview-branch-selector-and-in-place-switching.md) and [ADR 0049](../../docs/adr/0049-live-preview-trunk-synchronization-and-in-place-resync.md).
