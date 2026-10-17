# 03: Repository-Wide Telemetry Aggregation Endpoint and View

**What to build:** An end-to-end repository-wide aggregated bottlenecks view. A backend database service and REST endpoint `GET /api/repos/{repo}/bottlenecks` query persistent telemetry events across all past runs of a repository, grouping normalized commands to calculate cumulative execution time, invocation count, average time, and maximum single-run duration. A scope toggle in the Bottlenecks tab allows developers to switch between inspecting the single active run and viewing repository-wide recurring bottlenecks.

**Blocked by:** 01: In-Drawer Bottleneck Tab and Live Event Ranking

**Status:** resolved

- [x] Database storage layer includes an aggregation query grouping `job_telemetry_events` by normalized command or thinking phase for a given repository.
- [x] Canonical endpoint `GET /api/repos/{repo}/bottlenecks` returns aggregated metrics (total time, count, average time, max time, stage, and category).
- [x] Frontend API client includes `fetchRepoBottlenecks(repo: string)` with appropriate TypeScript types.
- [x] Scope toggle in the Bottlenecks tab switches between "Current Run" and "Repository Aggregates".
- [x] The aggregated view renders a table showing rank, normalized command/phase, total duration, invocation count, and average execution time.
- [x] Automated tests cover backend route aggregation and frontend scope toggling.
