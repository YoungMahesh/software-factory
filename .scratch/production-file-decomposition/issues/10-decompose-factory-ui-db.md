# 10: Decompose factory/ui/db.py

**What to build:**
Decompose `factory/ui/db.py` (687 physical lines) into a cohesive directory package `factory/ui/db/` adhering to deep module principles:
- Create `factory/ui/db/`:
  - `_schema.py`: Table DDL definitions, schema migration logic, and default path constants (`DEFAULT_DB_DIR`, `DEFAULT_DB_PATH`).
  - `_models.py`: Row-to-dict converters (`_row_to_job_dict`, `_row_to_preview_dict`), dataclasses, and serialization helpers.
  - `_chat.py`: Chat history persistence methods (save message, mark reverted, fetch history, clear messages).
  - `_jobs.py`: Job record and telemetry log persistence methods (save job, update job stage, append telemetry logs, fetch jobs).
  - `_preview.py`: Preview state persistence methods (save preview state, update status).
  - `__init__.py`: Define `StudioDatabase` class composing the storage delegates and re-export public interfaces.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_ui.py` to ensure all database queries and transactions pass without test modifications.

**Blocked by:** 09-decompose-sandbox-factory-harness

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/db/` directory and internal sub-modules (`_schema.py`, `_models.py`, `_chat.py`, `_jobs.py`, `_preview.py`).
- [x] Move logic into respective sub-modules ensuring each is $\le 500$ physical lines.
- [x] Populate `factory/ui/db/__init__.py` with `StudioDatabase` composing the modules.
- [x] Remove legacy `factory/ui/db.py`.
- [x] Verify `pytest tests/test_ui.py` passes without test modifications.
