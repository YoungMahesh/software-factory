# Dedicated Modal Sandbox SSH Key Pair

Previously, sandbox runners expected developers to point `--ssh-key` to personal SSH keys (defaulting to non-existent `id_ed25519` files). We decided to standardize on a dedicated repository key pair: the public key is checked into version control at `shared/ssh-key.pub` and injected into sandbox containers, while the private key is encrypted with SOPS at `secrets/ssh-private-key` and decrypted to `~/.ssh/modal-sandbox` (mode 0600) via `scripts/setup.sh`. The `--ssh-key` CLI argument was removed, and sandbox scripts fail fast if `~/.ssh/modal-sandbox` has not been decrypted.

## Considered Options

- **Personal SSH keys via CLI argument (`--ssh-key ~/.ssh/id_ed25519`)**: Require every developer to pass or configure their individual SSH key pair when launching sandboxes. Rejected because it created onboarding friction, broke across different machines, and lacked a shared standard for team sandbox access.
- **Dynamic per-launch key pair generation**: Generate a fresh ephemeral SSH key pair in memory on every launch. Rejected because developers frequently reconnect across sessions and configure persistent `Host` blocks in `~/.ssh/config`.
- **Dedicated shared key pair with SOPS encryption**: Track the public key openly in `shared/ssh-key.pub` for immediate injection into `SSH_AUTHORIZED_KEY`, encrypt the private key in `secrets/ssh-private-key`, and provision it to `~/.ssh/modal-sandbox` with 0600 permissions via `scripts/setup.sh`. Accepted because it provides a frictionless, zero-config experience once repository secrets are decrypted.

## Consequences

- Launching sandboxes no longer requires specifying `--ssh-key`.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` automatically load `shared/ssh-key.pub` and reference `~/.ssh/modal-sandbox` in generated connection snippets.
- If `~/.ssh/modal-sandbox` is missing, the runners abort early with an actionable error instructing the user to run `bash scripts/setup.sh`.
