# Frontend Testing Boundary and Test Suite Simplification

**Status**: Accepted (Amends ADR 0036)

Following the migration of Factory Studio from a monolithic Jinja2 HTML template to a Compiled Vite React SPA (ADR 0036), tests verifying frontend components and telemetry UI remained split across two distinct environments with misaligned responsibilities. Python tests under `tests/test_ui_events.py` and `tests/test_ui.py` inspected TypeScript (`.tsx`) source files as raw text and executed `node -e` subprocesses to verify string parsing, while legacy template assertions tested Jinja2 remnants.

To establish maintainable, decoupled, and fast test suites across both environments, we decided to enforce a strict **architectural testing boundary** between the frontend React SPA and the backend FastAPI service, and modernize test utilities in both layers.

## Considered Options

- **Dual-Layer Assertions (Status Quo)**: Retaining Python tests that open frontend `.tsx` files to assert JSX string tokens alongside Vitest component tests. Rejected because tests broke on harmless variable renames or refactorings without catching real regressions, creating high maintenance overhead and false test failures for autonomous agents.
- **Full End-to-End Browser Testing in Python (Playwright / Selenium)**: Running browser-driven E2E tests against the built Vite bundle from Python. Rejected because spinning up headless browsers for every component and drawer permutation incurs high CI runtime and resource usage, whereas Vitest + React Testing Library provides fast, deterministic component testing.
- **Strict Architectural Boundary with Modernized Test Suites**: Accepted because it cleanly separates concerns:
  1. **Frontend (Vitest + React Testing Library + `@testing-library/user-event`)**: The sole authority for React component rendering, interactive drawer states, viewport toggling, diff expansion, and user input validation.
  2. **Backend (pytest + FastAPI TestClient)**: The sole authority for REST endpoint contracts, route alias equivalence, basic authentication enforcement, and Server-Sent Events (SSE) telemetry stream parsing and demuxing.
  3. **No Cross-Boundary Source Scraping**: Python tests are strictly prohibited from reading frontend source files or spawning Node.js subprocesses.

## Consequences

- All `.tsx` string-reading tests and `node -e` subprocess executions are pruned from `tests/test_ui_events.py`.
- Deprecated Jinja2 ghost tests in `tests/test_ui.py` (`TestStudioSplitPaneAndDualView`) are pruned, retaining API route alias equivalence assertions under the main FastAPI test class.
- The root build entry point (`factory/ui/frontend/index.html`) is reaffirmed as essential for Vite compilation into static assets served by FastAPI.
- A centralized test utility module (`factory/ui/frontend/src/test/test-utils.tsx`) provides `renderWithProviders()` with standard default mocks, and `@testing-library/user-event` is adopted to eliminate React 19 `act(...)` console warnings.
