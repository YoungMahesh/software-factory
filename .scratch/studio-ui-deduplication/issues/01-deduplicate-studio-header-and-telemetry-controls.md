# 01: Deduplicate Factory Studio Header Chrome and Telemetry Controls

**What to build:** Consolidate active job status, cancellation, and Activity Drawer triggers into `AppNavigation`, remove redundant `Activity` / `Logs` buttons, floating status badge, and static repository pill from `StudioHeader` and `AppNavigation`, clean up obsolete `onSwitchToConsole` references, and recompile the static production bundle.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Update `AppNavigation.tsx`:
  - Enhance active job indicator with job ID, clickable trigger invoking `onOpenDrawer()`, and an inline `Cancel` button (`XCircle`) when `activeJob.status === "RUNNING"` that invokes `onCancelJob(activeJob.id)` with `e.stopPropagation()`.
  - Remove static repository pill (`<GitBranch /> {selectedRepo || "no-repo"}`) from the header right section.
  - Wire `onCancelJob` via props and/or `StudioContext`.
- [ ] Update `StudioHeader.tsx`:
  - Remove `#studio-floating-status-badge` and its nested elements (`btn-studio-activity`, `btn-inspect-logs`, `btn-studio-cancel`, and stage/id chips).
  - Remove obsolete `onSwitchToConsole`, `onOpenDrawer`, and `onCancelJob` props from `StudioHeaderProps`.
- [ ] Clean up `StudioContext.tsx`, `StudioView.tsx`, and `App.tsx`:
  - Remove obsolete `onSwitchToConsole` from `StudioContextValue`, `useStudio`, and `App.tsx`.
  - Remove unused props passed to `StudioHeader` in `StudioView.tsx`.
- [ ] Update and expand automated tests:
  - Update `AppNavigation.test.tsx` and `App.navigation.test.tsx` to verify the enhanced clickable job pill, inline cancel button with stopped propagation, drawer invocation, and absence of the static repository pill.
  - Update `StudioHeader` and `StudioView` tests to verify clean rendering without the floating badge or duplicate activity/logs buttons.
  - Verify all modified TypeScript/Python files adhere to the <= 500 lines budget.
- [ ] Run `pnpm --dir factory/ui/frontend build` to recompile `factory/ui/static/dist/` and run `pytest tests/test_ui/test_frontend_dist_freshness.py` and `pnpm --dir factory/ui/frontend test` to ensure 100% passing tests with zero bundle divergence.
