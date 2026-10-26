# 02: Fast-Path Sandbox Resumption for Instant Cold Starts

**What to build:**
Instant cold-start sandbox provisioning that resumes existing Unified Studio Sandboxes from saved filesystem snapshot images in under 3 seconds. The sandbox spawner resolves warm snapshots from the database to instantiate the container image directly, bypassing image build staging, while the container entrypoint detects the resumed state to skip full repository cloning and redundant package installation, fetching only incremental branch updates before launching the dev server.

**Blocked by:** 01: Automatic Filesystem Snapshot Capture on Serving State

**Status:** claimed

- [ ] Sandbox spawner queries the database for existing snapshot image identifiers for the target repository before falling back to full image building.
- [ ] When a valid snapshot is found, the spawner instantiates the container directly from the snapshot image ID and passes the snapshot resumption signal.
- [ ] Container startup logic detects the resumption signal and bypasses Git clone and full package installation sequences.
- [ ] Resumed container performs a fast incremental fetch and checkout of the requested branch.
- [ ] Dependency drift detection checks if dependency manifests changed relative to the snapshot commit, running an incremental install only when necessary.
- [ ] Development server starts immediately upon workspace ref checkout, reducing cold-start boot time to under 3 seconds.
- [ ] Transparent fallback mechanism defaults to full base image building if a snapshot image is missing, corrupt, or expired.
- [ ] Automated tests verify snapshot image resolution, parameter propagation, resumption fast-path execution, and fallback handling.
