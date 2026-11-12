# Sandbox Software-Factory Commit Provenance and Inspection Tooling

**Status**: Accepted (Amends [ADR 0002](0013-unified-sandbox-runner.md), [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md), and [ADR 0052](0052-collapse-sandbox-provisioning-seam.md))

We establish end-to-end Git commit provenance tracking for Modal sandboxes, stamping the `software-factory` revision and dirty working tree status across container environment variables, persistent machine version files, Modal tags, and snapshot registries, backed by an in-container diagnostic utility (`check-software-factory` / `check-sf`).

## Context

Modal sandboxes are decoupled cloud environments provisioned by `software-factory` to host target repositories, developer tools, and AI agents. The container image layers (`shared/image.py`) and boot scripts (`shared/startup.sh`, `scripts/setup.sh`, `shared/t3_usage_sync.py`) are baked directly from the host `software-factory` checkout into the container filesystem.

When issues or behavioral regressions occur inside a sandbox (or when resuming an older snapshot), diagnosing the root cause previously suffered from an absence of origin metadata:
1. **Target Repository Isolation**: Inside the container, the cloned repository in `/root/<repo-name>` is the target application repository (e.g. `sFactory0/my-app`), not `software-factory`. There was no direct record indicating which revision of `software-factory` provisioned the container.
2. **Snapshot Age Drift**: Sandboxes captured as filesystem snapshots (`--from-snapshot`) preserve disk contents and baked scripts indefinitely. When resumed days or weeks later by a newer `software-factory` launcher, engineers could not distinguish between the snapshot's initial creation commit and the launcher's current commit.
3. **Uncommitted Local Edits**: During rapid development on `software-factory`, uncommitted host modifications in `shared/startup.sh` or `sandbox/launcher.py` were baked into sandboxes without recording dirty status, making comparisons against clean GitHub commits deceptive.

## Decisions

1. **Host Provenance Resolution Seam (`resolve_host_software_factory_provenance`)**:
   - In `sandbox/launcher.py`, implemented `resolve_host_software_factory_provenance(repo_root)` with a robust fallback hierarchy:
     1. Respect explicit process environment variables (`SOFTWARE_FACTORY_COMMIT`, `SOFTWARE_FACTORY_COMMIT_SHORT`, `SOFTWARE_FACTORY_REF`, `SOFTWARE_FACTORY_DIRTY`).
     2. Query host Git repository via `git rev-parse HEAD`, `git rev-parse --short HEAD`, `git symbolic-ref --short HEAD` (or `--abbrev-ref`), and `git status --porcelain`.
     3. Fall back safely to `"unknown"`, `"unknown"`, `"unknown"`, `"0"` when `.git` is unavailable (e.g. deployed control plane functions).

2. **Container Injection and Modal Tagging**:
   - `SandboxLauncher.launch()` injects the four provenance variables into the container environment dictionary.
   - Attaches provenance metadata to Modal Sandbox `tags`:
     ```python
     "tags": {
         "instance_name": sandbox_name,
         "app_name": app_name,
         "software_factory_commit": provenance["SOFTWARE_FACTORY_COMMIT_SHORT"],
         "software_factory_dirty": provenance["SOFTWARE_FACTORY_DIRTY"],
     }
     ```

3. **In-Sandbox Persistence & Snapshot Lineage**:
   - In `shared/startup.sh`, provenance variables are exported to `/etc/environment` and `~/.bashrc` for subshell and login consistency.
   - Written to `/etc/software-factory-version.json`. When resuming from a snapshot (`RESUME_SNAPSHOT=1`), the original creation commit is preserved as `origin_commit` and the resumption launch commit is recorded as `resumed_commit`.

4. **In-Container Inspection Utility (`check-software-factory` / `check-sf`)**:
   - Installed `/usr/local/bin/check-software-factory` and symlinked `/usr/local/bin/check-sf`.
   - Formats provenance details and outputs an actionable GitHub comparison URL:
     `https://github.com/${GH_ORG_NAME:-sFactory0}/software-factory/compare/<commit>...main`

5. **Snapshot Registry Integration**:
   - `record_snapshot()` in `sandbox/snapshots.py` captures `software_factory_commit` and `software_factory_dirty`, ensuring snapshot metadata in `modal.Dict` and local fallback retains factory lineage.

## Consequences

- Engineers and agents inside sandboxes can instantly verify container provenance and view GitHub diffs via `check-software-factory`.
- Control plane listings and snapshot registries display container build revisions and dirty indicators without container entry.
- Resumed snapshots maintain unambiguous audit trails between original image creation and resumption time.
- Zero performance overhead or boot latency degradation.
