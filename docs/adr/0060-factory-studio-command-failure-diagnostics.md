# Factory Studio Command Failure Diagnostics

**Status**: Accepted

To enable developers to rapidly diagnose missing system packages, broken build tooling, and suboptimal LLM system prompts when building web applications on the Software Factory, we decided to introduce a dedicated **Command Failure Diagnostics** tab in Factory Studio's Activity Drawer, capturing non-zero exit code command executions across both the Coder Agent and Deterministic Verifier stages via a hybrid streaming and database retrieval architecture.

## Context

Factory Studio operates as an interactive harness driving the in-sandbox **Pi Agent Harness** to iteratively build, test, and preview web applications. During feature implementation, the LLM Coder Agent executes shell commands (e.g. installing dependencies via `pnpm add`, compiling source files, or executing scripts), followed by the non-agentic **Deterministic Verifier** executing test and lint commands (`pnpm test`, `pytest`, etc.).

Previously, command execution output was only inspectable by scrolling through the interleaved "Timeline" tab (where successful thinking, diffs, and commands are mixed) or reading unstructured console output in the "Terminal Logs" tab. When an LLM attempted commands that failed due to missing packages, invalid CLI flags, or permission errors, developers had no isolated, structured view to answer:
1. What exact command was executed?
2. What was the non-zero exit code and working directory?
3. What was the exact stderr/stdout output?
4. How can we use this diagnostic signal to update the sandbox base image or refine system prompts?

## Decision

1. **Dedicated "Failed Commands" Tab in Activity Drawer**:
   - Add a fourth tab, `Failed Commands`, to `ActivityDrawer.tsx` alongside `Timeline`, `Terminal Logs`, and `History`.
   - When the active job has failed commands, a coral badge renders on the tab header (e.g. `Failed Commands (2)`).
   - When no commands have failed, render a clean, reassuring empty state indicating no errors were encountered.

2. **Unified Scope Across Coder and Verifier**:
   - Qualify any command execution with `exitCode != 0` or `isError: true` from both:
     - **Coder Agent**: In-sandbox Pi Agent `bash` tool invocations.
     - **Deterministic Verifier**: Test, lint, and build script runs executed during verification.
   - Both stages already emit normalized `tool_result` telemetry envelopes with `toolName: "bash"`, `command`, `cwd`, `exitCode`, and `output`/`stderr`.

3. **Hybrid Streaming and Database Retrieval Architecture**:
   - **Active Stream**: For the currently running or freshly streamed job, filter `events` in memory on the client for zero-latency instant updates.
   - **Historical Retrieval**: Introduce a canonical REST endpoint `GET /api/jobs/{job_id}/failed-commands` in `factory/ui/routes/jobs.py` that queries `job_telemetry_events` in the Studio Database for historical or cold jobs, returning normalized failed command records.

4. **Structured Command Cards and Stage Filtering**:
   - Render failed commands using an enhanced `CommandCard` featuring command string, exit code badge, duration, working directory, and highlighted stderr lines.
   - Provide a quick stage filter (`All`, `CODER`, `VERIFIER`) and a past-run selector dropdown allowing inspection of prior jobs within the active repository.

5. **Notification and Navigation**:
   - Display a vibrant coral counter badge on the Activity Drawer trigger in `AppNavigation.tsx` whenever the active job has failed commands, alert-routing developers to the diagnostics tab without intrusive auto-opening.

## Consequences

- **Domain Model**: `Command Failure Diagnostics` is added as a canonical term in [`CONTEXT.md`](../../CONTEXT.md).
- **Accelerated Environment Tuning**: Developers can immediately spot missing CLI tools (e.g. `npx`, `jq`, `unzip`) or package dependencies (`lucide-react`, `@types/...`) and add them to the Shared Base Image or preflight instructions.
- **System Prompt Refinement**: Repeated syntactical mistakes or forbidden commands by specific LLM models are highlighted, providing immediate empirical signal to refine `CODER_SYSTEM_PROMPT`.
- **Architectural Seams**: Leverages the existing `job_telemetry_events` table and SSE event stream with zero database schema migrations.
