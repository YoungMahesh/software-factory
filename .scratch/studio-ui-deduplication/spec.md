# Specification: Factory Studio UI Telemetry & Header Chrome Deduplication

## Problem Statement

In Factory Studio, developers currently experience confusing visual clutter and redundant interactive controls in the top navigation and studio header areas:
1. **Duplicate Telemetry Triggers**: Right next to each other on the right side of the secondary header (`StudioHeader`), both an "Activity" button and a "Logs" button are rendered. Both buttons open the exact same slide-over Activity Drawer (one defaulting to the timeline tab, and the other opening the terminal logs tab).
2. **Duplicate Activity Drawer Entry Points**: There are two separate "Activity" buttons rendered on the screen simultaneously—one in the top navigation bar (`AppNavigation`) and another in the secondary studio header (`StudioHeader`).
3. **Duplicate Active Job Indicators**: When an assembly line pipeline job is active or completed, its execution stage is rendered twice on screen simultaneously: once in the top navigation bar (`• COMPLETED • v1-initial-app`) and once directly below it in a dark floating badge (`COMPLETED fa5b0b0cf6`).
4. **Duplicate Repository Indicators**: The active repository name is rendered twice within inches of each other: once as a static breadcrumb pill in the top navigation bar, and once as the interactive repository selection dropdown in the secondary header.
5. **Obsolete Leftover Routing**: The `onSwitchToConsole` callback prop remains wired across Studio components despite the standalone Testing Console view having been fully retired in ADR 0059.

## Solution

Consolidate all global workspace telemetry triggers, active job status indicators, and pipeline cancellation controls into the primary top navigation bar (`AppNavigation`), and remove redundant buttons and static indicators from both `AppNavigation` and `StudioHeader`:
1. Remove both the "Activity" button and "Logs" button from `StudioHeader`, establishing the top navigation "Activity" button as the single canonical entry point to the Activity Drawer.
2. Remove the second-row floating job badge (`#studio-floating-status-badge`) from `StudioHeader`.
3. Enrich the top navigation active job status pill in `AppNavigation`:
   - Display active pipeline stage, feature/repository name, and truncated job ID.
   - Make the entire pill clickable with hover feedback to open the Activity Drawer.
   - Embed an inline, non-propagating Cancel button (`XCircle`) when the job status is `RUNNING` to cancel the active pipeline run.
4. Remove the static repository breadcrumb pill from `AppNavigation`, allowing the `Current App` selection dropdown in `StudioHeader` to be the sole repository identifier and switcher.
5. Fully clean up the obsolete `onSwitchToConsole` callback from `StudioContext`, `StudioView`, `StudioHeader`, and `App`.

## User Stories

1. As a developer using Factory Studio, I want a single canonical "Activity" button in the top navigation bar, so that I don't see duplicate buttons opening the same slide-over drawer.
2. As a developer using Factory Studio, I want the top navigation "Activity" button to display a coral badge with the failed-commands counter, so that I am immediately alerted to non-zero exit codes.
3. As a developer using Factory Studio, I want the active job pill in the top navigation bar to display the job stage, target feature, and job ID, so that I have complete pipeline status at a glance without duplicate badges.
4. As a developer using Factory Studio, I want to click anywhere on the top navigation active job pill to open the Activity Drawer, so that I can quickly inspect pipeline progress without seeking out a separate button.
5. As a developer using Factory Studio, I want an inline Cancel button inside the active job pill when a pipeline run is in progress, so that I can immediately abort an executing job directly from the top navigation.
6. As a developer using Factory Studio, I want clicking the inline Cancel button to stop event propagation, so that canceling a job does not inadvertently trigger the slide-over Activity Drawer.
7. As a developer using Factory Studio, I want the secondary header (`StudioHeader`) to be free of floating status badges and redundant activity buttons, so that the header controls remain focused on repository selection, issue management, PR workflow, and preview execution.
8. As a developer using Factory Studio, I want the static repository pill removed from the top navigation bar, so that my screen space is not cluttered by duplicate repository indicators right above the repository selection dropdown.
9. As a developer maintaining the codebase, I want obsolete references to `onSwitchToConsole` removed across context and view components, so that the code reflects the consolidated single-view Studio architecture.

## Implementation Decisions

- **Top Navigation Canonicalization**: `AppNavigation` is the sole chrome component responsible for global application telemetry and active job state.
- **Top Navigation Active Job Pill Enhancement**:
  - Rendered when `activeJob` is present.
  - Styled with Cohere enterprise near-black pill styling (`bg-primary`, `rounded-pill`, `border-hairline/40`).
  - Displays a pulsing emerald dot, the uppercase stage name, a divider bullet, the feature or repository name, and the truncated job ID.
  - Interactive wrapper button/div with `cursor-pointer` and hover highlighting (`hover:bg-primary/90`) that invokes `onOpenDrawer()`.
  - When `activeJob.status === "RUNNING"`, includes an inline Cancel icon button (`XCircle`) with `e.stopPropagation()` calling `onCancelJob(activeJob.id)`.
- **Top Navigation Repository Pill Removal**:
  - Remove `<div className="..."><GitBranch ... /> <span>{selectedRepo || "no-repo"}</span></div>` from `AppNavigation`.
- **Secondary Header Streamlining (`StudioHeader`)**:
  - Remove `#studio-floating-status-badge` and its nested elements (`studio-badge-stage-text`, `studio-badge-job-detail`, `btn-studio-activity`, `btn-inspect-logs`, `btn-studio-cancel`).
  - Remove props `onSwitchToConsole`, `onOpenDrawer`, and `onCancelJob` from `StudioHeaderProps`.
- **Context & Hook Cleanup**:
  - Remove `onSwitchToConsole` from `StudioContextValue` in `StudioContext.tsx`.
  - Pass `onCancelJob` to `AppNavigation` from `StudioContext` (or as a direct prop in `App.tsx`).
  - Remove `onSwitchToConsole` implementation from `App.tsx` and usages in `StudioView.tsx`.
- **Freshness and Compilation**:
  - Recompile production bundle via `pnpm --dir factory/ui/frontend build` to synchronize `factory/ui/static/dist/`.

## Testing Decisions

- **Testing Seams**: Test at the highest component and view integration seams using `@testing-library/react` and Vitest:
  - `AppNavigation.test.tsx`:
    - Assert `AppNavigation` renders the canonical `Activity` button with `nav-activity-drawer-btn` test ID.
    - Assert `AppNavigation` renders the active job pill when `activeJob` is provided.
    - Assert clicking the active job pill invokes `onOpenDrawer`.
    - Assert when `activeJob.status === "RUNNING"`, an inline Cancel button is rendered and clicking it invokes `onCancelJob` without invoking `onOpenDrawer`.
    - Assert the static repository pill (`no-repo` / repository name) is no longer rendered in `AppNavigation`.
  - `StudioView.core.test.tsx` / `StudioHeader` tests:
    - Assert `StudioHeader` no longer renders `studio-floating-status-badge`, `btn-studio-activity`, `btn-inspect-logs`, or `btn-studio-cancel`.
    - Assert repository dropdown, New App button, Issues button, and Preview App controls render properly without layout regression.
- **Production Freshness Verification**:
  - Execute `pytest tests/test_ui/test_frontend_dist_freshness.py` to ensure static dist assets are recompiled and committed cleanly.

## Out of Scope

- Changes to the internal tabs or contents of `ActivityDrawer` (Timeline, Terminal Logs, Bottlenecks, Failed Commands, History remain intact).
- Changes to preview controls in `StudioHeader` or `LivePreviewToolbar` (Preview App, Stop, Reload remain intact).
- Backend REST API route modifications.

## Further Notes

- Adheres strictly to the Universal File Line Budget (<= 500 physical lines for all modified and newly created files per ADR 0051 and ADR 0057).
- Preserves the Cohere Editorial Design System tokens and pill geometry per ADR 0053.
