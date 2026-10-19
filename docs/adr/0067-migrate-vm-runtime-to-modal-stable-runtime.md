# Migrate VM Runtime to Modal Stable Runtime and Unify Memory Bursting

Previously, VM sandboxes in this repository were provisioned using the internal experimental option `experimental_options={"vm_runtime": True}` with a static memory allocation (`memory_mib = memory_gb * 1024`, default 1024 MiB), while Standard Sandboxes ran on gVisor with dynamic memory bursting `(128, 16384)` MiB (ADR 0016). In Modal SDK v1.6.0+, Modal graduated the virtual machine runtime into a first-class parameter `runtime="vm"`, added native memory bursting support for VM sandboxes, and deprecated `experimental_options['vm_runtime']` with server-side warnings. We decided to migrate all VM sandboxes to `runtime="vm"`, explicitly set `runtime="gvisor"` for Standard Sandboxes, unify VM memory to use identical burstable RAM `(128, 16384)` MiB, and soft-deprecate `--memory` while retaining it to scale `SWAP_GB` for backwards compatibility.

## Considered Options

- **Keep static 1 GB RAM allocation for VM sandboxes with `runtime="vm"`**: Only update `experimental_options` to `runtime="vm"`, maintaining `memory = 1024`. Rejected because VM sandboxes on Modal now support dynamic memory bursting; keeping static 1 GB allocation unnecessarily caps available RAM for Docker builds and compilation, while paying for 1 GB continuously even when idle.
- **Hard-deprecate and reject `--memory` with a CLI error**: Immediately remove `--memory` from `sandbox/cli.py` or raise a validation error. Rejected because existing user scripts and automation workflows may still pass `--memory 2` or `--memory 4`; a hard failure would introduce disruptive breaking changes.
- **Unified burstable memory with soft-deprecated `--memory` scaling `SWAP_GB`**: Unify VM sandbox RAM to standard burstable `(128, 16384)` MiB. If `--memory <GB>` is passed, emit a user-facing deprecation warning but use it to size `SWAP_GB = memory_gb * 2` (defaulting to 2 GB swap when omitted). Explicitly declare `runtime="vm"` and `runtime="gvisor"`. Accepted because it eliminates deprecation warnings, provides burstable memory headroom up to 16 GB, prevents billing waste on idle VMs, and preserves Docker stability and backward compatibility.

## Consequences

- `experimental_options={"vm_runtime": True}` is completely purged from `sandbox/main.py`, `factory/spawner/_factory.py`, and `scripts/test_live_sandbox.py`.
- `sandbox/main.py` explicitly sets `runtime="vm"` when `--vm` is enabled, and `runtime="gvisor"` when standard container mode is used.
- Both Standard and VM Sandboxes allocate burstable memory `(128, 16384)` MiB.
- The `--memory` CLI parameter is soft-deprecated: when specified with `--vm`, it issues a warning and sizes `SWAP_GB = memory_gb * 2`. Without `--memory`, VM sandboxes default to a 2 GB swapfile.
- `factory/spawner/_factory.py` sets `runtime="vm"` when `config.vm` is True and `runtime="gvisor"` otherwise, allocating `FACTORY_STANDARD_MEMORY` (`(128, 16384)` MiB) across both flavors.
- Unit tests in `tests/test_spawner.py` and `tests/test_sandbox/` are updated to assert `runtime` values and verify the absence of `experimental_options`.
