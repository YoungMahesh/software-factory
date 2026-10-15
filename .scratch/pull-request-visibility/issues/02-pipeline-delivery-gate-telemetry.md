# 02: In-Sandbox Pipeline Delivery Gate Telemetry

**What to build:** Emit structured `delivery_gate` telemetry events from the in-sandbox assembly line pipeline when a Feature Pull Request is initialized as a draft or finalized as ready for review.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] In `sandbox/factory/pipeline.ts`, emit a structured `delivery_gate` telemetry event via `emitTelemetryEvent` upon successful execution of `tracker.initializeDeliveryGate` containing pull request number, HTML URL, branch, title, and `draft: true`.
- [x] In `sandbox/factory/pipeline.ts`, emit an updated `delivery_gate` telemetry event upon successful execution of `tracker.finalizeDeliveryGate` containing pull request number, HTML URL, branch, and `ready_for_review: true`.
- [x] In `sandbox/factory/events.ts`, ensure `delivery_gate` is recognized as a typed telemetry event with helper functions if needed.
- [x] Update `sandbox/factory/pipeline.test.ts` to assert that `delivery_gate` telemetry envelopes are properly emitted over container output during gate initialization and finalization.

## Answer

Structured `delivery_gate` telemetry events have been integrated into the in-sandbox assembly line pipeline and telemetry emitter:
1. `sandbox/factory/events.ts` defines `"delivery_gate"` under `TelemetryEventType`, adds typed `DeliveryGateEventData`, `emitDeliveryGateEvent` helper (normalizing camelCase and snake_case aliases), and `AgentEventStream.prototype.emitDeliveryGate`.
2. `sandbox/factory/tracker/types.ts` & `sandbox/factory/tracker/github-tracker.ts` return `title` and `branch` on `DeliveryGateInitResult` and `DeliveryGateFinalizeResult`.
3. `sandbox/factory/pipeline.ts` invokes `emitDeliveryGateEvent` upon successful execution of `tracker.initializeDeliveryGate` (`draft: true`) and `tracker.finalizeDeliveryGate` (`ready_for_review: true`), while preserving `deliveryGateInitialized = true` across both GitHub and local trackers.
4. `sandbox/factory/pipeline.test.ts` and `sandbox/factory/events.test.ts` assert end-to-end container output emission and parsing of `delivery_gate` telemetry envelopes across batch and targeted single-issue executions.
