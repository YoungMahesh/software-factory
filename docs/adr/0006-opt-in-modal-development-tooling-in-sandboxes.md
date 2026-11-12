# Opt-In Modal Development Tooling and Credential Provisioning in Sandboxes

Previously, sandboxes supported `--python` for runtime virtual environment isolation, while setup scripts and ADR-0005 intentionally prohibited decrypting Modal client credentials (`~/.modal.toml`) inside sandboxes to prevent container processes from accessing root Modal cloud account infrastructure. However, workflows developing Modal applications, sandboxes, or distributed functions from inside a cloud sandbox require both a Python environment and authenticated Modal CLI/SDK access. We decided to retire `--python` and replace it with `--modal` across both standard and VM sandboxes: passing `--modal` couples Python 3 virtual environment provisioning (with the `modal` package pre-installed) with SOPS decryption of `secrets/modal.toml` into `~/.modal.toml`. When `--modal` is omitted, neither Python tooling nor Modal client credentials are provisioned inside the sandbox.

## Considered Options

- **Retain separate `--python` and introduce independent `--modal-creds`**: Keep `--python` strictly for the virtual environment and add a second flag for credential decryption. Rejected because running Modal tooling inside the sandbox inherently requires Python, and splitting them introduces redundant flags and partial configuration states where credentials exist without the SDK or vice versa.
- **Maintain strict credential isolation and prohibit sandbox credentials**: Continue refusing to decrypt `secrets/modal.toml` in sandboxes under all circumstances, forcing developers to run Modal commands exclusively from host workstations. Rejected because it blocks self-contained cloud development workflows, meta-sandboxing, and autonomous agent tasks that manage Modal resources.
- **Unified `--modal` flag provisioning both Python environment and credentials**: Replace `--python` with `--modal` in both `standard_sandbox/main.py` and `vm_sandbox/main.py`. When enabled, dynamically install Python 3 system dependencies, provision an isolated `.venv` with `modal` pre-installed, and decrypt `secrets/modal.toml` to `~/.modal.toml` (mode 0600) via `scripts/setup.sh --modal`. When omitted, neither credentials nor Python tooling are injected. Accepted because it aligns sandbox capabilities with host workflows, preserves least privilege by default, and maintains flavor parity.

## Consequences

- `--python` is removed from `standard_sandbox/main.py`.
- `--modal` is supported in both `standard_sandbox/main.py` and `vm_sandbox/main.py`.
- In `startup.sh` (both standard and VM sandboxes), SOPS bootstrapping triggers if `ENABLE_ANTIGRAVITY=1` or `ENABLE_MODAL=1`, requiring `AGE_PRIVATE_KEY` and passing the active flags (`--modal`, `--agy`, or both) to `scripts/setup.sh`.
- Sandboxes launched with `--modal` have `$TARGET_DIR/.venv` provisioned with the `modal` Python SDK pre-installed and project dependencies installed from `requirements.txt`.
- Sandboxes launched without `--modal` do not provision Python tooling, `.venv`, or `~/.modal.toml`.
- Inspection utility `/usr/local/bin/check-modal` verifies Python, `.venv`, and Modal authentication status, with `/usr/local/bin/check-python` maintained as a symlink.
- Documentation in `CONTEXT.md`, `readme.md`, `standard_sandbox/readme.md`, and `vm_sandbox/readme.md` is updated to reflect Modal Development Tooling.
