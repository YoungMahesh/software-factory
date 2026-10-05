# Unified Base Image for Standard and VM Sandboxes

Previously, Standard Sandboxes and VM Sandboxes maintained separate base images: Standard Sandboxes built on Debian (`node:24.21-bookworm-slim`) with pre-baked Node.js and no Docker tooling, while VM Sandboxes built on Ubuntu 24.04, installed `docker.io`, and installed Node.js 24 dynamically at runtime via `fnm install 24` in `startup.sh`. We decided to unify the foundational base image across both sandbox types onto Ubuntu 24.04 with pre-baked Node.js 24 (via NodeSource), pnpm, Docker CLI tools, and a shared `shared/startup.sh`. This ensures 100% Modal image layer caching parity across both runtimes, eliminates runtime Node installation latency in VM Sandboxes, and consolidates sandbox bootstrap scripts.

## Considered Options

- **Retain separate base images per runner**: Keep Debian for Standard Sandboxes and Ubuntu for VM Sandboxes. Rejected because it prevented layer cache reuse on Modal, required maintaining two divergent base image layers and startup scripts, and imposed a 5–15 second startup penalty on every VM Sandbox launch while `fnm` downloaded Node.js.
- **Unified base image without Docker CLI tools**: Omit Docker packages from the base image and install them in an incremental layer only when launching VM Sandboxes. Rejected because pre-installing Docker CLI tools into the base image allows both runners to share the exact same base image cache layer, while Docker CLI binaries exist inertly in Standard Sandboxes without starting `dockerd`.
- **Unified Ubuntu 24.04 base image with pre-baked Node.js 24 and shared startup script**: Build a single `Shared Base Image` in `shared/image.py` on Ubuntu 24.04 containing SSH, SOPS, age, Git, ripgrep, Docker CLI tools, Node.js 24 (NodeSource), and pnpm, bundled with `shared/startup.sh`. Accepted because it maximizes Modal layer caching, guarantees instant boot times for both sandbox types, and unifies environment configuration.

## Consequences

- Both `standard_sandbox/main.py` and `vm_sandbox/main.py` import `base_image` and dynamic image building logic from `shared/image.py`.
- `standard_sandbox/startup.sh` and `vm_sandbox/startup.sh` are replaced by a single `shared/startup.sh` baked into `/root/startup.sh`.
- In `shared/startup.sh`, `dockerd` startup is guarded by `ENABLE_DOCKER=1`, set only by the VM runner.
- Swapfile creation remains guarded by `SWAP_GB`, configured only for VM Sandboxes.
- VM Sandboxes launch instantly without needing runtime `fnm install` overhead.
- Standard Sandboxes carry a slightly larger image footprint (~300 MB) containing unstarted Docker CLI binaries, but benefit from instant startup and layer reuse.
- Both runners can optionally support `--react-native` tooling through the shared image builder.
