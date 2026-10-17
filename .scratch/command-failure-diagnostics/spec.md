# Spec: Factory Studio Command Failure Diagnostics

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When AI agents in Factory Studio execute tasks to generate or modify web applications, they run within ephemeral or persistent sandboxes managed by the Software Factory. During implementation, the Coder Agent attempts bash shell commands (e.g. installing dependencies, running generators, compiling assets), and the Deterministic Verifier runs automated test suites and linters.

Currently, when any of these commands fail—such as due to missing system binaries, missing npm packages, bad CLI arguments, or permission errors—the developer has no dedicated surface in Factory Studio to isolate and inspect these failures:
1. **Hidden Failures in Interleaved Telemetry**: Command results are interleaved with model thinking deltas, tool starts, and git diffs in the slide-over Activity Drawer's Timeline tab. Developers must manually scroll through dozens of events to locate which command failed and why.
2. **Unstructured Console Logs**: The Terminal Logs tab dumps raw standard output and standard error sequentially, making it time-consuming to correlate non-zero exit codes with exact command lines and working directories.
3. **Delayed Diagnosis of Missing Packages**: When building websites, AI models frequently attempt to invoke packages or tools that are not pre-installed in the Shared Base Image. Without an immediate, focused failure report, developers cannot quickly identify what packages are missing or refine agent system prompts to avoid forbidden commands.
4. **No Cross-Run Visibility**: Historical pipeline runs do not provide an easy way to view only the commands that broke without re-streaming or replaying full run logs.

## Solution

Introduce **Command Failure Diagnostics** in Factory Studio: a dedicated telemetry inspection surface in the slide-over Activity Drawer that isolates, filters, and renders non-zero exit code shell executions from both the Coder Agent and Deterministic Verifier stages.

The solution provides:
1. **Dedicated "Failed Commands" Tab in Activity Drawer**: A fourth tab positioned alongside Timeline, Terminal Logs, and History. When the active job contains failed commands, a prominent coral counter badge displays the failure count. When no commands fail, a reassuring empty state indicates a clean run.
2. **Unified Scope Across Coder and Verifier**: Automatically captures and displays commands with non-zero exit codes or error flags emitted by both the Pi Agent Harness Coder Agent (`CODER`) and the Deterministic Verifier (`VERIFIER`).
3. **Hybrid Streaming and Database Retrieval**: Real-time client-side event filtering for active streaming jobs, backed by a canonical REST API endpoint (`GET /api/jobs/{job_id}/failed-commands`) querying persisted telemetry events in the Studio Database for cold or historical jobs.
4. **Rich Diagnostic Cards & Filtering**: Renders each failure with the exact command line, working directory (`cwd`), pipeline stage, execution duration, exit code, and collapsible output with highlighted error lines. Includes quick stage filtering (`All`, `CODER`, `VERIFIER`) and a past-run selector to inspect earlier jobs in the repository.
5. **Non-Intrusive Notifications**: Displays a vibrant coral alert badge on the Activity Drawer trigger button in the main navigation bar whenever the active job encounters failed commands, alerting the developer without disrupting their conversational flow.

## User Stories

1. As a developer building a web app in Factory Studio, I want to see an error counter badge on the Activity Drawer button in the navigation bar when a command fails, so that I immediately know the agent encountered environment or command errors.
2. As a developer troubleshooting an agent run, I want a dedicated "Failed Commands" tab in the Activity Drawer, so that I don't have to sift through hundreds of lines of thinking logs or raw terminal output.
3. As a developer inspecting failed commands, I want to see the exact bash command line that failed, so that I can identify which binary or tool the model tried to run.
4. As a developer inspecting a failure, I want to see the working directory (`cwd`) where the command was executed, so that I understand the directory context of the failure.
5. As a developer diagnosing missing packages, I want to see the non-zero exit code and execution duration, so that I know whether the command failed immediately or timed out.
6. As a developer diagnosing build failures, I want to see the standard error output with error lines prominently highlighted, so that I can quickly read compiler or package manager error messages.
7. As a developer inspecting large command outputs, I want standard output and error to be collapsible with a toggle to view full output, so that long stack traces don't overwhelm the screen.
8. As a developer reviewing a pipeline run, I want to see failures from both the Coder Agent stage and the Deterministic Verifier stage in one unified list, so that I don't miss test suite execution failures.
9. As a developer focusing on implementation errors, I want to filter the failed commands list by stage (`CODER` vs `VERIFIER`), so that I can isolate agent mistakes from pre-existing test failures.
10. As a developer inspecting a successful run, I want the "Failed Commands" tab to show a clean empty state with a confirmation message, so that I am confident no shell commands failed.
11. As a developer reviewing past runs for the active repository, I want a run selector dropdown inside the tab to switch between recent jobs, so that I can inspect failures from previous attempts.
12. As a developer inspecting historical jobs from earlier sessions, I want the UI to load failed commands seamlessly from the backend database, so that diagnostics are available even after reloading the browser.
13. As a developer refining agent system prompts, I want to copy the exact failed command and error output with one click, so that I can provide corrective feedback or update prompt constraints.
14. As an infrastructure maintainer, I want to review common command failures across jobs, so that I can decide which packages and tools to pre-install in the Shared Base Image.
15. As a developer closing the drawer, I want the badge state on the drawer button to persist accurately based on the active job's status, so that I remain aware of failure counts.
16. As a developer running multiple jobs sequentially, I want the failed commands list and badge count to reset or update automatically when a new job starts, so that telemetry is always tied to the correct run.
17. As an API client, I want `GET /api/jobs/{job_id}/failed-commands` to return a clean, structured JSON payload of normalized failed commands, so that programmatic tools can extract failure telemetry.
18. As a frontend developer, I want the design of the Failed Commands tab to strictly follow the Cohere Editorial Design System, so that the diagnostics surface looks consistent with the rest of Factory Studio.

## Implementation Decisions

- **Activity Drawer Tab Expansion**:
  - Add `failed_commands` (display label "Failed Commands") as a first-class tab in the slide-over Activity Drawer alongside `timeline`, `logs`, and `history`.
  - Display a red/coral pill badge next to the tab label indicating the number of failed commands for the currently selected job.
  - When the count is zero, display no badge on the tab label.

- **Unified Command Failure Qualification**:
  - A command qualifies for the Failed Commands view if:
    - Its telemetry event type is `tool_result` with tool name `bash`.
    - AND either `exitCode` is defined and non-zero (`exitCode !== 0`) OR `isError` is true.
  - Both Coder Agent (`CODER`) and Deterministic Verifier (`VERIFIER`) emit events adhering to this schema.

- **Backend REST API Endpoint**:
  - Implement `GET /api/jobs/{job_id}/failed-commands` under the canonical job routes.
  - If the job is active in the in-memory registry, extract and filter failed command results from its event buffer.
  - If the job is historical, query `job_telemetry_events` in the Studio Database for the given `job_id` where `event_type = 'tool_result'` and the stored data contains `exitCode != 0` or `isError: true`.
  - Return HTTP 404 if the job identifier is invalid or not found.
  - Response payload contract:
    ```json
    {
      "job_id": "job-abc123",
      "count": 2,
      "failed_commands": [
        {
          "id": "evt-123",
          "command": "pnpm add some-package",
          "cwd": "/root/workspace",
          "stage": "CODER",
          "exit_code": 1,
          "is_error": true,
          "output": "ERR_PNPM_FETCH_404: Not Found",
          "stderr": "ERR_PNPM_FETCH_404: Not Found",
          "duration_ms": 1420,
          "created_at": 1729152000.0
        }
      ]
    }
    ```

- **Frontend Data Layer & Query Hook**:
  - Export a client API function `fetchFailedCommands(jobId: string)` in the API client module.
  - Create a React Query hook `useJobFailedCommandsQuery(jobId: string)` that fetches historical failed commands when the job is not actively streaming.
  - In the Activity Drawer, merge in-memory streaming events (for the live job) with query results (for historical jobs) into a unified memoized list.

- **Navigation Badge Integration**:
  - Compute the total failed command count for the active job.
  - If `count > 0`, display a coral pill badge with the failure count on the Activity Drawer trigger button in the main application navigation bar.
  - If `count === 0` or no job is active, omit the badge.

- **Diagnostics View UX & Filtering**:
  - Inside the Failed Commands tab, provide:
    - A past-run dropdown selector to switch between recent jobs of the active repository.
    - A filter bar with stage chips: `All (<count>)`, `Coder (<count>)`, and `Verifier (<count>)`.
    - A list of command cards rendering the command, cwd, stage badge, exit code, duration, and expandable stderr/stdout.
    - An empty state illustration and message (`No failed commands recorded for this job`) when zero commands failed.

## Testing Decisions

- **Testing Principles**:
  - Only test observable user-facing behavior and external HTTP API contracts; do not assert internal state or private helpers.
  - Prefer high-level seams (HTTP request/response seam for backend, Component user interaction seam for frontend).
  - Avoid shallow mocking of subcomponents; render through the full component hierarchy.

- **Backend Seam (FastAPI REST Endpoint)**:
  - Exercise `GET /api/jobs/{job_id}/failed-commands` using the test client.
  - Assert that a running job in the registry returns its non-zero bash tool results.
  - Assert that a cold job persisted only in the database returns its filtered failed commands.
  - Assert that a 404 status is returned when an invalid job ID is queried.
  - Assert that exitCode 0 commands and non-bash tool results (e.g. read, grep) are excluded.

- **Frontend Seam (Activity Drawer & Navigation)**:
  - In the Activity Drawer test suite, assert that the "Failed Commands" tab renders with the appropriate counter badge.
  - Assert that clicking the tab displays failed command cards with command line, exit code, and error text.
  - Assert that stage filtering correctly filters cards between Coder and Verifier stages.
  - Assert that when no failed commands exist, the empty state message is displayed.
  - In the Navigation test suite, assert that the coral error badge appears on the Activity Drawer button when the active job has failed commands, and is omitted when clean.

## Out of Scope

- Auto-installing missing packages or mutating the sandbox filesystem automatically from the diagnostics card.
- Inline prompt editing or prompt retraining from the UI (the diagnostics card provides copyable feedback for developer inspection).
- Interactive shell or pseudo-terminal (PTY) emulation inside the diagnostics view.
- Real-time lint error parsing beyond capturing command exit codes and output text.

## Further Notes

- Adheres strictly to [ADR 0060](file:///root/failed-commands/docs/adr/0060-factory-studio-command-failure-diagnostics.md) and the domain terminology in [`CONTEXT.md`](file:///root/failed-commands/CONTEXT.md#L342-L347).
- Both backend and frontend modifications must respect the Universal File Line Budget (<= 500 lines per file).
