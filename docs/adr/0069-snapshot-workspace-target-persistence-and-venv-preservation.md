# Snapshot Workspace Target Directory Persistence and Virtualenv Preservation

**Status**: Accepted (Amends [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md), [ADR 0050](0050-developer-cli-tooling-precedence-and-dot-directory-resolution.md), and [ADR 0059](0059-sandbox-software-factory-commit-provenance.md))

We establish explicit workspace target directory persistence and virtualenv preservation for Modal sandbox filesystem snapshots, preventing secondary repository clones (such as backup or mirror directories) from hijacking `TARGET_DIR` and corrupting the active Python environment on resumption.

## Context

Under [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md), Modal sandboxes can be frozen into filesystem snapshots and resumed with `RESUME_SNAPSHOT=1`, bypassing Git cloning and dependency installation.

When resuming from a snapshot where `GH_REPO` is not explicitly supplied in the resume command (e.g. offline resumption or resume by snapshot name), `shared/startup.sh` previously relied on an unweighted loop over `/root/*/` to auto-discover the target workspace:

```bash
for d in /root/*/; do
    if [ -d "${d}.git" ]; then
        TARGET_DIR="${d%/}"
        break
    fi
done
```

This heuristic exhibited critical failure modes when multiple Git repositories coexisted in `/root/`:
1. **Alphabetical Directory Hijacking**: If secondary repositories, backup clones (e.g. `/root/repo-backups`), or auxiliary checkouts existed alongside the primary repository (`/root/software-factory`), alphabetical expansion selected the backup directory first.
2. **Virtualenv Corruption**: The subsequent tooling setup in `shared/startup.sh` assumed the newly resolved `TARGET_DIR` lacked a virtual environment. It ran `uv venv --seed "$TARGET_DIR/.venv"` and installed only `modal`.
3. **Shell Activation Hijacking**: `shared/startup.sh` appended activation for the newly generated `.venv` to `~/.bashrc` and overwrote `/etc/profile.d/python-venv.sh`.
4. **Missing Dependencies**: When engineers or agents opened the resumed sandbox, the active environment was the newly created bare virtualenv rather than the project's fully installed virtualenv. Commands like `modal deploy sandbox/function.py` immediately crashed with `ModuleNotFoundError: No module named 'fastapi'`.

## Decisions

1. **Persistent Target Directory Markers (`/root/.workspace-target-dir` and `/etc/workspace-target-dir`)**:
   - During initial sandbox provisioning, once `TARGET_DIR` is established, `shared/startup.sh` writes the absolute path to `/root/.workspace-target-dir` and `/etc/workspace-target-dir`.
   - On snapshot resumption (`RESUME_SNAPSHOT=1`), `shared/startup.sh` checks the target directory marker files before initiating directory scans.

2. **Provenance Metadata Integration**:
   - `shared/startup.sh` records `target_dir` inside `/etc/software-factory-version.json` alongside commit provenance, providing a structured fallback.

3. **Resumption Resolution Hierarchy and Exclusion Patterns**:
   - When resuming from a snapshot, `TARGET_DIR` is resolved using the following precedence:
     1. `$GH_REPO` (if explicitly provided).
     2. `/root/.workspace-target-dir` or `/etc/workspace-target-dir`.
     3. `/etc/software-factory-version.json` (`target_dir` attribute).
     4. Existing `VIRTUAL_ENV` parent directory (if containing `.git`).
     5. Known primary repository checkout (`/root/software-factory`).
     6. Directory scan of `/root/*/` with explicit exclusion of backup and mirror patterns (`*backup*`, `*.bak`, `*copy*`).

4. **Virtualenv Preservation and Activation Guarding**:
   - On snapshot resume, existing virtual environments in `TARGET_DIR` are preserved without re-running `uv pip install modal` if the Modal binary already exists.
   - Shell activation profiles (`~/.bashrc` and `/etc/profile.d/python-venv.sh`) are kept pointing strictly to the validated `TARGET_DIR/.venv`.

## Consequences

- Sandboxes containing multiple Git repositories or backup mirrors resume reliably with the correct workspace root and tooling bindings.
- Fully baked virtual environments with complex dependencies (FastAPI, Pydantic, HTTPX, QR code, etc.) remain intact and active across snapshot restore cycles.
- Eliminates startup friction, broken CLI deployments, and `ModuleNotFoundError` regressions on snapshot cold starts.
