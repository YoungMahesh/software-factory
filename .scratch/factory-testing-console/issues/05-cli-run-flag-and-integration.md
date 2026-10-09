# Issue 05: CLI Run Flag, Server Entrypoint, and Verification

Status: resolved

## Objective
Implement `factory/ui/server.py` and `factory/ui/__main__.py` to launch the Uvicorn web server on configurable host/port. Update `factory/run.py` to add `--ui` / `--console` flag that launches the console. Add comprehensive unit tests in `tests/test_ui.py`.

## Acceptance Criteria
- `python -m factory.ui` and `python factory/ui/server.py` start the Uvicorn server on `127.0.0.1:8080`.
- `python factory/run.py --ui` launches the server and opens the URL.
- Comprehensive unit tests verify GitHub discovery, JobRegistry lifecycle, API endpoints, and runner integration.
