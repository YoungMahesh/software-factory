# SOPS-Decrypted Cloudflare Tunnel Token and Default share0 Mounting

Previously, `shared/startup.sh` configured Cloudflare Tunnel using a cleartext fallback tunnel token and accepted runtime overrides via the `CLOUDFLARE_TUNNEL_TOKEN` environment variable, while Modal secret `share0` was only mounted when explicit agent flags (`--agy`, `--modal`, `--opencode`) were passed (ADR 0014, ADR 0015). We decided to encrypt the tunnel credential at rest in `secrets/cloudflare.env`, bake the encrypted file into the Shared Base Image at `/root/secrets/cloudflare.env`, mount `share0` by default across all sandboxes unless `--no-cloudflare` is given, decrypt `CF_TOKEN` directly at container boot in Step 0 via SOPS without intermediate unencrypted files, completely eliminate cleartext fallback tokens and environment variable overrides, and unconditionally scrub `AGE_PRIVATE_KEY` and temporary SOPS state after sandbox bootstrap.

## Considered Options

- **Mount `secrets/cloudflare.env` as a Modal Secret**: Extract the token and pass it as an environment variable or individual Modal secret. Rejected because maintaining multiple disparate secret objects adds operational friction, while baking the SOPS-encrypted file into the base image provides zero-leakage distribution backed by the unified `share0` master key.
- **Retain cleartext fallback token in `shared/startup.sh`**: Keep the hardcoded token as a secondary fallback if decryption fails. Rejected because tracking live cleartext tokens in version control contradicts the repository's security architecture.
- **Runtime decryption via `scripts/setup.sh --cloudflare`**: Delegate Cloudflare decryption to `scripts/setup.sh` in the cloned project repository. Rejected because Cloudflare Tunnel is a container-level infrastructure daemon started before repo cloning, whereas `scripts/setup.sh` is workspace-level tooling that may not exist in cloned external repositories.
- **In-memory SOPS decryption with default `share0` mounting**: Bake `secrets/cloudflare.env` into `/root/secrets/cloudflare.env` via `shared/image.py`, mount `share0` by default in `sandbox/main.py` whenever Cloudflare is active (opt out with `--no-cloudflare`), decrypt `CF_TOKEN` directly via `SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt --extract '["CF_TOKEN"]'`, fail fast if decryption or keys are missing, and unconditionally scrub `AGE_PRIVATE_KEY` across all sandboxes before interactive shells start. Accepted because it delivers zero-leakage secret distribution, guarantees fail-fast security, and ensures master keys never persist into active developer shells.

## Consequences

- `shared/image.py` bakes `secrets/cloudflare.env` into `/root/secrets/cloudflare.env` in the Shared Base Image.
- `sandbox/main.py` mounts `share0` by default unless `--no-cloudflare` is specified.
- `shared/startup.sh` extracts `CF_TOKEN` directly in Step 0 using `sops decrypt --extract '["CF_TOKEN"]'` and `SOPS_AGE_KEY="$AGE_PRIVATE_KEY"`. Hardcoded fallback tokens and the `CLOUDFLARE_TUNNEL_TOKEN` environment variable are completely removed; missing keys or failed decryptions immediately fail container bootstrap with exit code 1.
- `shared/startup.sh` unconditionally unsets `AGE_PRIVATE_KEY` from memory and login profiles and removes `~/.config/sops` after Step 2, ensuring master keys never persist into user shells on both bare and feature-enabled sandboxes.
- Sandboxes launched without `--no-cloudflare` require Modal secret `share0` to exist in the Modal workspace.
