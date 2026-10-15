# 02: In-Sandbox Pipeline Delivery Gate Telemetry

**What to build:** Emit structured `delivery_gate` telemetry events from the in-sandbox assembly line pipeline when a Feature Pull Request is initialized as a draft or finalized as ready for review.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] In `sandbox/factory/pipeline.ts`, emit a structured `delivery_gate` telemetry event via `emitTelemetryEvent` upon successful execution of `tracker.initializeDeliveryGate` containing pull request number, HTML URL, branch, title, and `draft: true`.
- [ ] In `sandbox/factory/pipeline.ts`, emit an updated `delivery_gate` telemetry event upon successful execution of `tracker.finalizeDeliveryGate` containing pull request number, HTML URL, branch, and `ready_for_review: true`.
- [ ] In `sandbox/factory/events.ts`, ensure `delivery_gate` is recognized as a typed telemetry event with helper functions if needed.
- [ ] Update `sandbox/factory/pipeline.test.ts` to assert that `delivery_gate` telemetry envelopes are properly emitted over container output during gate initialization and finalization.
