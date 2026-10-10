# 01: In-Sandbox Telemetry Envelope & Host SSE Demux

**What to build:** The foundational end-to-end telemetry transport pipeline between the in-sandbox assembly line and the host web application. When the in-sandbox harness runs, it formats structured telemetry events into tagged stdout lines using a defined prefix (`__SF_EVENT__:`). The host's `JobRegistry` detects and parses these envelopes, separating plain-text terminal lines from structured telemetry into dual-channel storage (`job.logs` and `job.events`). The host SSE endpoint `/api/jobs/{job_id}/stream` delivers initial state (`backlog` and `events`) on connection, and streams real-time typed events to the web client.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] An in-sandbox telemetry event emitter utility exists in `sandbox/factory/` capable of formatting typed events (`thinking`, `tool_start`, `tool_result`, `stage`) into single-line JSON envelopes prefixed with `__SF_EVENT__:`.
- [x] In-sandbox entrypoint and harness pipe stdout such that `__SF_EVENT__:` lines are transmitted unbuffered through Modal container stdout.
- [x] `JobRegistry.append_log()` in `factory/ui/registry.py` detects lines prefixed with `__SF_EVENT__:`, parses the JSON payload, and records the structured event object in `job.events`.
- [x] Raw `__SF_EVENT__:` lines are stripped from `job.logs`, ensuring that terminal log copying and plain-text backlog exports remain clean and free of JSON noise.
- [x] `JobRegistry` broadcasts parsed telemetry to active queue listeners as discrete typed SSE payloads (`{"event": "agent_event", "data": ...}`).
- [x] The `/api/jobs/{job_id}/stream` SSE endpoint transmits an `init` event containing both `backlog` (clean text lines) and `events` (structured event objects) upon connection.
- [x] Unit and integration tests in `tests/test_ui_events.py` verify that feeding simulated container stdout chunks containing mixed plain text and `__SF_EVENT__:` envelopes correctly populates both storage channels and streams valid SSE events.

## Answer

Implemented the end-to-end telemetry transport pipeline between the in-sandbox environment and the host web application:

1. **In-Sandbox Telemetry Emitter (`sandbox/factory/events.ts`)**:
   - Implemented `formatTelemetryEnvelope`, `parseTelemetryEnvelope`, and `emitTelemetryEvent` with single-line JSON formatting prefixed with `__SF_EVENT__:`.
   - Added typed emission helpers (`emitThinkingEvent`, `emitToolStartEvent`, `emitToolResultEvent`, `emitStageEvent`, `emitAttemptEvent`) and stateful `AgentEventStream` class.
   - Writes directly to fd 1 (`fs.writeSync(1, ...)`) for unbuffered stdout transmission through container stdout.
   - Comprehensive unit test suite in `sandbox/factory/events.test.ts`.

2. **Unbuffered Piping (`shared/factory_entrypoint.sh`)**:
   - Set `PYTHONUNBUFFERED=1` in the container entrypoint before launching the in-sandbox pipeline.

3. **Host Dual-Channel Demux (`factory/ui/registry.py`)**:
   - Added `job.events` list and `event_count` metadata in `FactoryJob.to_dict()`.
   - Updated `JobRegistry.append_log()` to inspect lines for `__SF_EVENT__:`, parse JSON payloads into `job.events`, strip raw envelope lines from `job.logs`, detect stage transitions for `stage` type events, and broadcast discrete typed SSE payloads (`{"event": "agent_event", "data": ...}`).

4. **SSE Initial State and Streaming (`factory/ui/app.py`)**:
   - Updated `/api/jobs/{job_id}/stream` to deliver both `backlog` (clean text lines) and `events` (structured event objects) in the initial `init` event.

5. **Test Coverage (`tests/test_ui_events.py`)**:
   - Added unit and integration tests verifying dual-channel demuxing, clean `job.logs`, `job.events` accumulation, stage updates, malformed JSON resilience, and SSE streaming.
