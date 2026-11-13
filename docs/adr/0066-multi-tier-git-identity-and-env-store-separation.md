# Multi-Tier Git Identity and Env-Store Authorship Separation

**Status**: Accepted (Amends [ADR 0054](0054-codebase-de-hardcoding-and-parameterization.md) and [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md))

We introduce multi-tier Git identity support across Modal sandboxes and developer CLI workflows, allowing global fallback authorship via `DEFAULT_GIT_NAME` and `DEFAULT_GIT_EMAIL` in `.env`, coupled with repository-specific identity overrides stored in `<repo>/git.env` within the Central Environment Store (`env-store`), while completely removing synthetic fallback identities and strictly decoupling Git authorship from application `.env` files.

## Context

When committing from T3 Code Web UI or automated agent processes inside Modal sandboxes, Git operations require a configured author and committer identity (`user.name` and `user.email`). Previously:
1. `shared/startup.sh` exported environment variables `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` with synthetic fallback values (`Modal Sandbox User <sandbox@modal.local>`), which were not registered in global or local Git configuration files (`.gitconfig` or `.git/config`).
2. Non-interactive daemons and background server processes (including T3 Code's Git VCS driver) that do not source interactive shell profiles failed with `Git command exited with a non-zero status` due to unconfigured Git identity.
3. Users managing multiple target repositories across different GitHub accounts or identities had no automated mechanism to override Git authorship per repository.
4. Git author credentials must not be mixed into project `.env` files, as project `.env` files are intended exclusively for application runtime secrets and should not contain Git configuration.

## Decisions

1. **Multi-Tier Git Identity Resolution Hierarchy**:
   - **Tier 1 (Repository-Specific Override)**: Stored in `<repo>/git.env` inside the `env-store` vault. Retrieved during sandbox launch or `ghclone` / `pull-repo-env`, and applied strictly as local Git configuration (`git -C <repo> config --local user.name` and `user.email`).
   - **Tier 2 (Global Default Authorship)**: Configured via `DEFAULT_GIT_NAME` and `DEFAULT_GIT_EMAIL` in the host `.env` file or environment. Applied globally inside sandboxes (`git config --global user.name` and `user.email`) and exported for sub-processes.
   - **Tier 3 (Host Git Configuration Fallback)**: Resolved by `SandboxLauncher` from host `git config user.name` and `user.email` if Tier 1 and Tier 2 are not set.

2. **Strict Decoupling of Git Authorship from Project `.env`**:
   - `git.env` is stored as an independent file (`<repo>/git.env`) in the `env-store` vault, separate from application secrets (`<repo>/default.env`).
   - `git.env` is never written to the project's `.env` file during sandbox provisioning or `ghclone`.
   - Variables `TARGET_GIT_AUTHOR_NAME` and `TARGET_GIT_AUTHOR_EMAIL` injected into sandbox startup are applied directly to local Git config and scrubbed from the environment immediately afterward.

3. **Retirement of Synthetic Fallback Identities**:
   - Completely remove `Modal Sandbox User` and `sandbox@modal.local` fallbacks from `shared/startup.sh`.
   - If neither a repository override nor a default/host identity is provided, Git remains unconfigured, and empty repository initial commits in standalone runs are skipped.

4. **Dedicated CLI Sub-Command for Authorship Management**:
   - Add a dedicated `push-repo-env git` sub-command:
     ```bash
     push-repo-env git [--name <name>] [--email <email>] [-r <repo>] [-o <org>]
     ```
   - Encrypts and pushes `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` to `<repo>/git.env` via the GitHub REST API.
   - Update `pull-repo-env` and `ghclone` to automatically fetch `<repo>/git.env` and apply `git config --local` to target repositories.

## Consequences

- **Reliable T3 Code Commits**: Git commits succeed cleanly in T3 Code Web UI and background daemons without auto-detection errors.
- **Multi-Account Authorship**: Different target repositories automatically receive their correct, designated Git commit author and email without manual configuration.
- **Clean Separation of Concerns**: Application secrets and Git identity remain strictly partitioned in `env-store` and on the local filesystem.
- **Zero Synthetic Identities**: Commits are never attributed to dummy or synthetic sandbox users.
