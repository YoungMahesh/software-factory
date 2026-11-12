# Pre-bake GitHub CLI in Shared Base Image

**Status**: Accepted (Amends [ADR 0005](0008-unified-base-image-for-standard-and-vm-sandboxes.md), [ADR 0002](0019-prebake-docker-compose-v2-in-shared-base-image.md), [ADR 0025](0025-t3-code-server-and-agent-control-surface.md), and [ADR 0038](0038-centralized-org-credentials-and-in-repo-secrets.md))

## Context

Sandboxes running T3 Code (`--t3`/`--t3code`) execute agent workflows where coding agents (Antigravity, Claude Code, Codex, OpenCode) create pull requests, monitor review comments, inspect CI checks, and interact with repository issues. Furthermore, skills such as `t3dotgg/tstack` (`file-pr`, `babysit-pr`, `takeover`) rely directly on the GitHub CLI (`gh`).

While `shared/startup.sh` was previously configured in ADR 0038 to retain `GH_TOKEN` in `/etc/environment` and `~/.bashrc` specifically when `--t3` is passed, the GitHub CLI binary (`gh`) was not installed in the container image. As a result, agents and automated skills attempting to file or inspect pull requests failed with `command not found: gh`.

## Considered Options

- **Dynamic runtime installation in `startup.sh` on every launch**: Download and install `gh` during sandbox boot when `ENABLE_T3=1`. Rejected because downloading packages at startup introduces latency and external network failure modes to sandbox startup.
- **Install only in the incremental T3 Code layer (`build_sandbox_image(t3=True)`)**: Layer `gh` conditionally in `build_sandbox_image` only when `t3` is true. Rejected because GitHub CLI is universally useful across all developer workflows (interactive SSH sessions, OpenCode, Antigravity CLI, issue tracking) and diverging image definitions fragments Modal layer caching parity between Standard and VM Sandboxes.
- **Pre-bake `gh` in Shared Base Image via `base_image.apt_install()`**: Install `gh` directly via `base_image.apt_install()` in `shared/image.py`. Accepted because Ubuntu 24.04 (`noble`) provides `gh` natively, it maintains 100% Modal base layer cache parity, adds negligible image overhead (~30MB), and guarantees instant zero-config availability. Combined with `GH_TOKEN` retention for T3 Code, `gh` is pre-authenticated out of the box.

## Consequences

- `gh` is added to `base_image.apt_install()` in `shared/image.py`.
- `/usr/local/bin/check-t3` in `shared/startup.sh` is updated to verify `gh --version` and report `gh auth status`.
- In T3 Code sessions (`--t3`), agents and users can immediately run `gh pr create`, `gh pr checks`, `gh issue view`, and PR skills without manual installation or authentication steps.
- All sandboxes (Standard and VM) carry the GitHub CLI binary without runtime performance or boot penalties.
