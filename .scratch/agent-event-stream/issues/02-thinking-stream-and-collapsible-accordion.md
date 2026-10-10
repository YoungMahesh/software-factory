# 02: Real-Time LLM Reasoning & Thinking Accordion

**What to build:** Real-time capturing, streaming, and visual presentation of the LLM's thought process across Planner, Coder, and Reviewer agent stages. In-sandbox agents subscribe to reasoning deltas and `<think>` tags, buffering tokens and emitting them at 100ms intervals over the Agent Event Stream. In the Factory Testing Console, developers see an active, pulsating thinking accordion showing the streaming reasoning in real time. When reasoning concludes and a tool or response turn begins, the container automatically collapses into a compact duration badge (e.g., "🧠 Reasoning finished in 4.2s") that can be clicked to re-expand the full thought text at any time.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** resolved

- [x] In-sandbox `runPlannerAgent`, `runCoderAgent`, and `runReviewerAgent` in `sandbox/factory/harness.ts` subscribe to `@earendil-works/pi-agent-core` events via `agent.subscribe()`.
- [x] Reasoning extraction supports dual-extraction: capturing native `thinking_delta` events as well as parsing and stripping text-streamed `<think>...</think>` blocks.
- [x] A 100ms micro-batch buffer aggregates streaming thinking deltas into periodically flushed `thinking_delta` envelopes, flushing immediately on `thinking_end` or tool execution.
- [x] Emitted thinking events include duration tracking and stage attribution (`stage: "PLANNER" | "CODER" | "REVIEWER"`).
- [x] The Factory Testing Console UI in `factory/ui/templates/index.html` renders an active thinking container with an animated pulse accent while tokens stream.
- [x] When thinking completes, the container automatically transitions to a collapsed badge displaying elapsed time and an expand toggle button.
- [x] Clicking any collapsed thinking badge re-expands the markdown reasoning view without interrupting subsequent log or command streaming.
- [x] Tests verify that rapid bursts of reasoning deltas are throttled to 100ms envelopes and that completed thinking blocks auto-collapse in the frontend.

## Comments

Implemented real-time LLM reasoning capture, dual-extraction, and interactive thinking accordion for the Factory Testing Console:

1. **Dual-Extraction Reasoning Extractor (`sandbox/factory/events.ts`)**:
   - Implemented `ThinkingExtractor` supporting native `thinking_delta` events as well as stateful chunk boundary parsing and stripping of `<think>...</think>` blocks from `text_delta`.
   - Aggregates high-frequency tokens via 100ms micro-batching buffer (`ThinkingBatchBuffer`), immediately flushing on `thinking_end`, `</think>`, or tool start.
   - Measures elapsed reasoning duration in milliseconds (`durationMs`) and attributes stage (`PLANNER`, `CODER`, `REVIEWER`).
   - Added `subscribeAgentTelemetry` and `stripThinkTags` helpers.

2. **Assembly Line Harness Subscription (`sandbox/factory/harness.ts`)**:
   - `runPlannerAgent`, `runCoderAgent`, and `runReviewerAgent` subscribe to `@earendil-works/pi-agent-core` events via `subscribeAgentTelemetry(agent, stage, ...)`.
   - Wraps prompt execution with deterministic `finally` cleanup to flush pending thinking envelopes and unsubscribe.
   - Strips `<think>` reasoning tags from extracted assistant text to prevent pollution of parsed JSON plans and review verdicts.

3. **Factory Testing Console Thinking Accordion (`factory/ui/templates/index.html`)**:
   - Renders active thinking container with animated pulsating accent (`animate-pulse`) while tokens stream in real time.
   - Automatically transitions to a sleek collapsed badge on completion (`Reasoning finished in 4.2s`) or upon tool execution.
   - Interactive click handler allows re-expanding and collapsing the full thought process without disrupting subsequent log or command streaming.
   - Rehydrates historical thinking events on reconnect (`init` SSE message).
   - Keeps plain-text log buffer clean for clipboard copying.

4. **Testing (`sandbox/factory/events.test.ts`, `sandbox/factory/harness.test.ts`, `tests/test_ui_events.py`)**:
   - Tested dual extraction of native thinking deltas and streamed `<think>...</think>` blocks across split chunk boundaries.
   - Verified 100ms micro-batch throttling of rapid bursts and immediate flush on tool execution.
   - Verified `runPlannerAgent`, `runCoderAgent`, and `runReviewerAgent` event subscription and stage attribution.
   - Verified frontend accordion components, auto-collapsing state machine, and SSE streaming pipeline.
