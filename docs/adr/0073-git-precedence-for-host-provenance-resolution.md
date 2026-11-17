# Git Precedence for Host Provenance Resolution and Ambient Environment Isolation

**Status**: Accepted (Amends [ADR 0059](0059-sandbox-software-factory-commit-provenance.md) and [ADR 0069](0069-control-plane-deployment-provenance-and-clean-tree-enforcement.md))

We establish that local Git repository inspection takes precedence over ambient process environment variables during `software-factory` provenance resolution whenever a valid Git repository checkout is detected, while preserving environment variable fallback for serverless cloud execution and providing an explicit opt-in override (`SOFTWARE_FACTORY_FORCE_ENV=1`) for CI environments.

## Context

[ADR 0059](0059-sandbox-software-factory-commit-provenance.md) established Git commit provenance resolution (`resolve_host_software_factory_provenance`) to stamp `software-factory` revision metadata across container environments, version files, and snapshot registries. [ADR 0069](0069-control-plane-deployment-provenance-and-clean-tree-enforcement.md) subsequently extended this mechanism to inject deployment provenance into Modal control plane secrets (`modal deploy sandbox/function.py`) and enforce clean working trees prior to deployment.

However, the resolution hierarchy in `sandbox/provenance.py` checked process environment variables (`SOFTWARE_FACTORY_COMMIT`, `SOFTWARE_FACTORY_COMMIT_SHORT`, `SOFTWARE_FACTORY_REF`, `SOFTWARE_FACTORY_DIRTY`) *before* executing Git commands (`git rev-parse HEAD`). This created a serious failure mode in self-hosted development environments:
1. **Ambient Environment Stagnation**: When development sandboxes boot, `shared/startup.sh` exported the initial container launch commit to `/etc/environment` and `~/.bashrc`. If `software-factory` was developed and committed inside such a sandbox, subsequent Git commits were masked by the stale environment variables from sandbox boot time.
2. **Deceptive Control Plane Deployments**: Running `modal deploy sandbox/function.py` from within a development sandbox read the stale ambient `SOFTWARE_FACTORY_COMMIT` from `~/.bashrc`, silently deploying new codebase files with an old Git commit SHA baked into cloud secrets and rendered in the Web UI badge.
3. **Dirty Tree Bypass**: Because `SOFTWARE_FACTORY_DIRTY="0"` was exported in `~/.bashrc`, `validate_clean_working_tree` failed to query `git status --porcelain`, allowing uncommitted local edits to be deployed without developer awareness.

## Decisions

1. **Live Git Precedence over Ambient Environment**:
   - In `sandbox/provenance.py`, `resolve_host_software_factory_provenance(repo_root)` now inspects the local Git repository (`(target_dir / ".git").exists()`) directly via `git rev-parse HEAD`, `git rev-parse --short HEAD`, `git symbolic-ref --short HEAD`, and `git status --porcelain`.
   - Ambient process environment variables no longer override the local Git repository checkout.

2. **Explicit Opt-In CI Override (`SOFTWARE_FACTORY_FORCE_ENV`)**:
   - To support continuous integration (CI) workflows (e.g. shallow checkouts, detached HEADs in GitHub Actions, or testing fixtures), environment variables take precedence only when `SOFTWARE_FACTORY_FORCE_ENV="1"` is explicitly set.

3. **Cloud Runtime Fallback**:
   - In environments where `.git` is absent (such as inside deployed Modal cloud containers where `.git` is not copied), `resolve_host_software_factory_provenance` cleanly falls back to `os.environ` injected via `modal.Secret`.

4. **Prevent Static Shell Stamping in Software-Factory Workspaces**:
   - In `shared/startup.sh`, the sandbox boot script checks if `$TARGET_DIR` contains `.git` and is a `software-factory` repository. If so, it skips writing static `export SOFTWARE_FACTORY_*` statements to `~/.bashrc` and `/etc/environment`, allowing developer subshells to dynamically resolve Git provenance.

## Consequences

- Deploying the control plane (`modal deploy sandbox/function.py`) from any environment containing a Git repository accurately captures the exact active Git HEAD and working tree status.
- Ambient environment variables stamped during container initialization can no longer spoof local Git state or bypass dirty working tree validation.
- Unit tests and CI pipelines retain full determinism via `SOFTWARE_FACTORY_FORCE_ENV=1`.
- The universal file line budget (`tests/test_standards.py`) is strictly maintained.
