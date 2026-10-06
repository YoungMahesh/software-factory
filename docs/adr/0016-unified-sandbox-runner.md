# Unified Sandbox Runner

Previously, the repository maintained two separate sandbox launcher scripts: `standard_sandbox/main.py` for lightweight container sandboxes and `vm_sandbox/main.py` for virtualized VM sandboxes. Although the image definition (`shared/image.py`) and startup script (`shared/startup.sh`) were already unified in ADR 0011, the two runners were ~90% duplicate code and suffered from behavioral drift. We decided to unify both sandbox execution models into a single launcher at `sandbox/main.py` differentiated by an explicit `--vm` boolean flag, remove the redundant `standard_sandbox/` and `vm_sandbox/` directories, and strictly constrain `--memory` to VM mode.

## Considered Options

- **Retain separate launcher scripts per directory (`standard_sandbox/` and `vm_sandbox/`)**: Keep `standard_sandbox/main.py` and `vm_sandbox/main.py` isolated. Rejected because every feature flag addition, bug fix, or port configuration required identical duplicate edits across both files, creating code drift (e.g. OpenCode client attach syntax and log streaming discrepancies).
- **Merge into repository root `main.py`**: Consolidate directly at the repository root. Rejected because keeping sandbox runner logic isolated within a dedicated `sandbox/` directory maintains clean separation between repository-level metadata and sandbox runtime tooling.
- **Unified runner in `sandbox/main.py` with `--vm` differentiator and strict `--memory` guard**: Consolidate all launcher logic into `sandbox/main.py`. Without `--vm`, it provisions a Standard Sandbox on the container runtime with burstable RAM `(128, 16384)` MiB, no swap, and unstarted Docker daemon. With `--vm`, it provisions a VM Sandbox with `experimental_options={"vm_runtime": True}`, sets `ENABLE_DOCKER=1`, sets swapfile allocation, and accepts `--memory` (default: 1 GB RAM + 2 GB swap). Accepted because it eliminates code duplication, guarantees feature parity across both flavors, prevents invalid memory configurations, and unifies sandbox documentation.

## Consequences

- `standard_sandbox/` and `vm_sandbox/` directories are completely removed.
- `sandbox/main.py` is the canonical entry point for all sandbox launches.
- Running without `--vm` launches a Standard Sandbox by default.
- Passing `--vm` activates virtual machine virtualization, custom kernel privileges, Docker daemon startup, and swap allocation.
- Passing `--memory` without `--vm` produces an explicit CLI validation error; with `--vm`, it allocates `N` GB RAM and `2N` GB swap.
- Standardizes OpenCode client connection command on `opencode --server <url>`.
- Documentation is consolidated into `sandbox/readme.md` and referenced from the repository root `readme.md`.
