# 02: Factory Studio Issue Drawer and Top Bar Trigger

**What to build:** An interactive slide-over `IssueDrawer` component and top bar trigger in Factory Studio that enables developers to browse, search, and filter GitHub issues grouped by milestone, with strict dependency guards, "Grill & Align" conversational seeding, "Instant Dispatch" fast-build execution, and "Run Milestone" batch dispatch confirmation.

**Blocked by:** 01: Studio Dispatch API and GitHub Issue Normalization

**Status:** resolved

- [x] Top control bar in `StudioView` renders an "Issues" trigger button with a live badge displaying the count of open issues for the active repository.
- [x] Clicking the "Issues" button opens the slide-over `IssueDrawer` without interrupting live preview state or chat scroll history.
- [x] Issues are presented grouped by GitHub Milestone, with progress counts and an unassigned backlog section for standalone issues.
- [x] Filter controls support toggling between `Open`, `Closed`, and `All` issues, alongside a real-time text search filter matching numbers, titles, and labels.
- [x] Factory lifecycle labels (`factory:ready`, `factory:claimed`, `factory:resolved`, `factory:ready-for-human`) are displayed as distinct visual status pills.
- [x] Issues with open dependencies (`Blocked by: #...`) or active claims (`factory:claimed`) disable "Instant Dispatch" with an informative tooltip explanation, while keeping "Grill & Align" enabled.
- [x] Clicking "Grill & Align" closes the drawer and automatically submits the issue's full specification (title, description, acceptance criteria) into the Grilling Assistant chat timeline.
- [x] Clicking "Instant Dispatch" invokes `POST /api/studio/dispatch` and updates the active job and live preview.
- [x] Milestone headers include a "Run Milestone" button that reveals a confirmation popover summarizing ticket counts and the target branch before triggering batch dispatch.
- [x] Issue queries use TanStack Query with automatic invalidation on drawer open, job completion, and via a manual refresh button.
- [x] Frontend test suites verify drawer opening/closing, filtering, dependency disabling, popover confirmations, and dispatch actions.
