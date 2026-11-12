# Ephemeral SOPS Credentials and In-Sandbox Key Purging

Previously, during sandbox bootstrap with `--sops` or `--agy`, `startup.sh` extracted `AGE_PRIVATE_KEY` from environment variables, wrote the private key to `~/.config/sops/age/keys.txt`, and executed `scripts/setup.sh`. While `startup.sh` unset `AGE_PRIVATE_KEY` in bash login profiles, the plaintext Age key file remained permanently on disk at `~/.config/sops/age/keys.txt`, leaving the root decryption key accessible to interactive developer shells, untrusted code, and autonomous agents running inside the container. We decided to make SOPS decryption strictly ephemeral: immediately after `scripts/setup.sh` runs (whether it succeeds or fails), `startup.sh` unconditionally purges `~/.config/sops` via `rm -rf ~/.config/sops` and clears `AGE_PRIVATE_KEY` from memory.

## Considered Options

- **Retain `~/.config/sops/age/keys.txt` in the container**: Keep the private key file on the filesystem after bootstrap. Rejected because it grants interactive processes and AI agents persistent access to repository master encryption keys, violating credential least privilege.
- **Purge `~/.config/sops` inside `scripts/setup.sh`**: Add deletion commands to the end of `scripts/setup.sh`. Rejected because `scripts/setup.sh` is also executed by developers locally on their workstations (e.g. `scripts/setup.sh --modal`), where deleting `~/.config/sops` would destroy the developer's permanent Age keys.
- **Ephemeral in-sandbox lifecycle with guaranteed cleanup in `startup.sh`**: Provision `~/.config/sops/age/keys.txt` temporarily during container bootstrap, execute `scripts/setup.sh`, and unconditionally execute `rm -rf ~/.config/sops` and `unset AGE_PRIVATE_KEY` before continuing or exiting on error. Accepted because it confines the master key exposure strictly to the bootstrap execution phase and ensures zero lingering secrets on the container filesystem.

## Consequences

- `standard_sandbox/startup.sh` and `vm_sandbox/startup.sh` unconditionally purge `~/.config/sops` right after executing `scripts/setup.sh`.
- If `scripts/setup.sh` fails during decryption, `~/.config/sops` is still wiped before the script exits with an error.
- Post-bootstrap interactive sessions or background agents inside running sandboxes cannot re-run `scripts/setup.sh` or decrypt additional SOPS secrets without manually re-providing the Age key.
- Host workstation setups via `scripts/setup.sh` remain unaffected and never touch the developer's local `~/.config/sops`.
