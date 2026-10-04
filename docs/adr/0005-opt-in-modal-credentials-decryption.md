# Opt-In Modal Credentials Decryption and Sandbox Isolation

Previously, `scripts/setup.sh` unconditionally decrypted `secrets/modal.toml` into `~/.modal.toml`. Because `scripts/setup.sh` is automatically executed during container bootstrap when SOPS is enabled, this provisioned host Modal cloud credentials into sandbox runtime environments. We decided to make Modal client credential decryption strictly opt-in via a `--modal` argument in `scripts/setup.sh`, while continuing to decrypt sandbox SSH keys and Antigravity tokens by default. In-sandbox startup scripts execute `scripts/setup.sh` without flags, enforcing credential isolation and preventing container workloads or autonomous agents from accessing host Modal account infrastructure.

## Considered Options

- **Unconditional secret decryption in `scripts/setup.sh`**: Decrypt all repository secrets including `secrets/modal.toml` whenever `scripts/setup.sh` is run. Rejected because executing `scripts/setup.sh` inside sandboxes exposes the developer's root Modal account API tokens to untrusted container processes and autonomous agents, creating an unnecessary credential blast radius.
- **Separate host and sandbox setup scripts**: Maintain independent provisioning scripts (such as `scripts/setup-host.sh` and `scripts/setup-sandbox.sh`). Rejected because it duplicates decryption and permissions management logic, increases maintenance overhead, and fragments repository onboarding.
- **Opt-in `--modal` flag with safe default decryption**: Introduce strict argument parsing in `scripts/setup.sh` where `secrets/modal.toml` is decrypted only when `--modal` is explicitly passed, while sandbox SSH keys and Antigravity tokens decrypt by default. Accepted because it unifies secret bootstrapping into a single script, enforces the principle of least privilege, and guarantees container credential containment.

## Consequences

- `scripts/setup.sh` accepts `--modal` to decrypt `secrets/modal.toml` to `~/.modal.toml` with 0600 permissions.
- Invoking `bash scripts/setup.sh` without arguments provisions `~/.ssh/modal-sandbox` and `~/.gemini/antigravity-cli/antigravity-oauth-token`, skipping `secrets/modal.toml`.
- Passing unrecognised options to `scripts/setup.sh` fails fast with an error message and exit code 1.
- `standard_sandbox/startup.sh` and `vm_sandbox/startup.sh` execute `bash scripts/setup.sh` without arguments, ensuring `~/.modal.toml` is never provisioned into sandboxes.
- Developer workstation onboarding documentation in `readme.md` instructs running `bash scripts/setup.sh --modal`.
