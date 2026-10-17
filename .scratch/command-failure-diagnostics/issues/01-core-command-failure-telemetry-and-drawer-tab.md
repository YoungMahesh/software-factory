# 01: Core Command Failure Telemetry API and Activity Drawer Tab

**What to build:** The backend API endpoint and basic Activity Drawer tab enabling developers to view failed shell commands attempted by the Coder Agent and Deterministic Verifier for the active pipeline job, displaying exact command lines, exit codes, working directories, execution duration, and expandable stderr/stdout.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Implement `GET /api/jobs/{job_id}/failed-commands` returning normalized failed command objects from active in-memory job events or queried from `job_telemetry_events` in the Studio Database
- [x] Ensure non-zero exit codes (`exitCode != 0` or `isError: true`) for `bash` tool results from both `CODER` and `VERIFIER` stages are isolated, while zero exit codes and read-only tools are excluded
- [x] Add the `Failed Commands` tab to the slide-over `ActivityDrawer` rendering structured cards with command, cwd, stage, duration, exit code, and expandable output
- [x] Render a clean empty state with a confirmation message when zero commands failed for the selected job
- [x] Provide automated backend test verifying endpoint behavior and frontend component test verifying drawer tab rendering and empty state

