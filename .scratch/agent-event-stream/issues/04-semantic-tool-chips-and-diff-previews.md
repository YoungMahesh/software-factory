# 04: Semantic Tool Chips & Diff Previews

**What to build:** Concise visual tracking for non-shell agent tool invocations (`edit`, `write`, `read`, `grep`, `diff`). Instead of dumping raw multikilobyte file contents into the console stream, tool inputs and outputs are sanitized into high-signal semantic summaries: `edit` tools display target file paths with unified diff previews of the modification, `write` tools show paths and bytes written, and `read`/`grep`/`diff` tools render compact single-line inspection chips showing paths and matched line counts.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** ready-for-agent

- [ ] Telemetry adapter in `sandbox/factory/` intercepts `read`, `write`, `edit`, `diff`, and `grep` tool calls before and after execution.
- [ ] For `edit` tools, the emitter extracts the target file path and generates a unified patch diff of the change, omitting verbose instructions from the event payload.
- [ ] For `write` tools, the payload reports the destination file path and byte length written, avoiding serializing entire file bodies across the stream.
- [ ] For `read` and `grep` tools, the payload records the target file path, line count inspected, or match count, suppressing verbatim file text.
- [ ] In the Factory Testing Console UI (`factory/ui/templates/index.html`), read-only tools render as compact single-line chips (e.g., `📄 Read src/routes/index.tsx (42 lines)`).
- [ ] `edit` tool executions render an expandable Diff Preview Card displaying syntax-colored line additions (`+`) and deletions (`-`).
- [ ] Tests verify that large file reads do not emit full file bodies over stdout and that edit diffs are properly parsed and displayed in the frontend.
