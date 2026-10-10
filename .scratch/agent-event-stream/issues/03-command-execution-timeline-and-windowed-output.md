# 03: Command Execution Timeline & Windowed Output

**What to build:** An interactive command execution timeline tracking shell commands across the Coder Agent (`bash`) and the Deterministic Verifier (`verifyWorkspace`). When a command executes, a prominent card appears on the console timeline showing the command line, execution stage, and active timer. When execution finishes, the card displays the exit code badge, elapsed duration, and command output. Output is windowed to the last 100 lines with an expand button for full logs, preventing browser DOM thrashing during large build or test runs.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** resolved

- [x] In-sandbox `harness.ts` captures `tool_execution_start` and `tool_execution_end` for `bash` invocations, emitting `tool_start` and `tool_result` envelopes over the Agent Event Stream with exact command strings and working directories.
- [x] In-sandbox Deterministic Verifier in `sandbox/factory/verifier.ts` emits matching command start and result events for test suite executions (`pnpm test`, `pytest`).
- [x] Tool results include exit code, duration in milliseconds, stdout/stderr text, and an error flag (`isError: boolean`).
- [x] The Factory Testing Console UI in `factory/ui/templates/index.html` displays a dedicated Command Execution Card for each command execution.
- [x] Active commands show a live running spinner and elapsed second counter; completed commands display an exit code badge (`Exit code 0` in green, non-zero in red).
- [x] Command output is rendered inside a dark, scrollable code box capped by default to the last 100 lines, with a toggle displaying: "Showing last 100 of N lines — [View full output]".
- [x] Clicking "[View full output]" expands the container to show all lines without truncation.
- [x] Tests verify that both Coder bash commands and Verifier test suites emit consistent command telemetry and render windowed outputs.

## Comments

Implemented the interactive command execution timeline and windowed output across the Coder Agent and Deterministic Verifier:

1. **In-Sandbox Coder Bash Telemetry (`sandbox/factory/events.ts`, `sandbox/factory/harness.ts`)**:
   - Enhanced `AgentEventStream` and `subscribeAgentTelemetry` to track active tool calls by `toolCallId`.
   - On `tool_execution_start` for `bash`, emits `tool_start` with exact command string, working directory (`cwd`), and arguments.
   - On `tool_execution_end` for `bash`, emits `tool_result` with exact command string, `cwd`, exit code, elapsed duration in ms, stdout/stderr text, and `isError: boolean`.
   - Wired `workspaceDir` through `harness.ts` into `AgentEventStream`.

2. **Deterministic Verifier Matching Telemetry (`sandbox/factory/verifier.ts`)**:
   - Updated `verifyWorkspace` to emit matching `tool_start` and `tool_result` telemetry envelopes for every verification command execution (`pnpm test`, `pytest`, etc.).
   - Attributes stage as `VERIFIER` and captures exact exit codes, stdout, stderr, execution duration, and `isError` flag.

3. **Factory Testing Console UI (`factory/ui/templates/index.html`)**:
   - Implemented dedicated Command Execution Cards (`.command-card`) for each executed command on the live timeline.
   - Active commands display a live spinning indicator (`animate-spin`) and elapsed timer (`0.0s`).
   - Completed commands display an exit code badge (`Exit code 0` in green, non-zero in red), elapsed execution duration, and dark scrollable code box.
   - Windowed output: capped by default to the last 100 lines with an expansion toggle `"Showing last 100 of N lines — [View full output]"`.
   - Clicking `[View full output]` expands the container to show all lines without truncation, toggling to `[Show last 100 lines]`.
   - Rehydrates historical command execution cards and output from SSE `init` backlog and events.

4. **Testing (`sandbox/factory/events.test.ts`, `sandbox/factory/verifier.test.ts`, `sandbox/factory/harness.test.ts`, `tests/test_ui_events.py`)**:
   - Tested bash telemetry capture and formatting for success and failure cases.
   - Tested verifier test suite command start and result telemetry.
   - Tested full assembly line harness Coder bash execution with mock provider.
   - Tested host SSE demuxing, clean terminal logs, and UI components / windowed output expansion logic.

