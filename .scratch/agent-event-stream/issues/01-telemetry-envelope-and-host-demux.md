# 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**What to build:** The foundational end-to-end telemetry transport pipeline between the in-sandbox assembly line and the host web application. When the in-sandbox harness runs, it formats structured telemetry events into tagged stdout lines using a defined prefix (`__SF_EVENT__:`). The host's `JobRegistry` detects and parses these envelopes, separating plain-text terminal lines from structured telemetry into dual-channel storage (`job.logs` and `job.events`). The host SSE endpoint `/api/jobs/{job_id}/stream` delivers initial state (`backlog` and `events`) on connection, and streams real-time typed events to the web client.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] An in-sandbox telemetry event emitter utility exists in `sandbox/factory/` capable of formatting typed events (`thinking`, `tool_start`, `tool_result`, `stage`) into single-line JSON envelopes prefixed with `__SF_EVENT__:`.
- [ ] In-sandbox entrypoint and harness pipe stdout such that `__SF_EVENT__:` lines are transmitted unbuffered through Modal container stdout.
- [ ] `JobRegistry.append_log()` in `factory/ui/registry.py` detects lines prefixed with `__SF_EVENT__:`, parses the JSON payload, and records the structured event object in `job.events`.
- [ ] Raw `__SF_EVENT__:` lines are stripped from `job.logs`, ensuring that terminal log copying and plain-text backlog exports remain clean and free of JSON noise.
- [ ] `JobRegistry` broadcasts parsed telemetry to active queue listeners as discrete typed SSE payloads (`{"event": "agent_event", "data": ...}`).
- [ ] The `/api/jobs/{job_id}/stream` SSE endpoint transmits an `init` event containing both `backlog` (clean text lines) and `events` (structured event objects) upon connection.
- [ ] Unit and integration tests in `tests/test_ui_events.py` verify that feeding simulated container stdout chunks containing mixed plain text and `__SF_EVENT__:` envelopes correctly populates both storage channels and streams valid SSE events.
