# Spec: Agent Event Stream and Real-Time Reasoning Console

Status: ready-for-agent

## Problem Statement

When the autonomous Software Factory assembly line executes inside ephemeral Modal Sandboxes, developers monitoring runs in the Factory Testing Console and Factory Studio only see raw, unformatted stdout terminal logs or high-level milestone progress. Long LLM reasoning traces (from models like DeepSeek V4.1 Flash and MiMo-V2.6-Flash) dump thousands of continuous tokens into the terminal buffer, obscuring actual executed shell commands, tool invocations, and test results. Furthermore, developers cannot easily see what commands were executed, whether they succeeded or failed, what files were inspected or edited, or how the Coder Agent reacted during self-correction loops without hunting through thousands of raw log lines.

## Solution

The **Agent Event Stream** provides a structured, real-time telemetry channel bridging in-sandbox agent execution with the Factory Testing Console and Factory Studio. 

1. An in-sandbox telemetry listener hooks into the Pi Agent Harness and Deterministic Verifier, capturing LLM thinking tokens, tool invocations (`bash`, `write`, `edit`, `read`, `diff`, `grep`), tool results, and stage transitions.
2. The harness formats telemetry into tagged JSON event envelopes (`__SF_EVENT__:{...}`) over the standard container stdout stream, utilizing a 100ms micro-batch buffer for thinking deltas to prevent stdout stream saturation.
3. The host Job Registry intercepts these envelopes, separating plain-text terminal logs from structured telemetry into dual-channel storage (`logs` and `events`), and broadcasts discrete typed Server-Sent Events (SSE) to connected clients.
4. The Factory Testing Console renders an interactive timeline with pulsating thinking accordions that auto-collapse on turn completion, rich command execution cards with windowed output (last 100 lines + full expansion), semantic tool chips with diff previews, and explicit self-correction attempt dividers.
5. Factory Studio displays inline thinking disclosures and tool action chips directly within the conversational assistant message bubble, backed by an expandable slide-over Agent Activity drawer.

## User Stories

1. As a developer watching an autonomous assembly line in the Factory Testing Console, I want to see a live pulsating "Thinking..." accordion while the LLM is reasoning, so that I know the model is actively processing without flooding my console with raw text.
2. As a developer, I want completed thinking blocks to automatically collapse into a compact duration badge (e.g., "Reasoning finished in 4.2s"), so that my view stays focused on actionable commands.
3. As a developer, I want to click any collapsed thinking badge at any time to expand and inspect the full markdown thought process, so that I can understand why the model chose a specific architecture or implementation approach.
4. As an engineer reviewing executed actions, I want to see a distinct command execution card whenever the agent runs a `bash` command, showing the exact command line, working directory, and running duration.
5. As an engineer, I want the output of a `bash` command to be windowed to the last 100 lines with an expand button, so that noisy package installations or build outputs do not cause browser scrolling lag.
6. As a developer, I want test suites executed by the Deterministic Verifier to appear as standard command execution cards on the same timeline, so that I have a unified narrative across both agentic and non-agentic stages.
7. As an engineer diagnosing a failed run, I want failed commands (non-zero exit code or assertion failure) to automatically expand with a prominent red badge showing stderr, so that I can diagnose the defect immediately without digging through logs.
8. As a developer observing a self-correction loop, I want to see an explicit visual divider between attempts (e.g., "Self-Correction Loop: Attempt 2/3"), so that I can easily see how the agent altered its code in response to previous test or review failures.
9. As an engineer watching file mutations, I want `edit` tool executions to display the target file path along with a unified diff preview of the modification, so that I can see exact code changes before git commits are created.
10. As an engineer, I want `read` tool invocations to display the inspected file path and line count rather than dumping the full file text into the stream, so that large file reads do not clutter the timeline.
11. As a developer copying logs via "Copy Logs", I want the copied text to be clean, human-readable terminal output without raw `__SF_EVENT__` JSON strings, so that I can share clean logs with colleagues or paste them into bug reports.
12. As a developer refreshing the page or switching tabs mid-run, I want the console to instantly rehydrate the full history of accordions, command cards, and tool chips, so that I don't lose past execution state.
13. As a developer using Factory Studio, I want to see inline thinking disclosures and step chips (e.g., "[Ran test]", "[Edited index.tsx]") inside the assistant chat bubble, so that I have conversational clarity on what the agent is doing.
14. As a Factory Studio user, I want to click an "Agent Activity" button or step chip to slide out a full-height activity drawer with the complete command timeline and logs, so that I can inspect execution details without navigating away from the chat and live preview.
15. As a developer using models that emit `<think>...</think>` tags in text rather than API reasoning deltas, I want thinking to be extracted seamlessly, so that reasoning is displayed consistently across different inference providers.

## Implementation Decisions

- **In-Sandbox Event Emitter**:
  The Pi Agent Harness subscribes to agent runtime events (`message_update`, `tool_execution_start`, `tool_execution_end`, `turn_end`). Thinking deltas are buffered and flushed at 100ms intervals or immediately prior to tool execution. Non-shell tool invocations generate semantic summaries (path and unified diff for edits, path and size for writes, path and line range for reads). Stage 3 Deterministic Verifier emits structured command events matching the harness schema.

- **Wire Format & Envelope Schema**:
  Events are serialized as single-line JSON strings preceded by a fixed delimiter:
  ```
  __SF_EVENT__:{"type":"thinking|tool_start|tool_result|stage|attempt","stage":"PLANNER|CODER|VERIFIER|REVIEWER","data":{...},"timestamp":1728547200.0}
  ```
  This guarantees standard output compatibility with Modal container streaming and terminal log readers.

- **Host Job Registry Dual-Channel Storage**:
  The host `JobRegistry` detects the `__SF_EVENT__:` delimiter on incoming stdout chunks. It strips the envelope from the plain-text log buffer (`job.logs`) and records the parsed event payload into a structured telemetry array (`job.events`). Broadcasts to queue listeners emit discrete typed event payloads (`thinking`, `tool_start`, `tool_result`, `stage`).

- **Server-Sent Events Protocol Expansion**:
  The `/api/jobs/{id}/stream` endpoint sends both `backlog` (clean text) and `events` (structured telemetry history) in the initial `init` event, ensuring complete client rehydration on reconnect. Subsequent events stream real-time typed updates.

- **Console & Studio UI Enhancements**:
  The web interface implements a hybrid stream view: a high-density terminal log tab alongside an interactive command execution timeline. Active thinking containers animate with a subtle pulse effect and automatically collapse when a tool or turn completes. Command output containers feature line-height virtualization or a 100-line tail cap with an expansion toggle. Factory Studio incorporates an expandable side drawer syncing with the same SSE stream.

## Testing Decisions

- **Testing Philosophy**:
  Tests must verify external behavioral contracts at architectural seams without asserting private implementation details. Specifically, tests should verify that given runtime events or stdout streams, the correct envelopes and SSE messages are delivered, and that plain-text log exports remain pristine.

- **Seams Identified for Testing**:
  1. *Highest / Primary Seam: Host Job Registry & SSE Demux (`tests/test_ui_events.py`)*
     Feeding simulated container stdout chunks containing plain text lines, stage markers, and `__SF_EVENT__:` envelopes to `JobRegistry.append_log()`. Assert that:
     - `job.logs` contains only clean text with all `__SF_EVENT__` envelopes scrubbed.
     - `job.events` correctly accumulates structured event models.
     - SSE queue listeners receive properly formatted `log` and `agent_event` payloads.
     - Initial sync payloads on `/api/jobs/{id}/stream` return both clean backlog and events history.
  2. *Secondary Seam: In-Sandbox Event Emitter Unit Tests (`sandbox/factory/events.test.ts`)*
     Testing the event emitter against simulated `@earendil-works/pi-agent-core` event subscriptions, verifying that:
     - 100ms micro-batching aggregates high-frequency thinking deltas into single chunks.
     - Dual-extraction extracts `<think>` blocks from text when native thinking deltas are absent.
     - Tool arguments are properly sanitized into semantic summaries (unified diffs for `edit`, line counts for `read`).

- **Prior Art**:
  - `tests/test_ui.py` for FastAPI endpoints and `JobRegistry` lifecycle verification.
  - `sandbox/factory/harness.test.ts` for Pi Agent Harness execution mocks and options resolution.
  - `sandbox/factory/verifier.test.ts` for test execution mocking.

## Out of Scope

- Bi-directional interactive terminal input (stdin) while commands are running.
- Persistent database storage for historical event streams beyond the existing in-memory job registry.
- Arbitrary breakpoint / step-through debugger controls inside the autonomous agent loop.

## Further Notes

- Aligns directly with **ADR-0035** and domain terminology in **CONTEXT.md**.
- The `__SF_EVENT__:` envelope ensures 100% backward compatibility with CLI-based runners (`factory/run.py`), which will simply ignore or display clean logs.
