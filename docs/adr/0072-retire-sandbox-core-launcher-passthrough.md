# Retire sandbox.core.launch_sandbox Passthrough Seam

**Status**: Accepted (Amends [ADR 0052](0052-collapse-sandbox-provisioning-seam.md) Section 5)

We permanently retire the backward-compatibility adapter `launch_sandbox()` from `sandbox/core.py`, standardizing all factory callers (`sandbox/main.py`, `sandbox/function.py`, `sandbox/web.py`) directly on `sandbox.launcher.launch_sandbox`, eradicating circular import dependencies between `sandbox.core` and `sandbox.launcher`.

## Context

When [ADR 0052](0052-collapse-sandbox-provisioning-seam.md) consolidated sandbox provisioning into `SandboxLauncher` (`sandbox/launcher.py`), Section 5 preserved a `launch_sandbox()` wrapper in `sandbox/core.py` to provide a backward-compatible delegation seam.

Over time, this preservation introduced subtle architectural degradation:
1. **Lazy Circular Imports**: Internal modules (`sandbox/main.py`, `sandbox/function.py`, `sandbox/web.py`) imported `launch_sandbox` from `sandbox.core`, while `sandbox.core` imported `SandboxLauncher` from `sandbox.launcher` (which in turn imports types from `sandbox.core`). This required lazy function-level imports to evade circular import exceptions.
2. **Shallow Passthrough**: `sandbox/core.py:launch_sandbox` provided zero leverage, acting merely as a parameter forwarding layer that violated the deep module principle.
3. **Seam Ambiguity**: New callers and tests were forced to choose between `sandbox.core.launch_sandbox` and `sandbox.launcher.launch_sandbox`.

## Decisions

1. **Retire `sandbox/core.py:launch_sandbox()`**:
   - Completely remove `launch_sandbox()` from `sandbox/core.py`, satisfying Michael Feathers' "deletion test": deleting the pass-through eliminates complexity rather than scattering it across callers.
   - Decouple `sandbox/core.py` from `sandbox/launcher.py`, permanently eliminating the circular module dependency.

2. **Standardize on `sandbox.launcher.launch_sandbox`**:
   - Bind all execution points (`sandbox/main.py`, `sandbox/function.py`, `sandbox/web.py`) directly to `sandbox.launcher.launch_sandbox` / `SandboxLauncher`.
   - Maintain re-exports of Pydantic data schemas (`LaunchRequest`, `LaunchResponse`, `SnapshotRequest`, `SnapshotResponse`) in `sandbox/core.py` for API typing stability.

## Consequences

- Completely eliminates the circular import between `sandbox.core` and `sandbox.launcher`.
- Shrinks `sandbox/core.py` by an additional 25 lines, keeping it well below the 500-line budget.
- All provisioning callers cross one single, canonical seam at `sandbox/launcher.py`.
