# Decouple Setup Script Flags and Retire Sandbox SOPS Flag

Previously, `scripts/setup.sh` supported opt-in Modal client credential decryption via `--modal`, but continued to decrypt the Antigravity OAuth token unconditionally by default. As a result, running `scripts/setup.sh --modal` on host workstations unintentionally decrypted Antigravity tokens, there was no independent `--agy` flag, and sandboxes relied on zero-argument execution to decrypt Antigravity tokens via a generic `--sops` launcher flag. We decided to decouple credential provisioning entirely: `scripts/setup.sh` now independently accepts `--modal` and `--agy`, neither flag triggers the other, zero-argument invocations exit cleanly as a no-op, and the redundant `--sops` flag has been removed from sandbox runners with container decryption triggered strictly by `--agy`.

## Considered Options

- **Retain default Antigravity decryption in `scripts/setup.sh`**: Keep zero-argument and `--modal` executions decrypting Antigravity tokens automatically. Rejected because it couples unrelated credential domains, forces unwanted Antigravity credentials onto machines only needing Modal client configuration, and prevents scoped provisioning.
- **Mutually exclusive flags with validation errors on collision**: Reject invocations that provide both `--modal` and `--agy`. Rejected because developers setting up host workstations frequently need both Modal client access and local Antigravity CLI tokens, and forcing sequential script executions adds unnecessary friction.
- **Decoupled orthogonal flags with no-op default and retirement of `--sops`**: Make `--modal` and `--agy` independent boolean flags in `scripts/setup.sh` that can be specified individually or together without interference, treat zero arguments as an exit 0 no-op, remove `--sops` from `standard_sandbox/main.py` and `vm_sandbox/main.py`, and have container startup scripts invoke `scripts/setup.sh --agy` when `ENABLE_ANTIGRAVITY=1`. Accepted because it provides clean orthogonal credential scopes, eliminates dead CLI arguments, and enforces least privilege.

## Consequences

- `scripts/setup.sh` accepts `--modal` (decrypts `secrets/modal.toml` to `~/.modal.toml`), `--agy` (decrypts `secrets/antigravity-oauth-token.json` to `~/.gemini/antigravity-cli/antigravity-oauth-token`), or both simultaneously.
- Invoking `bash scripts/setup.sh` with zero arguments performs no decryption and exits cleanly with code 0.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` remove the `--sops` argument and the `SOPS` feature banner.
- `standard_sandbox/startup.sh` and `vm_sandbox/startup.sh` trigger SOPS key configuration and execute `bash scripts/setup.sh --agy` strictly when `ENABLE_ANTIGRAVITY=1`.
- Host workstation documentation in `readme.md` instructs running `bash scripts/setup.sh --modal --agy` for complete local development setups, or individual flags for scoped setups.
