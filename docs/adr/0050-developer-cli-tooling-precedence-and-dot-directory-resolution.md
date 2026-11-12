# Developer CLI Tooling Precedence and Dot-Directory Resolution

**Status**: Accepted (Amends [ADR 0005](0017-in-sandbox-tooling-secrets-and-setup-script-staging.md) and [ADR 0043](0043-sandbox-dot-directories-for-secrets-and-scripts.md))

We establish an explicit precedence hierarchy for developer CLI tooling (`agyq`, `ghls`, `ghpr`, `ghclone`, `agyprofile`, `decrypt-repo-env`, `encrypt-repo-env`) inside Modal sandboxes and implement dynamic dot-directory resolution across `shared/image.py` to prevent stale container binaries from shadowing active repository versions and staged scripts.

## Context

ADR 0043 migrated staging directories from `/root/scripts` and `/root/secrets` to hidden dot-directories `/root/.scripts` and `/root/.secrets`. However, two integration gaps emerged:

1. **Static Local Path Resolution in `shared/image.py`**:
   `LOCAL_SCRIPTS_DIR` was hardcoded to `REPO_ROOT / "scripts"`. Inside the hosted Modal control plane container (`sandbox/function.py`) and inside active sandboxes, scripts are staged into `/root/.scripts` and secrets into `/root/.secrets`. As a result, `LOCAL_SCRIPTS_DIR` resolved to non-existent `/root/scripts`, causing `add_local_files_if_present()` to silently skip developer CLI tools when building sandbox images from within the control plane.
2. **Stale Pre-baked Image Binary Precedence in `shared/startup.sh`**:
   In `shared/startup.sh`, the staging loop guarded symlink creation with `[ ! -f "/usr/local/bin/$cmd" ]`. Because the pre-baked Modal base image already contains older versions of developer CLI utilities in `/usr/local/bin`, the guard prevented newly staged scripts in `/root/.scripts` from overwriting stale base image binaries.
3. **Absence of Workspace Repository Precedence**:
   When launching a development sandbox for a repository that provides updated versions of developer utilities (such as `software-factory` with updated rolling quota logic in `scripts/agyq`), `startup.sh` did not inspect `$TARGET_DIR/scripts`. Consequently, commands executed on `$PATH` invoked the stale pre-baked `/usr/local/bin` binary rather than the live repository version checked out in the workspace.

## Decisions

1. **Developer CLI Tooling Precedence Hierarchy**:
   We establish a strict three-tier precedence order for developer CLI binaries on `$PATH`:
   - **Tier 1: Workspace Repository (`$TARGET_DIR/scripts`)**: If the cloned or resumed target repository provides developer CLI tools (or Python counterparts such as `decrypt_repo_env.py`), `shared/startup.sh` symlinks them into `/usr/local/bin`, giving live workspace scripts highest priority.
   - **Tier 2: Staged Dot Directory (`/root/.scripts`)**: For sandboxes without workspace repository scripts (or standalone sandboxes), staged scripts in `/root/.scripts` (or `/root/scripts`) force-symlink (`ln -sf`) into `/usr/local/bin`, overwriting stale image fallbacks.
   - **Tier 3: Pre-baked Base Image Binary (`/usr/local/bin`)**: The base container binaries serve as the ultimate fallback when neither workspace repository scripts nor staged dot-directory scripts exist.

2. **Dynamic Dot-Directory Script and Secret Resolution in `shared/image.py`**:
   - Introduce dynamic resolution helpers (`_resolve_dir` and `_resolve_file`) in `shared/image.py` inspecting candidate directories (`scripts`, `.scripts`, `/root/.scripts`, `/root/scripts`, `.secrets`, `secrets`, `/root/.secrets`, `/root/secrets`).
   - Define both `LOCAL_SCRIPTS_DIR` and `LOCAL_SECRETS_DIR` dynamically to track valid directory roots across host developer machines, control plane containers, and active sandboxes.
   - Ensure all developer CLI tools (`LOCAL_AGYQ`, `LOCAL_GHLS`, etc.) and secrets (`LOCAL_OPENCODE_SECRET`, `LOCAL_ANTIGRAVITY_SECRET*`, `LOCAL_MODAL_SECRET`, `LOCAL_CLOUDFLARE_SECRET`, `LOCAL_GITHUB_ORGS_SECRET`) resolve existing disk files across both dot-prefixed and non-dot-prefixed staging paths.

3. **Convenience Symlink Cycle Prevention**:
   In `shared/startup.sh`, convenience symlinks in `/root/.scripts` pointing to `/usr/local/bin` verify realpaths to prevent circular symlink chains between `/root/.scripts/$cmd` and `/usr/local/bin/$cmd`.

## Consequences

- **Live Script Reactivity**: Updates to scripts in `$TARGET_DIR/scripts` (such as `scripts/agyq` rolling quota calculations) immediately take effect in `/usr/local/bin` and `$PATH` without requiring image rebuilds or manual symlink recreation.
- **Control Plane Consistency**: When the hosted control plane (`sandbox/function.py`) builds sandbox images, `shared/image.py` accurately discovers staged developer tools in `/root/.scripts` and secrets in `/root/.secrets`.
- **Clean Fallback Chain**: Environments without a target repository or staged files gracefully fall back to base image binaries.
