# 03: Command Execution Timeline & Windowed Output

**What to build:** An interactive command execution timeline tracking shell commands across the Coder Agent (`bash`) and the Deterministic Verifier (`verifyWorkspace`). When a command executes, a prominent card appears on the console timeline showing the command line, execution stage, and active timer. When execution finishes, the card displays the exit code badge, elapsed duration, and command output. Output is windowed to the last 100 lines with an expand button for full logs, preventing browser DOM thrashing during large build or test runs.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** ready-for-agent

- [ ] In-sandbox `harness.ts` captures `tool_execution_start` and `tool_execution_end` for `bash` invocations, emitting `tool_start` and `tool_result` envelopes over the Agent Event Stream with exact command strings and working directories.
- [ ] In-sandbox Deterministic Verifier in `sandbox/factory/verifier.ts` emits matching command start and result events for test suite executions (`pnpm test`, `pytest`).
- [ ] Tool results include exit code, duration in milliseconds, stdout/stderr text, and an error flag (`isError: boolean`).
- [ ] The Factory Testing Console UI in `factory/ui/templates/index.html` displays a dedicated Command Execution Card for each command execution.
- [ ] Active commands show a live running spinner and elapsed second counter; completed commands display an exit code badge (`Exit code 0` in green, non-zero in red).
- [ ] Command output is rendered inside a dark, scrollable code box capped by default to the last 100 lines, with a toggle displaying: "Showing last 100 of N lines — [View full output]".
- [ ] Clicking "[View full output]" expands the container to show all lines without truncation.
- [ ] Tests verify that both Coder bash commands and Verifier test suites emit consistent command telemetry and render windowed outputs.
