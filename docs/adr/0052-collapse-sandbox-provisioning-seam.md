# Collapse Sandbox Provisioning Seam

**Status**: Accepted (Amends [ADR 0040](0040-hosted-sandbox-control-plane-function.md) and [ADR 0041](0041-automatic-ssh-config-registration-for-sandboxes.md))

We consolidate sandbox configuration, image building, secret staging, container creation, tunnel negotiation, lifecycle tracking, and SSH configuration into a dedicated deep module `SandboxLauncher` (`sandbox/launcher.py`), returning an encapsulated `RunningSandbox` domain model and eliminating runtime global monkey-patching hacks (`_resolve_fn`).

## Context

Sandbox provisioning in the factory was previously driven by a procedural pipeline in `sandbox/core.py:launch_sandbox()`. Over time, this function accumulated significant complexity:
1. **Shallow Seam & Global Module Inspection**: `launch_sandbox()` used `_resolve_fn` to inspect `sys.modules["sandbox.main"]` at runtime for monkey-patched overrides (`build_sandbox_image` and `load_ssh_pub_key`). This forced tests to mutate caller module globals rather than testing clean interfaces.
2. **Side-Effect Leakage into Callers**: Post-launch setup (tunnels, SSH config registration via `append_ssh_config()`, connection printing, and lifecycle tracking) was split between `sandbox/core.py` and `sandbox/main.py`. Callers like `sandbox/function.py` and `sandbox/web.py` had to coordinate these calls while avoiding workstation-specific side effects.
3. **Line Budget Pressure**: `sandbox/core.py` grew to 447 physical lines, near the 500-line repository limit enforced by ADR 0027 / AGENTS.md.

## Decisions

1. **Dedicated Deep Module (`sandbox/launcher.py`)**:
   - Introduce `SandboxLauncher` in `sandbox/launcher.py` as the canonical execution seam for creating and provisioning Modal sandboxes.
   - Encapsulate validation, image resolution, environment compilation, container instantiation, tunnel negotiation, T3 pairing, and lifecycle registration behind a unified `launch()` interface.

2. **Removal of `_resolve_fn` and Explicit Dependency Injection**:
   - Completely eliminate `_resolve_fn` and runtime inspection of `sys.modules["sandbox.main"]`.
   - Accept optional dependencies (`build_image_fn`, `load_pubkey_fn`, `log_cb`, `client`) directly via the `SandboxLauncher` constructor or `launch()` parameters. Tests and specialized callers supply dependencies explicitly across the interface.

3. **Encapsulation of SSH Config Registration**:
   - Absorb `append_ssh_config()` into `SandboxLauncher` controlled via `register_ssh_config: bool`.
   - Enabled by default for local CLI launches in `sandbox/main.py`, and explicitly disabled (`register_ssh_config=False`) for Hosted Control Plane execution in `sandbox/function.py` and `sandbox/web.py`.

4. **Rich `RunningSandbox` Domain Result**:
   - Define `RunningSandbox` encapsulating the active `modal.Sandbox`, resolved tunnels, and connection metadata.
   - Provide standard lifecycle passthroughs (`terminate()`, `poll()`, `exec()`) and a `.to_response() -> LaunchResponse` projection for seamless FastAPI and Pydantic serialization.

5. **Backward Compatibility via `sandbox/core.py`**:
   - Preserve `launch_sandbox()` in `sandbox/core.py` as a lightweight compatibility adapter delegating directly to `SandboxLauncher.launch()`.
   - Re-export `LaunchRequest`, `LaunchResponse`, and `RunningSandbox` from `sandbox/core.py` to ensure external consumers and existing tests continue to function.

## Consequences

- The sandbox creation pipeline is consolidated into a single deep module with high leverage behind its seam.
- Fragile `sys.modules` monkey-patching traps are permanently eradicated.
- Callers no longer orchestrate side effects or negotiate tunnel states manually.
- `sandbox/core.py` shrinks by over 50%, and all modules stay comfortably under the 500-line budget ratchet.
