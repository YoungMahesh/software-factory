# Mandatory Resource Plane SSH Key and In-Repo Secrets Directory

**Status**: Accepted (Amends [ADR 0082](0082-strict-resource-plane-deployment-configuration-and-idempotency.md)).

## Context

ADR 0082 established strict configuration requirements for `RESOURCE_PLANE_SSH_HOST` while eliminating legacy `DB_HOST_SSH_*` aliases. However, `RESOURCE_PLANE_SSH_KEY` remained optional, falling back to ambient user SSH keys (`~/.ssh/id_rsa`, `~/.ssh/id_ed25519`) or an active SSH agent.

In practice, ambient SSH fallbacks introduce ambiguity, configuration drift across machines and automated environments, and unpredictable deployment failures when an ambient key lacks root access to the target VPS.

Furthermore, SSH private keys are multi-line PEM files. SOPS encryption of dotenv files fails when values contain physical line breaks (`invalid dotenv input line`), and standard `.env` parsers break on multi-line values. Encoding keys as base64 in `.env` introduces runtime decoding overhead, requiring tools to write temporary files with strict permissions before every SSH call.

## Decision

1. **Mandatory SSH Key Configuration**: `RESOURCE_PLANE_SSH_KEY` is strictly required in `.env` or via `--key`. Ambient SSH fallbacks and ambient SSH agent execution without explicit key specifications are removed. `modal-sandbox infra deploy` strictly requires `RESOURCE_PLANE_SSH_KEY` and always passes `-i <key_path>` to `ssh`.
2. **In-Repo Secrets Directory (`.secrets/`)**: Standardize private key placement inside the repository at `.secrets/resource_plane_ssh` (extensionless per Linux OpenSSH conventions). The entire `.secrets/` directory is ignored in `.gitignore`.
3. **Automatic Path Resolution and Permission Hardening**:
   - Relative paths in `RESOURCE_PLANE_SSH_KEY` resolve deterministically against `resolve_factory_root()`.
   - Missing key files raise `FileNotFoundError` immediately before launching network operations.
   - If key file permissions are more open than `0600` on POSIX systems, `infra_deploy` automatically normalizes them to `0600` (`chmod 600`) and logs the action to prevent OpenSSH permission rejections.
4. **Secret Vault Synchronization (`env-store`)**: Extensionless keys are synchronized to the central `env-store` vault using `push-repo-env -e .secrets/resource_plane_ssh -d resource_plane_ssh --allow-binary`. Decryption via `pull-repo-env` preserves the `env.map` destination and automatically sets `0600` permissions.

## Consequences

- SSH connection credentials for the Resource Plane are explicit, isolated, and deterministic across workstations and CI environments.
- Private keys can be safely stored within the repository without risk of accidental git staging or SOPS multiline dotenv parse failures.
- File permission errors with OpenSSH are eliminated through proactive validation and automatic permission hardening.
