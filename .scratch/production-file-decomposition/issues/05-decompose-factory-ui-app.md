# 05: Decompose factory/ui/app.py

**What to build:**
Decompose `factory/ui/app.py` (1,120 physical lines) by migrating route handlers into focused FastAPI `APIRouter` modules under `factory/ui/routes/`:
- Create `factory/ui/routes/`:
  - `repos.py`: Repository discovery, template instantiation, branch listing, and metadata endpoints (`/api/repos`, `/api/repos/{repo}/*`).
  - `jobs.py`: Factory sandbox job dispatch, status querying, cancellation, and SSE log streaming (`/api/jobs/*`).
  - `studio_preview.py`: Preview sandbox launch, status, branch switching, and trunk synchronization (`/api/studio/repos/{repo}/preview/*`).
  - `studio_chat.py`: Grilling turn interactions, chat history retrieval, prompt intent evaluation, and turn rollback (`/api/studio/repos/{repo}/chat/*`, `/turns/rollback`).
  - `studio_pulls.py`: Pull request discovery, delivery gate evaluation, and merge controls (`/api/studio/repos/{repo}/pulls/*`).
- Refactor `factory/ui/app.py`:
  - Retain the `create_app()` factory function, middleware registration, static file serving, exception handlers, and `app.include_router(...)` mount calls.
  - Target size for `app.py`: $\le 200$ physical lines.
- Invariant: Each router file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_ui.py` to ensure all endpoint contracts pass without test modifications.

**Blocked by:** 04-decompose-sandbox-factory-events

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/routes/` directory and implement sub-routers (`repos.py`, `jobs.py`, `studio_preview.py`, `studio_chat.py`, `studio_pulls.py`).
- [x] Ensure all Pydantic request/response models are cleanly co-located with their respective routers.
- [x] Mount routers in `factory/ui/app.py` and strip inlined route handlers.
- [x] Verify `factory/ui/app.py` is $\le 200$ physical lines and all router files are $\le 500$ lines.
- [x] Verify `pytest tests/test_ui.py` passes without test modifications.

## Comments

- Decomposed `factory/ui/app.py` into package directory `factory/ui/routes/` with 5 focused sub-routers (`repos.py`, `jobs.py`, `studio_preview.py`, `studio_chat.py`, `studio_pulls.py`), package `__init__.py`, and streamlined `app.py`.
- All newly created and modified files strictly adhere to the line budget:
  - `factory/ui/app.py`: 165 lines ($\le 200$ target physical lines)
  - `factory/ui/routes/__init__.py`: 15 lines ($\le 500$ lines)
  - `factory/ui/routes/repos.py`: 98 lines ($\le 500$ lines)
  - `factory/ui/routes/jobs.py`: 130 lines ($\le 500$ lines)
  - `factory/ui/routes/studio_preview.py`: 378 lines ($\le 500$ lines)
  - `factory/ui/routes/studio_chat.py`: 462 lines ($\le 500$ lines)
  - `factory/ui/routes/studio_pulls.py`: 138 lines ($\le 500$ lines)
- All 182 tests in `tests/test_ui.py` and 258 tests across all UI test suites pass with zero modifications.

