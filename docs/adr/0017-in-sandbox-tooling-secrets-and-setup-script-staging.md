# In-Sandbox Tooling Secrets and Setup Script Staging

Previously, `shared/startup.sh` attempted to run `scripts/setup.sh` from the cloned target repository (`$TARGET_DIR`). Because external guest repositories do not track the factory's setup script and the image builder (`shared/image.py`) never staged tooling secrets (`secrets/opencode.env`, `secrets/antigravity-oauth-token.json`, `secrets/modal.toml`), sandboxes launched with `--opencode`, `--agy`, or `--modal` silently skipped credential decryption, resulting in missing API key errors. We decided to decouple factory tooling setup from the cloned repository: `scripts/setup.sh` is staged into the image at `/root/scripts/setup.sh` and dynamically resolves secrets relative to its own script location, `build_sandbox_image` stages only the specific encrypted tooling secrets matching requested flags into `/root/secrets/`, `shared/startup.sh` invokes `/root/scripts/setup.sh` via absolute path, and all staged encrypted tooling secrets are purged immediately following decryption alongside `~/.config/sops`.

## Considered Options

- **Inline tooling decryption directly in `shared/startup.sh`**: Perform `sops decrypt` for each tooling secret directly inside `shared/startup.sh`, retiring `scripts/setup.sh` from sandbox bootstrap. Rejected because `scripts/setup.sh` already encapsulates environment propagation (`/etc/environment`, `~/.bashrc`) and maintaining two divergent credential provisioning implementations between host workstations and sandboxes leads to behavioral drift.
- **Unconditionally stage all tooling secrets in `base_image`**: Bake `opencode.env`, `antigravity-oauth-token.json`, and `modal.toml` into `/root/secrets/` on every image build, decrypting only active flags. Rejected because it violates least privilege by leaving unnecessary encrypted credential files at rest in containers that only need a subset of tooling.
- **Dedicated staged setup script with granular secret staging**: Stage `scripts/setup.sh` at `/root/scripts/setup.sh`, stage only the requested tooling secrets into `/root/secrets/` in `build_sandbox_image`, execute `/root/scripts/setup.sh` via absolute path from `shared/startup.sh`, and purge staged encrypted secrets immediately after decryption. Accepted because it maintains execution parity between host workstations and sandboxes, enforces strict least privilege across image layers, guarantees zero residual encrypted files after boot, and decouples infrastructure setup from guest repositories.

## Consequences

- `shared/image.py` stages `scripts/setup.sh` into the container at `/root/scripts/setup.sh`.
- `build_sandbox_image` in `shared/image.py` copies `secrets/opencode.env` when `opencode=True`, `secrets/antigravity-oauth-token.json` when `agy=True`, and `secrets/modal.toml` when `modal_tooling=True` to `/root/secrets/`.
- `scripts/setup.sh` computes `SECRETS_DIR="${SECRETS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/secrets}"`, running identically on host workstations and in sandboxes.
- `shared/startup.sh` executes `bash /root/scripts/setup.sh "${setup_args[@]}"` independently of `cd "$TARGET_DIR"`.
- Ephemeral cleanup in `shared/startup.sh` deletes `/root/secrets/opencode.env`, `/root/secrets/antigravity-oauth-token.json`, and `/root/secrets/modal.toml` right after SOPS decryption completes.
