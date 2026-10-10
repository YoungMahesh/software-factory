# 04: Semantic Tool Chips & Diff Previews

**What to build:** Concise visual tracking for non-shell agent tool invocations (`edit`, `write`, `read`, `grep`, `diff`). Instead of dumping raw multikilobyte file contents into the console stream, tool inputs and outputs are sanitized into high-signal semantic summaries: `edit` tools display target file paths with unified diff previews of the modification, `write` tools show paths and bytes written, and `read`/`grep`/`diff` tools render compact single-line inspection chips showing paths and matched line counts.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** resolved

- [x] Telemetry adapter in `sandbox/factory/` intercepts `read`, `write`, `edit`, `diff`, and `grep` tool calls before and after execution.
- [x] For `edit` tools, the emitter extracts the target file path and generates a unified patch diff of the change, omitting verbose instructions from the event payload.
- [x] For `write` tools, the payload reports the destination file path and byte length written, avoiding serializing entire file bodies across the stream.
- [x] For `read` and `grep` tools, the payload records the target file path, line count inspected, or match count, suppressing verbatim file text.
- [x] In the Factory Testing Console UI (`factory/ui/templates/index.html`), read-only tools render as compact single-line chips (e.g., `📄 Read src/routes/index.tsx (42 lines)`).
- [x] `edit` tool executions render an expandable Diff Preview Card displaying syntax-colored line additions (`+`) and deletions (`-`).
- [x] Tests verify that large file reads do not emit full file bodies over stdout and that edit diffs are properly parsed and displayed in the frontend.

## Comments

Implemented concise semantic tool visual tracking and diff previews for non-shell tool invocations across the in-sandbox telemetry pipeline and Factory Testing Console UI:

1. **In-Sandbox Telemetry Interception & Sanitization (`sandbox/factory/events.ts`)**:
   - Enhanced `subscribeAgentTelemetry`, `emitToolStartEvent`, and `emitToolResultEvent` to intercept `read`, `write`, `edit`, `grep`, and `diff` tool calls before and after execution.
   - For `read` tools, extracts file path and calculates line count inspected (`lineCount`), suppressing verbatim file bodies from container stdout and preventing stream saturation.
   - For `write` tools, extracts destination path and byte length written (`bytes`), omitting large file content bodies from both `tool_start` and `tool_result` event payloads.
   - For `edit` tools, extracts target file path and generates unified patch diffs of changes using `@earendil-works/pi-coding-agent`'s `generateUnifiedPatch`, omitting verbose instruction objects from event envelopes.
   - For `grep` tools, reports target path, search pattern, and match count (`matchCount`), suppressing raw matched lines from stdout.
   - For `diff` tools, records target file/tree path and inspected line count (`lineCount`), suppressing verbatim diff dumps.

2. **Factory Testing Console UI (`factory/ui/templates/index.html`)**:
   - Implemented compact single-line Tool Chips (`.tool-chip`) for `read`, `write`, `grep`, and `diff` operations with semantic icons (`📄 Read ... (42 lines)`, `📝 Write ... (N bytes)`, `🔍 Grep ... (N matches)`, `🔍 Diff ... (N lines)`).
   - Implemented expandable Diff Preview Cards (`.diff-preview-card`) for `edit` tools displaying syntax-colored line additions (`+` in emerald green) and deletions (`-` in rose red) with addition/deletion stats badges (`+N` / `-N`).
   - Added interactive diff collapse/expand toggle (`toggleDiffCard`) with header click handler.
   - Added rehydration support for semantic tool chips and diff preview cards from SSE init event backlogs.

3. **Comprehensive Test Suites (`sandbox/factory/events.test.ts`, `tests/test_ui_events.py`)**:
   - Verified that large file reads (2,000 lines, 100KB) emit lightweight summary payloads without dumping verbatim file text over stdout.
   - Verified write and edit payload sanitization, unified patch diff generation, and grep/diff count summaries.
   - Verified end-to-end agent event subscription, JobRegistry dual-channel demuxing, clean terminal logs, UI template classes/methods, and SSE history rehydration.
