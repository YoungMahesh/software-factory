# 01: Canonicalize Backend API Routes and Frontend Client

**What to build:** Reorganize backend route modules to clean domain names, migrate all REST endpoints from `/api/studio/*` to flat `/api/*`, remove duplicate route decorators, and simplify the frontend API client and query hooks to call canonical flat routes.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Route files under `factory/ui/routes/` are renamed to clean domain names: `preview.py`, `chat.py`, `pulls.py`, `rollback.py`, `repos.py`, and `jobs.py`.
- [x] All endpoint decorators in `factory/ui/routes/` are canonicalized under flat `/api/*` (`/api/repos`, `/api/jobs`, `/api/preview`, `/api/prompt`, `/api/approve`, `/api/dispatch`, `/api/repos/{repo}/pulls`, `/api/repos/{repo}/rollback`), completely eliminating `/api/studio/*` prefixes and duplicate `@router` decorators.
- [x] `factory/ui/app.py` registers the renamed route modules cleanly without legacy route duplication.
- [x] Frontend API client in `factory/ui/frontend/src/api.ts` is simplified to target flat `/api/*` endpoints, removing duplicate fetch functions like `fetchStudioRepos` in favor of `fetchRepos`.
- [x] Frontend React Query hooks in `useStudioQueries.ts` and query keys are updated to use canonical `/api/*` routes.
- [x] Backend FastAPI integration test suites in `tests/test_ui/` (`test_fastapi_app.py`, `test_dispatch_endpoint.py`, `test_approve_endpoint.py`, `test_fastapi_preview.py`, `test_pull_requests_endpoints.py`, `test_turn_rollback.py`) pass cleanly against flat `/api/*` routes and assert that `/api/studio/*` endpoints return 404 Not Found.
