# 02: Decompose factory/ui/registry.py

**What to build:**
Decompose `factory/ui/registry.py` (1,353 physical lines) into a cohesive directory package `factory/ui/registry/` adhering to deep module principles:
- Create `factory/ui/registry/`:
  - `_models.py`: Data models, enums (`JobStatus`, `JobStage`), dataclasses (`JobRecord`, `PreviewState`), and buffer abstractions.
  - `_milestones.py`: Stage transition milestone regexes, log parsers, and stage detection helpers.
  - `_preview.py`: Preview sandbox lifecycle, tunnel URL discovery, dev server process monitoring, and preview branch synchronization.
  - `_dispatch.py`: In-memory job registry state, thread-safe job tracking, background worker execution, and process cancellation.
  - `__init__.py`: Re-export all public functions, classes, and constants so existing imports (`from factory.ui.registry import ...`) continue working without modification.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_ui.py` to ensure all existing tests pass with zero modifications.

**Blocked by:** 01-decompose-factory-ui-github

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/registry/` directory and internal sub-modules (`_models.py`, `_milestones.py`, `_preview.py`, `_dispatch.py`).
- [x] Move logic into respective sub-modules ensuring each file is $\le 500$ physical lines.
- [x] Populate `factory/ui/registry/__init__.py` with all public re-exports matching original interface.
- [x] Remove legacy `factory/ui/registry.py`.
- [x] Verify `pytest tests/test_ui.py` passes without test modifications.

## Comments

- Decomposed `factory/ui/registry.py` into package directory `factory/ui/registry/` with 4 internal submodules (`_models.py`, `_milestones.py`, `_preview.py`, `_dispatch.py`) and `__init__.py`.
- All newly created files strictly adhere to the line budget ($\le 500$ physical lines):
  - `__init__.py`: 56 lines
  - `_dispatch.py`: 486 lines
  - `_milestones.py`: 43 lines
  - `_models.py`: 184 lines
  - `_preview.py`: 471 lines
- All 205 tests across `tests/test_ui.py` and `tests/test_preview.py` pass without modifications.
