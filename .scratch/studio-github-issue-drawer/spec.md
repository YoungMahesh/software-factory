# Spec: Factory Studio GitHub Issue Drawer and Unified Dispatch

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

In Factory Studio, developers can iteratively build frontend applications using natural language prompts evaluated by the Grilling Assistant and previewed live on the Unified Studio Sandbox. However, target repositories already track structured specifications, bug reports, acceptance criteria, and milestones as GitHub Issues in the Test Organization.

Currently, developers cannot view or interact with these GitHub issues from within Factory Studio:
1. **Context Fragmentation**: Developers must leave Factory Studio and browse GitHub in a separate browser tab to see what work items, bugs, or feature tickets exist for the active repository.
2. **Manual Copy-Pasting**: To implement a GitHub issue, a developer must manually copy the title, description, and acceptance criteria from GitHub and paste them into the Prompt Composer.
3. **No Direct Execution Path for Pre-Specified Tickets**: Well-specified GitHub issues that already contain deterministic acceptance criteria are forced through conversational grilling rounds unless the user manually toggles Fast Build, even when no further interview is necessary.
4. **No Milestone Batch Dispatch in Studio**: Although the backend assembly line harness supports autonomous feature batching across a milestone, Studio has no way to trigger a milestone batch run while bound to the live preview.
5. **No Dependency Visibility**: Developers cannot see which tickets are ready for work versus blocked by open dependencies (`Blocked by: #...`) or already claimed by running jobs (`factory:claimed`).

## Solution

Implement the **Studio Issue Drawer**—a slide-over interface within Factory Studio that presents GitHub issues for the active repository with dual execution paths (**Grill & Align** vs. **Instant Dispatch**), dependency guards, milestone batching, and Unified Studio Sandbox branch binding:

1. **Studio Issue Drawer (`Studio Issue Drawer`)**:
   - A slide-over panel opened from an "Issues" button in the Factory Studio top control bar, featuring a live badge displaying the count of open issues.
   - Preserves the dual-pane Chat Conversation and Live Preview layout without permanent horizontal space consumption.
2. **Milestone Grouping & Backlog Partitioning**:
   - Issues are organized by GitHub Milestone, showing milestone progress, issue counts, and title.
   - Standalone issues without an assigned milestone are presented in a dedicated "Backlog / Unassigned" section.
3. **Filtering, Searching, & Status Badging**:
   - Filter toggle between `Open` (default), `Closed`, and `All` issues.
   - Text search filter matching issue numbers, titles, and labels.
   - Visual status badges for factory lifecycle states (`factory:ready`, `factory:claimed`, `factory:resolved`, `factory:ready-for-human`).
4. **Dual Action Execution Model**:
   - **Grill & Align**: Closes the drawer and automatically submits the full issue specification (title, description, acceptance criteria) to the Grilling Assistant (`grill=true`), initiating an interview round in the chat timeline to stress-test requirements and produce an Architectural Decision Record (ADR) before building.
   - **Instant Dispatch**: Bypasses the Grilling Assistant for well-specified tickets and immediately dispatches the Assembly Line Pipeline on `factory/<milestone-slug>` (or `factory/issue-<number>`), attaching to the Unified Studio Sandbox and updating the live preview.
5. **Dependency & Claim Guards**:
   - Issues with open dependencies (`Blocked by: #...`) or active claims (`factory:claimed`) disable the "Instant Dispatch" button with a clear explanatory tooltip, while keeping "Grill & Align" accessible.
6. **Milestone Batch Dispatch with Pre-flight Confirmation**:
   - Milestone headers include a "Run Milestone" button that opens a pre-flight popover summarizing ready vs. blocked issues before launching an Autonomous Feature Batch.
7. **Unified Studio Dispatch Endpoint (`POST /api/studio/dispatch`)**:
   - Dedicated backend endpoint connecting directly to the Unified Studio Sandbox preview, synchronizing the target branch, and persisting a structured dispatch card to the SQLite Studio Database (`chat_messages`).
8. **Automatic Cache Revalidation**:
   - Managed via TanStack Query, automatically invalidating issue state when the drawer opens or when an assembly line run completes, supplemented by a manual refresh button.

## User Stories

1. As a developer in Factory Studio, I want to see an "Issues" button in the top bar with the count of open issues, so that I immediately know how many tickets exist for the active repository.
2. As a developer clicking the "Issues" button, I want a slide-over drawer to open without resetting or obscuring my live preview or chat scroll position, so that my development workflow is not interrupted.
3. As a developer browsing issues, I want them grouped by their GitHub Milestone, so that I can see issues in the context of their overarching feature.
4. As a developer with standalone tickets, I want to see an unassigned backlog section, so that issues without milestones are easily discovered.
5. As a developer triaging work, I want to filter issues by `Open`, `Closed`, and `All`, so that I can focus on pending work or verify previously resolved tasks.
6. As a developer searching for a specific bug, I want a search input that filters by issue number, title, or label in real time, so that I can quickly find the exact ticket I need.
7. As a developer, I want to see factory lifecycle labels (`factory:ready`, `factory:claimed`, `factory:resolved`, `factory:ready-for-human`) rendered as distinctive badges, so that I understand which agent stage or status the issue is in.
8. As a developer with a complex issue requiring architectural alignment, I want a "Grill & Align" button that loads the issue description into the Grilling Assistant, so that the assistant interviews me and drafts an ADR before any code is modified.
9. As a developer clicking "Grill & Align", I want the drawer to close automatically and start the interview turn in the chat timeline, so that I get immediate interactive feedback.
10. As a developer with an already well-specified bug or task, I want an "Instant Dispatch" button on the issue card, so that I can bypass the interview and execute the assembly line immediately.
11. As a developer viewing an issue that depends on another open issue (`Blocked by: #X`), I want the "Instant Dispatch" button disabled with an informative tooltip, so that I don't accidentally run tasks out of order.
12. As a developer viewing an issue currently claimed by a running job, I want "Instant Dispatch" disabled, so that multiple jobs do not conflict on the same ticket.
13. As a developer ready to deliver an entire feature milestone, I want a "Run Milestone" button on the milestone header, so that the factory can sequentially claim and resolve all unblocked tickets in an Autonomous Feature Batch.
14. As a developer clicking "Run Milestone", I want a confirmation popover displaying the count of ready vs. blocked tickets and the target branch, so that I can verify the batch execution plan before committing cloud compute.
15. As a developer dispatching an issue or milestone, I want a structured dispatch card to appear in the Studio Chat History, so that the action is permanently recorded across page reloads.
16. As a developer dispatching an issue belonging to a milestone, I want the assembly line to execute on branch `factory/<milestone-slug>` and hot-reload the Live Preview on that branch, so that my preview matches the active work.
17. As a developer dispatching a standalone issue without a milestone, I want the assembly line to execute on branch `factory/issue-<number>` and update the Live Preview accordingly, so that work is properly isolated.
18. As a developer, I want issue data to refresh automatically when an assembly line job finishes, so that resolved tickets update to `resolved` without requiring a hard browser reload.
19. As a developer making changes directly on GitHub, I want a manual "Refresh" button in the drawer header, so that I can pull the latest issues on demand.
20. As a developer working offline or with network delays, I want clean loading skeletons and graceful error states if the GitHub API fails or is rate-limited, so that the interface remains stable and responsive.

## Implementation Decisions

- **Studio Issue Drawer Component**:
  A slide-over sheet rendered in the studio view that docks to the right side of the screen with smooth CSS transitions, accessible via keyboard (Escape to close) and backdrop click. Contains search filtering, milestone accordions, issue cards, and dispatch actions.
- **Top Control Bar Integration**:
  The Studio top control bar displays an "Issues" button styled consistently with "Preview App", showing a badge with the count of open issues for the currently selected repository.
- **Issue Card Structure & Action Seams**:
  Each card displays the issue number, title, expandable body preview, factory status pills, blocker alerts, and two primary action buttons: "Grill & Align" and "Instant Dispatch" (guarded by dependency checks).
- **Milestone Batch Confirmation Popover**:
  Clicking "Run Milestone" toggles an inline floating popover summarizing total, ready, blocked, and resolved tickets with explicit "Confirm Batch" and "Cancel" buttons.
- **Dedicated Dispatch API Seam (`POST /api/studio/dispatch`)**:
  A specialized FastAPI endpoint dedicated to Studio issue and milestone dispatches. Resolves milestone slugs and branches, ensures the Unified Studio Sandbox preview is active on that branch, starts the job in `dev=True` mode, and records a structured dispatch entry in SQLite `chat_messages`.
- **Issue Data Normalization**:
  The GitHub issue normalization layer extracts milestone metadata (`number`, `title`, `slug`) alongside labels, bodies, and blocker IDs, enabling accurate client-side grouping without redundant network requests.
- **TanStack Query Invalidation & Stale Time**:
  Issues for the selected repository are cached under a dedicated query key with a 30-second stale time, invalidated automatically on drawer open, repository change, and job completion events.

## Testing Decisions

- **Good Test Principle**:
  Tests must assert user-visible behaviors, HTTP contracts, and database persistence—never internal private methods or implementation details.
- **Backend API Seam Testing**:
  - Test `POST /api/studio/dispatch` via `starlette.testclient.TestClient` against an in-memory SQLite database (`:memory:`).
  - Verify that dispatching an issue with a milestone binds the job to `factory/<milestone_slug>` and attaches the preview URL.
  - Verify that dispatching a standalone issue binds to `factory/issue-<number>`.
  - Verify that dispatching records a structured assistant card in `chat_messages`.
  - Verify that issue normalization properly parses milestones and blockers.
- **Frontend Component & View Seam Testing**:
  - Test `IssueDrawer.tsx` in Vitest using `@testing-library/react`.
  - Test filtering between Open, Closed, and All issues.
  - Test real-time search filtering by issue title and number.
  - Test that "Instant Dispatch" is disabled when `blocked_by` contains open issues.
  - Test that clicking "Grill & Align" triggers prompt submission and closes the drawer.
  - Test that clicking "Run Milestone" reveals the confirmation popover before invoking batch dispatch.
- **Prior Art**:
  - Backend prior art: `tests/test_ui.py` and `tests/test_ui_db.py`.
  - Frontend prior art: `factory/ui/frontend/src/components/ActivityDrawer.test.tsx` and `factory/ui/frontend/src/views/StudioView.test.tsx`.

## Out of Scope

- Creating new GitHub issues from within the drawer (issue creation continues through conversational grilling and plan approval).
- Editing or deleting existing GitHub issues directly inside the drawer.
- Assigning GitHub users or changing arbitrary non-factory GitHub labels.
- Native GitHub project board column dragging.

## Further Notes

- Governed by [ADR 0042: Factory Studio GitHub Issue Drawer and Unified Dispatch](file:///root/software-factory/docs/adr/0042-factory-studio-github-issue-drawer-and-dispatch.md).
- Follows domain terminology defined in [CONTEXT.md](file:///root/software-factory/CONTEXT.md).
