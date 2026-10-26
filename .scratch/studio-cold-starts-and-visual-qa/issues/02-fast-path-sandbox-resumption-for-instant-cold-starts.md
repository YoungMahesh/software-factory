# 02: Fast-Path Sandbox Resumption for Instant Cold Starts

**What to build:**
Instant cold-start sandbox provisioning that resumes existing Unified Studio Sandboxes from saved filesystem snapshot images in under 3 seconds. The sandbox spawner resolves warm snapshots from the database to instantiate the container image directly, bypassing image build staging, while the container entrypoint detects the resumed state to skip full repository cloning and redundant package installation, fetching only incremental branch updates before launching the dev server.

**Blocked by:** 01: Automatic Filesystem Snapshot Capture on Serving State

**Status:** resolved

- [x] Sandbox spawner queries the database for existing snapshot image identifiers for the target repository before falling back to full image building.
- [x] When a valid snapshot is found, the spawner instantiates the container directly from the snapshot image ID and passes the snapshot resumption signal.
- [x] Container startup logic detects the resumption signal and bypasses Git clone and full package installation sequences.
- [x] Resumed container performs a fast incremental fetch and checkout of the requested branch.
- [x] Dependency drift detection checks if dependency manifests changed relative to the snapshot commit, running an incremental install only when necessary.
- [x] Development server starts immediately upon workspace ref checkout, reducing cold-start boot time to under 3 seconds.
- [x] Transparent fallback mechanism defaults to full base image building if a snapshot image is missing, corrupt, or expired.
- [x] Automated tests verify snapshot image resolution, parameter propagation, resumption fast-path execution, and fallback handling.

## Answer

Implemented fast-path sandbox resumption for instant cold starts:
1. Extended `PreviewSpawnConfig` in `factory/spawner/_config.py` with `from_snapshot: str | None = None` and `snapshot_resume: bool = False`.
2. Updated `factory/spawner/_preview.py` to directly instantiate images using `modal.Image.from_id(config.from_snapshot)` when available, pass `SNAPSHOT_RESUME="1"` in the environment, and pass `--snapshot-resume` in container arguments.
3. Added `resolve_snapshot_image_id` and `spawn_preview_sandbox_with_fallback` in `factory/ui/registry/_snapshot.py`, queried before base image building in `_run_preview_worker` (`factory/ui/registry/_preview.py`), with transparent fallback to base image creation if snapshot resumption fails or if the snapshot is missing/expired.
4. Added snapshot fast-path resumption to `shared/factory_entrypoint.sh` detecting `SNAPSHOT_RESUME=1` and `--snapshot-resume`:
   - Bypasses full `git clone` and uses existing `/root/<repo>` directory.
   - Sourced `.factory.env` credentials if present.
   - Fast-fetches and checks out target branch ref (`+refs/heads/${BRANCH_NAME}:refs/remotes/origin/${BRANCH_NAME}`).
   - Detects dependency drift on `package.json` / `pnpm-lock.yaml` / `package-lock.json` and runs `pnpm install --prefer-offline` only when manifests drift.
   - Launches `start_dev_preview_supervisor` immediately upon ref checkout, reducing cold starts to < 3 seconds.
   - Falls back gracefully to clean clone and setup if target directory is invalid.
5. Added automated subsystem and integration tests in `tests/test_preview/test_resumption.py` (407 lines) and updated `tests/test_preview/test_registry.py` (289 lines). All 487 tests pass cleanly and all files adhere to the <= 500 lines budget.
