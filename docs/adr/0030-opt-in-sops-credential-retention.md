# Opt-In SOPS Credential Retention for Interactive Sandboxes

Previously, ADR 0007 established that SOPS credentials (`AGE_PRIVATE_KEY` and `~/.config/sops`) must be unconditionally purged during sandbox bootstrap, and ADR 0008 retired the `--sops` flag from sandbox runners. While this enforced zero-leakage security, it prevented developers from using `sops` or inspecting encrypted repository files during interactive debugging sessions without manually re-entering keys. We decided to re-introduce `--sops` in `sandbox/main.py` as an explicit, opt-in developer flag: default sandbox launches remain strictly ephemeral per ADR 0007, but passing `--sops` sets `ENABLE_SOPS=1`, configures `~/.config/sops/age/keys.txt` (mode 0600), exports SOPS environment variables (`SOPS_AGE_KEY`, `SOPS_AGE_KEY_FILE`, `AGE_PRIVATE_KEY`) to `~/.bashrc` and `/etc/environment`, and bypasses the credential purge.

## Considered Options

- **Retain credentials unconditionally in all sandboxes**: Revert ADR 0007 entirely. Rejected because it exposes master encryption keys from `share0` to untrusted code and autonomous agents by default, violating least privilege.
- **Retain key file only without environment variables**: Keep `~/.config/sops/age/keys.txt` on disk but still unset `AGE_PRIVATE_KEY` and omit shell exports. Rejected because interactive SSH and `modal shell` sessions would face inconsistent environment configuration across tools that expect `SOPS_AGE_KEY` or `AGE_PRIVATE_KEY`.
- **Opt-in `--sops` flag with full shell persistence and inspection tooling**: Keep ephemerality as the secure default, but allow developers to pass `--sops` to retain `~/.config/sops/age/keys.txt`, export `SOPS_AGE_KEY`, `SOPS_AGE_KEY_FILE`, and `AGE_PRIVATE_KEY`, install `/usr/local/bin/check-sops`, and skip the purge. Staged encrypted files are still cleaned up as normal. Accepted because it cleanly separates automated secure runs from interactive debugging needs while keeping master key retention explicit and deliberate.

## Consequences

- `sandbox/main.py` adds `--sops` argument, includes `"SOPS"` in the launch banner, prints SOPS access info in `print_access_info`, and passes `ENABLE_SOPS="1"` when set.
- `shared/startup.sh` provisions `~/.config/sops/age/keys.txt` when `ENABLE_SOPS=1` (even without `--agy`, `--modal`, or `--opencode`).
- When `ENABLE_SOPS=1`, `shared/startup.sh` skips purging `~/.config/sops` and `AGE_PRIVATE_KEY`, exporting `SOPS_AGE_KEY`, `SOPS_AGE_KEY_FILE`, and `AGE_PRIVATE_KEY` to `~/.bashrc` and `/etc/environment`.
- `shared/startup.sh` installs `/usr/local/bin/check-sops` when `ENABLE_SOPS=1`.
- When `--sops` is omitted, `shared/startup.sh` executes the unconditional purge of `~/.config/sops` and unsets `AGE_PRIVATE_KEY`, preserving ADR 0007 behavior for all standard and automated runs.
