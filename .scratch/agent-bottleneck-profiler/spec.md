# Spec: Agent Command Bottleneck Profiler and Telemetry Diagnostics

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

The Software Factory harnesses LLM agents (`pi-agent`) to autonomously build web applications inside Modal sandboxes. When agents execute workflows (exploring repositories, editing files, running bash commands, executing verifier tests, and reasoning in thinking blocks), developers lack clear visibility into which operations consume the most execution time. 

Without fine-grained diagnostic profiling:
1. **Hidden Infrastructure Bottlenecks**: Developers cannot determine whether slow pipeline execution is caused by network package installation (e.g., `pnpm install`), slow test runners (`vitest` / `pytest`), repetitive build compilation steps (`pnpm build`), or LLM generation and reasoning latency.
2. **Untargeted Cloud Optimization**: Infrastructure engineers cannot prioritize optimizations (such as pre-baking specific dependencies into container base images, provisioning caching mounts, or tuning agent system prompts) without concrete duration metrics.
3. **Opaque Multi-Run Performance Drift**: Even when individual runs succeed or fail, developers cannot compare command durations across runs or identify recurring slow operations across the entire repository history.

## Solution

Introduce the **Agent Bottleneck Profiler** in Factory Studio—an interactive diagnostic telemetry surface that extracts and sorts all executed shell commands, verifier test runs, and LLM thinking blocks from longest to shortest duration, providing:

1. **Dedicated Bottlenecks Tab in Activity Drawer**:
   - A fourth tab ("Bottlenecks") integrated directly into the slide-over Activity Drawer alongside Timeline, Terminal Logs, and History.
   - Real-time telemetry consumption that dynamically updates as streaming events arrive from the running sandbox.

2. **Fine-Grained Execution Ranking & Infrastructure Categorization**:
   - Sorted list of all executed commands and thinking blocks ordered strictly by duration (most time taken to least time taken).
   - Visual relative duration bars and color-coded exit code indicators.
   - Automatic infrastructure classification badges (e.g., `Package Install`, `Test Suite`, `Build / Compile`, `Git / VCS`, `LLM Thinking`).
   - Expandable command cards displaying exit codes, full output, stderr highlighting, working directory, and collapsible reasoning text.

3. **Dual Scoping (Current Run vs. Repository Aggregation)**:
   - Default active run view displaying every command and thinking block from the selected or active job.
   - A toggle to switch to **Repository-Wide Aggregation**, grouping recurring commands across all recorded runs for the repository and displaying total cumulative duration, invocation count, average duration, and max execution time.

4. **Interactive Filters, Thresholds & Export**:
   - Stage filter pills (*All*, *Planner*, *Coder*, *Verifier*, *Reviewer*).
   - Category toggles (*All*, *Commands*, *Thinking*).
   - Threshold toggle to hide micro-commands under 100ms.
   - A "Copy Summary" button that exports a clean markdown report of top bottlenecks to share with infrastructure and tooling teams.

5. **Backend Telemetry Aggregation Endpoint**:
   - A canonical REST endpoint `GET /api/repos/{repo}/bottlenecks` that aggregates structured telemetry events from persistent database storage.

## User Stories

1. As a software factory developer, I want to see all commands executed by the LLM and verifier sorted by execution duration, so that I can immediately identify the slowest steps in my build pipeline.
2. As a cloud infrastructure engineer, I want the profiler to highlight whether slow commands are package installations (`pnpm install`), so that I can pre-bake those packages into the container base image.
3. As an engineer optimizing test runners, I want to see the exact time taken by automated test executions (`pnpm test`, `pytest`), so that I can optimize test suite parallelization or mocking.
4. As a developer inspecting model performance, I want LLM thinking and reasoning blocks included in the sorted duration list, so that I can diagnose reasoning latency relative to tool execution time.
5. As a developer monitoring an active job, I want the Bottlenecks tab to update dynamically in real time as events stream in, so that I can watch bottlenecks emerge without refreshing the page.
6. As a developer watching an in-progress step, I want to see an active banner indicating the currently running command, so that I know what is executing right now.
7. As a developer troubleshooting a past job, I want to open the Activity Drawer, switch to History, pick a prior run, and inspect its Bottlenecks tab, so that I can diagnose historical failures.
8. As an infrastructure lead, I want to toggle to a Repository-Wide Aggregated view, so that I can see the cumulative time and average duration of recurring commands across all runs.
9. As a developer diagnosing a specific stage, I want to filter the bottleneck list by pipeline stage (*Planner*, *Coder*, *Verifier*, *Reviewer*), so that I can isolate bottlenecks specific to code synthesis or verification.
10. As a developer reviewing agent operations, I want to filter by category (*Commands* vs *Thinking*), so that I can analyze tool execution and model deliberation independently.
11. As a developer filtering out noise, I want a toggle to hide micro-commands under 100ms, so that quick commands like `git status` or `pwd` do not clutter the list.
12. As a developer inspecting a failed command, I want to click the bottleneck card to expand its stdout and stderr outputs, so that I can understand why the command took long or failed.
13. As a developer sharing findings with my team, I want to click a "Copy Summary" button that copies a markdown table of the top bottlenecks, so that I can easily paste diagnostic reports into discussions or issue trackers.
14. As an API client, I want to query `GET /api/repos/{repo}/bottlenecks` with optional limit parameters, so that external monitoring tools can ingest aggregated telemetry.
15. As a frontend maintainer, I want the profiler components to reside in a dedicated, modular component file, so that file line budgets remain strictly under 500 lines.
16. As a maintainer running test suites, I want comprehensive component and API tests for the bottleneck profiler, so that regressions in telemetry formatting or sorting are caught automatically.

## Implementation Decisions

- **Activity Drawer Tab Integration**:
  - Add a fourth tab button labelled `Bottlenecks` to the top tab bar in the Activity Drawer alongside `Timeline`, `Logs`, and `History`.
  - Maintain active tab switching state, preserving tab selection when inspecting different jobs.

- **Modular UI Component (`BottlenecksViewer.tsx`)**:
  - Encapsulate all bottleneck rendering, sorting, filtering, and aggregation display in a dedicated component file rather than bloating `ActivityDrawer.tsx`.
  - Ensure all files adhere strictly to the universal file line ratchet (<= 500 lines).

- **Telemetry Parsing & Normalization**:
  - Extract duration metrics directly from structured telemetry events (`tool_result` events containing `durationMs` and `thinking` events containing `durationMs`).
  - Represent thinking sessions with their stage and attempt context, preserving reasoning text for expansion.
  - Automatically detect infrastructure categories based on command prefix and binary heuristics:
    - *Package Install*: `pnpm install`, `pnpm add`, `npm install`, `npm i`, `yarn add`, `pip install`
    - *Test Suite*: `pnpm test`, `npm test`, `pytest`, `vitest`, `jest`
    - *Build / Compile*: `pnpm build`, `npm run build`, `tsc`, `vite build`
    - *Git / VCS*: `git clone`, `git fetch`, `git checkout`, `git status`, `git diff`
    - *LLM Thinking*: Thinking and reasoning delta blocks

- **Repository-Wide Aggregation Service**:
  - Add backend aggregation logic in the database storage layer that queries `job_telemetry_events` for the specified repository.
  - Group identical normalized commands, calculating total cumulative duration, execution count, average duration, and maximum single-run duration.
  - Expose the aggregated data through the canonical route `GET /api/repos/{repo}/bottlenecks`.

- **Client API Integration**:
  - Extend the frontend API client with `fetchRepoBottlenecks(repo: string)` to query the backend aggregation endpoint.
  - Manage loading and error states gracefully in the repository aggregation toggle.

- **Clipboard Export**:
  - Implement a markdown summary generator formatting the top bottlenecks into a clean GitHub-flavored markdown table including Rank, Duration, Category, Stage, and Command/Phase.

## Testing Decisions

- **Good Test Criteria**:
  - Tests must assert external behavior from the user's perspective (rendered DOM elements, visible badges, sorting order, tab switching, and clipboard calls) rather than internal React state.
  - Backend tests must exercise HTTP endpoints and database queries against realistic telemetry fixtures.
- **Modules to Test**:
  - Component tests: `BottlenecksViewer.test.tsx` verifying descending duration sorting, category badges, stage filtering, threshold toggling, output expansion, and markdown export.
  - Integration tests: `ActivityDrawer.test.tsx` verifying tab switching between Timeline, Logs, History, and Bottlenecks.
  - API endpoint tests: `test_bottlenecks_api.py` asserting `GET /api/repos/{repo}/bottlenecks` returns correct grouping and metrics.
  - Production build freshness: `test_frontend_dist_freshness.py` asserting compiled bundle matches frontend source code.
- **Prior Art**:
  - `ActivityDrawer.test.tsx` and `CommandCard.test.tsx` for drawer tabs and terminal card behavior.
  - `test_ui_events/test_console_telemetry.py` for structured telemetry event fixtures.

## Out of Scope

- Modifying agent tool definitions or adding new tools to `@earendil-works/pi-agent-core`.
- Automated container configuration mutation (e.g. automatically rewriting Dockerfiles based on detected slow commands).
- Live execution profiling via Linux kernel tracing (e.g. `perf`, `ebpf`, or CPU profiling). Profiling is strictly based on wall-clock execution durations recorded in the agent telemetry stream.

## Further Notes

- All changes must adhere to the 2026 Cohere design system (hairline rules, soft stone surfaces, monospaced technical telemetry, and pill controls).
- Bundle compilation must be performed via `pnpm --dir factory/ui/frontend build` and checked in atomically.
