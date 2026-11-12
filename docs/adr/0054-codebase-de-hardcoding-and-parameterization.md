# Codebase De-Hardcoding and Parameterization

**Status**: Accepted (Amends [ADR 0003](0012-prebaked-cloudflared-and-default-tunnel-ingress.md), [ADR 0038](0038-centralized-org-credentials-and-in-repo-secrets.md), [ADR 0063](0063-replace-secret-flag-with-repo-flag-in-sandbox-runner.md), and [ADR 0053](0053-consolidate-secrets-to-single-dotenv-and-retire-legacy-staging.md))

We decouple the software factory codebase, runner tooling, container startup scripts, and base images from personal Git identities, private directory conditional routing, and hardcoded organization defaults, parameterizing configurable domains and namespaces to prepare the repository for open-source adoption.

## Context

To prepare this repository for an open-source fork, personal configurations and proprietary defaults needed to be eliminated:
1. **Hardcoded Ingress Domain**: The launch readiness banner printed `https://3000.mahesh0.dev`, and CLI help hardcoded `3000.mahesh0.dev`.
2. **Personal Git Profile & Directory Routing**: `shared/gitconfig` declared hardcoded authorship (`Mahesh <maheshghamand@gmail.com>`), staged a secondary profile `shared/gitconfig-mahesh471978` (`mahesh471978@gmail.com`), and conditionally routed private directories (`[includeIf "gitdir:/root/intrifund/"]`).
3. **Hardcoded Container Git Commits**: `shared/startup.sh` initialized empty Git repositories with hardcoded authorship (`Mahesh <maheshghamand@gmail.com>`).
4. **Hardcoded GitHub Organization Default**: `sandbox/config.py`, `shared/startup.sh`, and developer CLI scripts (`scripts/ghclone`, `scripts/ghls`, `scripts/ghpr`) defaulted unqualified repository names to `sFactory0`.

## Decisions

1. **Cloudflare Tunnel Domain Parameterization and Fallback**:
   - Parameterize public tunnel domain display via `os.getenv("MODAL_SANDBOX_TUNNEL_DOMAIN") or os.getenv("CLOUDFLARE_TUNNEL_DOMAIN", "")`.
   - In `sandbox/formatting.py`, print the formatted URL if configured (`https://{domain} (port 3000)`). If unset, announce `• Cloudflare: Active on port 3000 (set MODAL_SANDBOX_TUNNEL_DOMAIN to display custom URL)` without leaking personal or invalid URLs.
   - Remove hardcoded domain references from CLI help in `sandbox/cli.py` and `readme.md`.
   - Document `MODAL_SANDBOX_TUNNEL_DOMAIN` in `.env.example`.

2. **Retire Personal Git Profile and Base Image Uncoupling**:
   - Delete `shared/gitconfig-mahesh471978`.
   - Strip hardcoded `[user]` authorship and `[includeIf]` conditional inclusion blocks from `shared/gitconfig`, retaining generic base defaults (`defaultBranch = main` and GitHub credential helpers).
   - Remove `LOCAL_GITCONFIG_MAHESH471978` and `REMOTE_GITCONFIG_MAHESH471978` from `shared/image.py` base image staging manifests (`BASE_IMAGE_FILES`).

3. **Dynamic Host Git Identity Propagation and Startup Fallback**:
   - Implement `resolve_host_git_identity()` in `sandbox/launcher.py` to inspect the host workstation's Git identity (`user.name`, `user.email`, `GIT_AUTHOR_*`, `GIT_COMMITTER_*`) and inject them into container environment variables (`GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL`).
   - Update `shared/startup.sh` fallback from `Mahesh <maheshghamand@gmail.com>` to generic sandbox defaults (`Modal Sandbox User <sandbox@modal.local>`).
   - Export host Git identity variables to `~/.bashrc` and `/etc/environment` during container boot for shell and SSH session persistence.

4. **Default GitHub Organization Configuration (`GH_ORG_NAME`)**:
   - Decouple `DEFAULT_ORG` in `sandbox/config.py` to resolve strictly via `os.environ.get("GH_ORG_NAME", "")`.
   - When a repository without an owner prefix is provided to `sandbox/launcher.py`, `scripts/ghclone`, `scripts/ghls`, or `scripts/ghpr`, require an explicit owner/repo or fail fast if `GH_ORG_NAME` is unset.
   - Update developer CLI helper scripts to use `DEFAULT_ORG="${GH_ORG_NAME:-}"` and remove hardcoded `sFactory0` from usage documentation.

5. **Unified Test Organization Scope**:
   - Eliminate separate test organization configuration. Integration and live verification tests target the default organization (`GH_ORG_NAME`), using repositories prefixed with `test-` (such as `test-live-test1`).

6. **Documentation & Glossary Alignment**:
   - Update `GLOSSARY.md` definitions for **Test Organization Scope**, **Sandbox Git Configuration**, and **Cloudflare Tunnel Domain**.
   - Update `readme.md` and `AGENTS.md` verification guidelines.
