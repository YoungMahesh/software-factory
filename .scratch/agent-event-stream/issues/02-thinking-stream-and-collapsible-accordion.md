# 02: Real-Time LLM Reasoning & Thinking Accordion

**What to build:** Real-time capturing, streaming, and visual presentation of the LLM's thought process across Planner, Coder, and Reviewer agent stages. In-sandbox agents subscribe to reasoning deltas and `<think>` tags, buffering tokens and emitting them at 100ms intervals over the Agent Event Stream. In the Factory Testing Console, developers see an active, pulsating thinking accordion showing the streaming reasoning in real time. When reasoning concludes and a tool or response turn begins, the container automatically collapses into a compact duration badge (e.g., "🧠 Reasoning finished in 4.2s") that can be clicked to re-expand the full thought text at any time.

**Blocked by:** 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**Status:** ready-for-agent

- [ ] In-sandbox `runPlannerAgent`, `runCoderAgent`, and `runReviewerAgent` in `sandbox/factory/harness.ts` subscribe to `@earendil-works/pi-agent-core` events via `agent.subscribe()`.
- [ ] Reasoning extraction supports dual-extraction: capturing native `thinking_delta` events as well as parsing and stripping text-streamed `<think>...</think>` blocks.
- [ ] A 100ms micro-batch buffer aggregates streaming thinking deltas into periodically flushed `thinking_delta` envelopes, flushing immediately on `thinking_end` or tool execution.
- [ ] Emitted thinking events include duration tracking and stage attribution (`stage: "PLANNER" | "CODER" | "REVIEWER"`).
- [ ] The Factory Testing Console UI in `factory/ui/templates/index.html` renders an active thinking container with an animated pulse accent while tokens stream.
- [ ] When thinking completes, the container automatically transitions to a collapsed badge displaying elapsed time and an expand toggle button.
- [ ] Clicking any collapsed thinking badge re-expands the markdown reasoning view without interrupting subsequent log or command streaming.
- [ ] Tests verify that rapid bursts of reasoning deltas are throttled to 100ms envelopes and that completed thinking blocks auto-collapse in the frontend.
