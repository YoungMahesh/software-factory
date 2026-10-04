# Shared Agent Configurations and In-Sandbox SOPS Antigravity Token

Previously, agent configurations (`opencode.json`, `settings.json`, `keybindings.json`) were duplicated across `standard_sandbox/` and `vm_sandbox/`, and sandbox runners attempted to inspect and bake unencrypted credentials from the developer's local workstation into container images. We decided to consolidate all shared agent configuration files into the top-level `shared/` directory and encrypt the Antigravity OAuth token at `secrets/antigravity-oauth-token.json`. Sandbox runners no longer read credentials from the host machine or `~/.gemini`; instead, specifying `--agy` automatically enables in-sandbox SOPS decryption via `scripts/setup.sh`, which decrypts the token directly into `~/.gemini/antigravity-cli/antigravity-oauth-token` (mode 0600).

## Considered Options

- **Mount unencrypted host credentials at image build time**: Read credentials from the host developer's `~/.gemini/antigravity-cli/antigravity-oauth-token` or repo directory and bake them into the container image layers. Rejected because it exposes sensitive credentials across container layers and fails in environments without local CLI authentication.
- **Maintain separate configuration files per sandbox directory**: Keep duplicate copies of `settings.json`, `keybindings.json`, and `opencode.json` inside both `standard_sandbox/` and `vm_sandbox/`. Rejected because it creates configuration drift and maintenance overhead when tuning agent tools and keybindings.
- **Unified shared configuration with in-sandbox SOPS token decryption**: Consolidate configuration files into `shared/`, track the encrypted token in `secrets/antigravity-oauth-token.json`, and decrypt credentials entirely inside the sandbox via `scripts/setup.sh` when `--agy` or `--sops` is specified. Accepted because it eliminates secret leakage into cached image layers, ensures configuration parity between Standard and VM sandboxes, and relies purely on the repository's SOPS + Age key architecture.

## Consequences

- `standard_sandbox/main.py` and `vm_sandbox/main.py` reference `shared/opencode.json`, `shared/antigravity-settings.json`, and `shared/antigravity-keybindings.json`.
- Sandbox runners never access or inspect the host developer's `~/.gemini/` directory or unencrypted token files.
- Passing `--agy` automatically enables SOPS decryption (`ENABLE_SOPS=1`), ensuring `scripts/setup.sh` decrypts `secrets/antigravity-oauth-token.json` to `~/.gemini/antigravity-cli/antigravity-oauth-token` with 0600 permissions.
- Sandboxes require `AGE_PRIVATE_KEY` in their Modal secret collection when `--agy` is passed to authenticate the CLI.
