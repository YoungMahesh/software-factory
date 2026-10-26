# 01: Automatic Filesystem Snapshot Capture on Serving State

**What to build:**
Automated root filesystem snapshot capture for Unified Studio Sandboxes once an application container successfully reaches the active serving state. Extends the database persistence layer to record snapshot metadata linked to each target repository, executes non-destructive container snapshotting in the background without interrupting active developer previews, registers the snapshot with a 30-day retention Time-To-Live, and logs the captured image identifier for future cold-start acceleration.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Database schema and persistence helpers store and retrieve snapshot image identifiers, commit SHAs, and capture timestamps for repositories.
- [x] Preview registry monitors active sandbox lifecycles and detects when a sandbox transitions into the active serving status.
- [x] Background snapshot worker asynchronously executes filesystem synchronization (`sync`) and invokes non-destructive snapshot capture with a 30-day retention period.
- [x] Active container remains running and serving traffic without termination or preview downtime during and after snapshot capture.
- [x] Captured snapshot image identifier and associated repository commit SHA are persisted in the database.
- [x] Snapshot capture errors do not crash the running preview or disrupt client connections.
- [x] Automated tests verify database persistence, lifecycle state triggers, and background snapshot worker dispatch.

## Answer

Implemented non-destructive automatic filesystem snapshot capture on serving state:
1. Extended SQLite previews table with snapshot metadata (`snapshot_image_id`, `snapshot_commit_sha`, `snapshot_captured_at`) and persistence helpers (`save_snapshot_metadata`, `get_snapshot_metadata`) in `factory.ui.db`.
2. Created `factory/ui/registry/_snapshot.py` implementing `capture_snapshot_in_background` which runs `sync`, invokes non-destructive `modal.Image.from_registry` / `sb.snapshot_filesystem(ttl=30*86400)`, queries repository HEAD commit SHA, and records metadata without interrupting running previews.
3. Hooked transition to `PreviewStage.SERVING` in `factory/ui/registry/_preview.py` to trigger background snapshot capture in an isolated thread.
4. Added test suites in `tests/test_ui_db.py` and `tests/test_preview/test_snapshot.py`. All tests pass and line budgets are maintained.
