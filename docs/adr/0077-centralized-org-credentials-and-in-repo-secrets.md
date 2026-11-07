# Centralized Organization Credentials and In-Repo Secrets Architecture

**Status**: Accepted (Amends [ADR 0016](0016-unified-sandbox-runner.md), [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md), and [ADR 0076](0076-retire-factory-studio-and-assembly-line-to-focus-on-modal-sandboxes.md))

## Context
Previously, repository authentication and environment secrets were bound to individual host-side directories under `secrets/<project>/` (e.g., `secrets/<project>/fetch.env` and `secrets/<project>/env.map`) or `secrets_org/<org>/token`. This model had several limitations:
1. **Secret Sprawl and Synchronization Overhead**: Developers and automated systems had to maintain distinct folders of secrets on their local machines for every target repository.
2. **Coupling to Host Filesystem**: Launching a sandbox required mounting local filesystem directories into the container image, preventing clean launches from environments without pre-staged local secrets.
3. **Repository Migration**: With repositories consolidating under the `sFactory0` GitHub organization, individual repository fetch tokens became redundant with organization-level access.

## Decision
We decided to adopt a two-tier architecture: **Centralized Organization Credentials** for GitHub repository authentication and **In-Repo Secret Manifests** for project runtime environment variables.

1. **Centralized Organization Credentials (`secrets/github-orgs.env`)**:
   - A single SOPS-encrypted file at `secrets/github-orgs.env` stores personal access tokens for target GitHub organizations, formatted as `<ORG>_GH_TOKEN` (e.g. `SFACTORY0_GH_TOKEN=ghp_...`).
   - `sandbox/main.py` parses `--secret` (e.g. `sFactory0/software-factory` or shorthand `software-factory`), identifies the target organization, and stages `secrets/github-orgs.env` to `/root/secrets/github-orgs.env`.
   - `shared/startup.sh` decrypts `github-orgs.env` using `AGE_PRIVATE_KEY`, extracts the matching organization token into `GH_TOKEN`, and immediately scrubs the file from disk.
   - Retired legacy `secrets_org/` and per-project host directories (`secrets/repo-horizon/`, `secrets/intrifund/`, `secrets/neon/`, `secrets/software-factory/`).

2. **In-Repo Secret Manifest (`.secrets/env.map`)**:
   - Each target repository stores its SOPS-encrypted environment files directly inside `.secrets/` in the repository root, accompanied by an `env.map` manifest.
   - `env.map` defines key-value mappings of encrypted source files to destination paths (e.g., `studio.env=.env` or `web.env=apps/web/.env`).
   - During sandbox provisioning, after cloning the repository, `shared/startup.sh` reads `$TARGET_DIR/.secrets/env.map`, decrypts each mapped secret into its workspace location, and applies `chmod 600`.
   - If `.secrets/env.map` is absent, initialization continues cleanly without error.

3. **Tooling Credential Preservation**:
   - For T3 Code sessions (`--t3`), `GH_TOKEN` is retained in the process environment (`/etc/environment` and `~/.bashrc`) so `t3 serve` and child coding agents can query PRs and execute VCS operations without authentication errors.
   - In standard non-T3 sessions, `GH_TOKEN` is scrubbed from the shell environment.
   - Ephemeral repository identifiers such as `GH_REPO` are scrubbed from the shell environment and unset in the `t3` CLI wrapper post-clone. This prevents stale repository overrides, ensuring GitHub CLI and T3 Code dynamically detect git remotes from local repositories and worktrees.
   - Global Git configuration (`shared/gitconfig`) declaratively configures GitHub CLI as the credential helper (`credential.https://github.com.helper=!/usr/bin/gh auth git-credential`), enabling Git and T3 Code VCS drivers to authenticate against repositories cloned without inline credentials.
   - If `--sops` is specified, `AGE_PRIVATE_KEY` is preserved in `~/.config/sops/age/keys.txt`; otherwise, all SOPS keys and staging files are scrubbed before handoff.

## Consequences
- **Simplified Provisioning**: Launching sandboxes requires only `secrets/github-orgs.env` on the host; individual project secret directories are eliminated.
- **Portability**: Repositories carry their encrypted configurations directly in version control, verifiable and reproducible across developers.
- **Security Invariants Maintained**: All secrets at rest in Git remain encrypted via SOPS and age. Decrypted files in sandboxes are strictly restricted to `0600` permissions, and intermediate tokens are purged from container storage.
