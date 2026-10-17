# 02: Stage Filtering and Historical Past-Run Job Selector

**What to build:** Interactive stage filtering controls and a past-run job selector within the Failed Commands tab, allowing developers to filter failures between Coder Agent and Verifier stages, and switch between recent jobs of the active repository to inspect historical command failures.

**Blocked by:** 01: Core Command Failure Telemetry API and Activity Drawer Tab

**Status:** ready-for-agent

- [ ] Implement stage filter chips (`All`, `Coder`, `Verifier`) in the Failed Commands tab header to filter displayed failure cards by stage
- [ ] Implement a past-run selector dropdown in the tab header listing recent jobs for the current repository
- [ ] Wire the past-run selector to load historical failed commands via `GET /api/jobs/{job_id}/failed-commands` when viewing a non-active job
- [ ] Display the count of failures for each stage in the filter chips
- [ ] Provide automated frontend tests verifying stage filtering interaction and historical job selection
