# 03: Navigation Bar Error Counter Badge and Production Bundle

**What to build:** A visual error counter badge on the main navigation bar Activity Drawer button alerting developers to failed commands in the active job, direct navigation to the Failed Commands tab, and recompilation of the fresh static frontend bundle.

**Blocked by:** 01: Core Command Failure Telemetry API and Activity Drawer Tab, 02: Stage Filtering and Historical Past-Run Job Selector

**Status:** ready-for-agent

- [ ] Add a coral pill badge to the Activity Drawer trigger button in `AppNavigation` displaying the count of failed commands for the active job
- [ ] Ensure the navigation badge is completely hidden when zero commands failed or no job is active
- [ ] Support opening the Activity Drawer directly into the `Failed Commands` tab when triggered from diagnostics shortcuts
- [ ] Rebuild the production static bundle into `factory/ui/static/dist/` via `pnpm --dir factory/ui/frontend build`
- [ ] Verify that automated tests pass and `tests/test_ui/test_frontend_dist_freshness.py` reports zero diff
