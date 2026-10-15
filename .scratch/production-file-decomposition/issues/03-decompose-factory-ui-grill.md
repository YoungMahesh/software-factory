# 03: Decompose factory/ui/grill.py

**What to build:**
Decompose `factory/ui/grill.py` (1,284 physical lines) into a cohesive directory package `factory/ui/grill/` adhering to deep module principles:
- Create `factory/ui/grill/`:
  - `_models.py`: Data structures (`GrillQuestion`, `DraftADR`, `GrillRoundResult`), dataclasses, and serialization helpers.
  - `_inference.py`: OpenCode Go client, OpenAI-compatible HTTP client, LLM prompt generation, streaming, and inference error handling.
  - `_archetypes.py`: Prompt archetype classification heuristics, intent detection, and codebase grounding context builders.
  - `_adr_drafting.py`: ADR synthesis, sequential number resolution, markdown formatting, and validation.
  - `_turn_runner.py`: Conversational interview runner, frontier extraction, round management, and plan card synthesis.
  - `__init__.py`: Re-export all public functions, classes, and constants so existing imports (`from factory.ui.grill import ...`) continue working without modification.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_grill.py tests/test_ui.py` to ensure all existing tests pass with zero modifications.

**Blocked by:** 02-decompose-factory-ui-registry

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/grill/` directory and internal sub-modules (`_models.py`, `_inference.py`, `_archetypes.py`, `_adr_drafting.py`, `_turn_runner.py`).
- [x] Move logic into respective sub-modules ensuring each file is $\le 500$ physical lines.
- [x] Populate `factory/ui/grill/__init__.py` with all public re-exports matching original interface.
- [x] Remove legacy `factory/ui/grill.py`.
- [x] Verify `pytest tests/test_grill.py tests/test_ui.py` passes without test modifications.

## Comments

- Decomposed `factory/ui/grill.py` into package directory `factory/ui/grill/` with 5 internal submodules (`_models.py`, `_inference.py`, `_archetypes.py`, `_adr_drafting.py`, `_turn_runner.py`) and `__init__.py`.
- All newly created files strictly adhere to the line budget ($\le 500$ physical lines):
  - `__init__.py`: 71 lines
  - `_adr_drafting.py`: 117 lines
  - `_archetypes.py`: 337 lines
  - `_inference.py`: 265 lines
  - `_models.py`: 94 lines
  - `_turn_runner.py`: 469 lines
- All 219 tests across `tests/test_grill.py` and `tests/test_ui.py` pass without modifications.
