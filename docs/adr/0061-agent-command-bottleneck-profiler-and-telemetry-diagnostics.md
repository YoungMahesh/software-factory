# Agent Command Bottleneck Profiler and Telemetry Diagnostics

**Status**: Accepted

To enable developers to rapidly diagnose performance bottlenecks, identify long-running commands, and optimize developer experience across autonomous coding jobs in Factory Studio, we decided to introduce a dedicated **Agent Bottleneck Profiler** in the Activity Drawer alongside a repository-wide telemetry aggregation endpoint `GET /api/repos/{repo}/bottlenecks`, automatic infrastructure category classification, and a one-click GitHub-flavored markdown diagnostic summary export.

## Context

Factory Studio orchestrates autonomous AI software engineering workflows across pipeline stages: Planner Agent, Coder Agent, Deterministic Verifier, and Reviewer Agent. During job execution, agents execute shell commands (e.g. installing dependencies via `pnpm add`, building assets via `pnpm build`, running test suites via `pytest` or `vitest`), invoke git operations, and generate reasoning thinking blocks.

Previously, timing information was scattered across unstructured console outputs in the "Terminal Logs" tab or interleaved chronologically inside the "Timeline" tab. Developers and platform engineers attempting to accelerate software factory workflows had no isolated, sorted view to answer:
1. What individual command, test runner, or LLM thinking block took the longest time in the current job?
2. Which infrastructure category is consuming the most time (package installations, test suites, build compilations, git operations, or model reasoning)?
3. What command is actively running right now, and in which stage?
4. Across all historical runs within a repository, what recurring commands consume the most cumulative execution time?
5. How can developers quickly export a structured markdown summary of bottlenecks to share in GitHub issues or team discussions?

## Decision

1. **Dedicated "Bottlenecks" Tab in Activity Drawer**:
   - Add a fourth tab button `Bottlenecks` (`id="btn-drawer-tab-bottlenecks"`) to `ActivityDrawer.tsx` alongside `Timeline`, `Terminal Logs`, and `History`.
   - Render completed bash commands, verifier test executions, and LLM thinking sessions sorted strictly in descending order of `durationMs`.
   - Display proportional duration bars relative to the longest operation in the active run.
   - Display an active execution banner (`id="active-execution-banner"`) with a running spinner whenever a tool or command is actively executing.
   - Provide a toggle control allowing developers to hide micro-commands that executed in less than 100ms.

2. **Infrastructure Badges and Stage Filtering**:
   - Apply automatic pattern heuristics to classify profiled operations into color-coded infrastructure categories: `Package Install`, `Test Suite`, `Build / Compile`, `Git / VCS`, `LLM Thinking`, and `Command`.
   - Render interactive stage filter pills (`All`, `Planner`, `Coder`, `Verifier`, `Reviewer`) and category toggle buttons (`All`, `Commands`, `Thinking`).
   - Provide interactive accordion card expansion displaying execution details: working directory (`cwd`), exit code status, full stdout/stderr with highlighted failure lines, and wrapped reasoning text.

3. **Repository-Wide Telemetry Aggregation**:
   - Implement `StudioDatabase.get_repo_bottlenecks` querying persistent `job_telemetry_events` across all past jobs for a repository.
   - Expose the canonical REST API endpoint `GET /api/repos/{repo}/bottlenecks?limit=50`.
   - Group telemetry events by normalized command string or thinking phase, computing cumulative execution time, invocation count, average run time, and maximum single-run duration.
   - Provide an in-drawer scope toggle switching between "Current Run" and "Repository Aggregates" with a dedicated ranked table.

4. **Diagnostic Summary Export**:
   - Add a "Copy Summary" button (`id="btn-copy-bottlenecks-summary"`) that formats the active bottleneck list into a clean GitHub-flavored markdown table and copies it to the developer's clipboard.
   - Provide visual feedback confirming successful copying by temporarily changing the icon and label to "Copied" for 2 seconds.

## Consequences

- **Domain Model**: `Agent Bottleneck Profiler` and `Infrastructure Bottleneck Heuristics` are added as canonical domain terms in [`CONTEXT.md`](../../CONTEXT.md).
- **Accelerated Environment Tuning**: Developers and platform operators can instantly spot slow package managers, un-cached test runs, or slow build steps and apply caching, pre-baked dependencies, or parallelization.
- **System Prompt Refinement**: Repeated micro-commands, redundant exploratory queries, or excessive LLM thinking phases are clearly highlighted for agent optimization.
- **Zero Schema Migrations**: Fully leverages the existing SQLite/Turso `job_telemetry_events` table and client SSE event stream with no database schema changes.
