# 02: Root Route Cutover & Legacy Monolith Decommissioning

**What to build:** Transition the compiled Vite React SPA to the primary root route `/` in FastAPI, permanently decommission the 3,172-line legacy Jinja template, redirect legacy `/v2` requests, and update server startup messaging and test suites to assert the compiled SPA.

**Blocked by:** 01: Vite React SPA Implementation & Dual-Route Serving (`/v2`)

**Status:** resolved

- [x] FastAPI in `factory/ui/app.py` updates the root path `/` to serve the compiled SPA from `factory/ui/static/dist/index.html`.
- [x] Requests to `/v2` issue an HTTP 307/308 redirect or transparent rewrite to `/`.
- [x] The legacy template `factory/ui/templates/index.html` is permanently deleted from the codebase.
- [x] Server startup banners in `factory/ui/server.py` reflect the compiled SPA deployment.
- [x] Integration tests in `tests/test_ui.py` are updated to assert that `/` serves the compiled Vite React SPA and that static assets load correctly.
- [x] All unit and integration test suites (`python3 -m unittest discover tests`) pass with zero regressions.
