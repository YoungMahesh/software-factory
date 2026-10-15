# 14: Decompose factory/spawner.py

**What to build:**
Decompose `factory/spawner.py` (522 physical lines) into a cohesive directory package `factory/spawner/` adhering to deep module principles:
- Create `factory/spawner/`:
  - `_config.py`: Shared constants (`FACTORY_TIMEOUT_SECS`, `FACTORY_IDLE_TIMEOUT_SECS`, resource tuples) and dataclasses (`PreviewSpawnConfig`, `FactorySpawnConfig`).
  - `_factory.py`: Assembly line factory sandbox provisioning (`create_factory_sandbox`).
  - `_preview.py`: Dedicated preview sandbox provisioning (`create_preview_sandbox`).
  - `__init__.py`: Re-export all public functions, classes, and constants so existing imports (`from factory.spawner import ...`) work with zero caller changes.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_sandbox.py tests/test_ui.py` to ensure spawner specifications pass without modification.

**Blocked by:** 13-decompose-github-tracker

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/spawner/` directory and internal sub-modules (`_config.py`, `_factory.py`, `_preview.py`).
- [x] Move logic into respective sub-modules ensuring each is $\le 500$ physical lines.
- [x] Populate `factory/spawner/__init__.py` with all public re-exports matching the original interface.
- [x] Remove legacy `factory/spawner.py`.
- [x] Verify `pytest tests/test_sandbox.py tests/test_ui.py` passes without test modifications.

