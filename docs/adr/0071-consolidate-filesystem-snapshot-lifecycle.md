# Consolidate Filesystem Snapshot Lifecycle into Deep Snapshot Module

**Status**: Accepted (Amends [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md) and [ADR 0040](0040-hosted-sandbox-control-plane-function.md))

We consolidate filesystem buffer flushing, VM detection, Modal filesystem capture, persistent catalog indexing, and optional container termination into a single deep module `sandbox/snapshots.py` (`capture_sandbox_snapshot()`), returning an encapsulated `SnapshotResult` domain model and resolving an active defect where CLI snapshot invocations bypassed persistent registry recording.

## Context

Prior to this decision, snapshot execution logic was fractured across three shallow modules:
1. `sandbox/snapshots.py` owned metadata storage and queries (`record_snapshot`, `list_snapshots`, `delete_snapshot`) via `modal.Dict` and local JSON fallback, but did not execute snapshot capture.
2. `sandbox/cli.py:capture_snapshot()` performed container buffer flushing (`sync`), VM detection, and Modal filesystem snapshotting (`sandbox.snapshot_filesystem()`), but omitted `record_snapshot()`. Consequently, snapshots created via `modal-sandbox --snapshot` never appeared in the persistent catalog or the Web UI dashboard.
3. `sandbox/core.py:capture_snapshot_core()` duplicated the buffer flushing, VM detection, and filesystem capture, and invoked `record_snapshot()`.

This duplication broke locality, created inconsistent behavior between CLI and Web Control Plane operations, and forced tests to mock divergent seams.

## Decisions

1. **Deep Snapshot Lifecycle Seam (`sandbox/snapshots.py`)**:
   - Provide `capture_sandbox_snapshot()` as the canonical execution seam for creating and recording filesystem snapshots.
   - Encapsulate profile and client resolution, filesystem `sync`, VM runtime detection, `snapshot_filesystem()`, catalog recording via `record_snapshot()`, formatted status reporting, and container termination behind one interface.

2. **Rich `SnapshotResult` Domain Result**:
   - Introduce `SnapshotResult` encapsulating `sandbox_id`, `image_id`, `ttl_days`, `ttl_seconds`, `terminated`, `name`, `is_vm`, `profile`, and commit provenance.
   - Provide `.to_response() -> SnapshotResponse` projection for seamless FastAPI and Pydantic serialization.

3. **Thin Interface Adapters**:
   - `sandbox/cli.py:capture_snapshot()` becomes a thin adapter delegating directly to `capture_sandbox_snapshot(..., echo=True)` and returning `image_id`.
   - `sandbox/core.py:capture_snapshot_core()` is maintained as a deprecated adapter delegating to `capture_sandbox_snapshot(..., echo=False).to_response()`.

## Consequences

- Resolves the defect where CLI snapshots bypassed persistent catalog indexing; all snapshots now register in `modal.Dict` and local fallback.
- Buffer synchronization, VM detection, and capture logic are consolidated into one deep module.
- CLI, Web API, and Hosted Control Plane share identical capture semantics.
