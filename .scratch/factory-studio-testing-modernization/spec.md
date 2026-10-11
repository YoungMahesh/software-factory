# Spec: Factory Studio Testing Suite Pruning and Setup Modernization

Status: resolved

## Problem Statement

Developers and autonomous coding agents maintaining Factory Studio face high maintenance friction, slow test execution, and brittle test failures due to misaligned testing boundaries and verbose testing syntax across the codebase.

Specifically:
1. The backend Python test suite attempts to verify frontend UI components by opening and string-scanning TypeScript source code files (`.tsx`) looking for arbitrary variable names and JSX tokens, and by spawning Node.js sub-processes to test JavaScript string parsers. These tests break whenever frontend files are refactored, even when user-facing behavior remains completely unchanged.
2. Legacy Jinja2 regression tests remain in the Python test suite, asserting meaningless string tokens like `<div id="root"></div>` or testing backend registry models under misleading UI names.
3. The frontend Vitest suite suffers from high syntactic boilerplate: view tests manually construct 15 to 20 discrete mock properties for context providers in every test file.
4. Frontend tests rely on low-level synthetic event dispatching (`fireEvent`), causing React 19 `act(...)` console warnings and failing to accurately simulate real browser event chains.
5. Vitest incurs unnecessary test isolation and startup overhead across jsdom environments, resulting in slow test suite execution.
6. Ambiguity regarding the frontend build system led to confusion around whether `index.html` could be removed, when in reality Factory Studio is a Compiled Vite React SPA requiring `index.html` as the root entry point.

## Solution

Establish a strict architectural testing boundary between the frontend Single Page Application (SPA) and the backend FastAPI web service, eliminate brittle cross-boundary tests, and modernize testing utilities across both suites:

1. **Strict Testing Boundary**:
   - The frontend React SPA is tested exclusively through its native Vitest test runner.
   - The backend web service is tested exclusively through Python test suites verifying HTTP status codes, JSON payloads, Server-Sent Events (SSE) telemetry multiplexing, and authentication.
2. **Prune Brittle and Redundant Tests**:
   - Remove all Python tests that read `.tsx` component source code as raw text or execute `node -e` subprocesses.
   - Remove redundant Jinja2 ghost tests from the Python suite while preserving legitimate API route alias parity assertions.
3. **Frontend Testing Setup Modernization**:
   - Introduce a centralized test utility module providing a standard render wrapper with sensible default provider states (context and query client), eliminating repetitive mock setups across test files.
   - Adopt simulated user interaction libraries (`user-event`) to eliminate React 19 `act(...)` warnings and model realistic user input workflows.
   - Optimize Vitest execution configuration to streamline test environment setup.
4. **Preserve Vite Build Entrypoint**:
   - Reaffirm that Factory Studio is a Compiled Vite React SPA as codified in ADR 0036 and must retain `index.html` as the build entrypoint.

## User Stories

1. As a frontend maintainer refactoring internal state hooks inside Factory Studio components, I want tests to pass without brittle failures, so that I can refactor component internals without breaking unrelated assertions.
2. As a backend maintainer modifying Python test suites, I want Python tests to focus strictly on API contracts and SSE event streaming, so that tests run quickly and do not depend on frontend file paths.
3. As an engineer writing component tests for Factory Studio views, I want a unified `renderWithProviders` helper with sensible default mocks, so that I do not have to write 20 lines of mock context boilerplate for each test scenario.
4. As an engineer testing form inputs and button clicks in Factory Studio, I want user interactions simulated with full browser event fidelity, so that React 19 does not emit `act(...)` console warnings during test runs.
5. As an engineer executing the frontend test suite, I want Vitest to run swiftly without redundant jsdom creation overhead, so that feedback cycles remain fast.
6. As a developer building Factory Studio for deployment, I want the Vite build process to reliably bundle the single-page application from `index.html`, so that FastAPI can serve the static distribution bundle.
7. As an autonomous coding agent executing the test suite, I want clear test failure messages that reflect actual functional regressions rather than missing variable name substrings in `.tsx` files, so that I can diagnose issues accurately.
8. As a developer observing agent execution in Factory Studio, I want the Agent Event Stream SSE demuxing and backlog replay to be verified by robust backend contract tests, so that streaming telemetry never drops events.
9. As a developer interacting with the Studio View and Testing Console View, I want view navigation and layout toggles verified through native component tests, so that navigation regressions are caught reliably.
10. As a developer submitting conversational prompts to the Software Factory, I want prompt input locking and submission triggers verified through realistic user events, so that concurrent submission bugs are prevented.
11. As a developer switching device viewports in the Live Preview iframe, I want viewport dimension changes verified through React Testing Library assertions, so that responsive previewing works across desktop, tablet, and mobile.
12. As a backend maintainer exposing API endpoints, I want route aliases (such as `/api/repos` and `/api/studio/repos`) verified for identical JSON responses in Python test suites, so that frontend consumers never receive divergent data.
13. As a security engineer auditing Factory Studio, I want Basic Auth enforcement on all REST and SSE endpoints verified by Python HTTP tests, so that unauthenticated access is reliably blocked.
14. As an engineer reviewing codebase architecture, I want an ADR explicitly stating the testing boundaries and Vite SPA conventions, so that future contributors do not reintroduce cross-boundary string-scraping tests.

## Implementation Decisions

- **Testing Boundary Separation**:
  - The frontend testing suite retains sole ownership over all UI component behavior, styling classes, keyboard shortcuts, DOM tree structures, and view transitions.
  - The backend testing suite retains sole ownership over FastAPI endpoint contracts, request validations, Basic Auth security, domain exception mapping, and SSE stream formatting.
  - Cross-boundary inspection (such as Python tests opening TypeScript files to search for code substrings or invoking Node to run JavaScript string parsers) is strictly prohibited.

- **Vite SPA Entrypoint Preservation**:
  - Factory Studio adheres to ADR 0036: it is a Compiled Vite React SPA, not TanStack Start SSR.
  - The root HTML entry point (`index.html`) under the frontend directory is permanent and essential for Vite bundling into the static distribution directory served by FastAPI.

- **Frontend Test Utility Layer**:
  - Establish a shared test helper module in the frontend test directory that exports an enhanced render function wrapping components in both the TanStack Query client provider and the Studio context provider.
  - Supply sensible default mock states for the Studio context (selected repository, active job status, empty message timeline, and stubbed action handlers) with shallow override support.
  - Migrate from synthetic event dispatchers to realistic user interaction dispatchers that naturally trigger complete event sequences (pointer events, focus, keydown, input, keyup, change) and resolve React 19 state synchronization warnings.

- **Vitest Environment Configuration**:
  - Update the Vitest configuration in the frontend build configuration to optimize thread pooling and avoid redundant environment re-instantiation across test files.

- **Python Test Pruning**:
  - In the event stream test suite, remove all test methods that inspect TypeScript files via filesystem reads (`test_console_template_contains_*`, `test_studio_chat_turn_renders_inline_thinking_and_step_chips`, `test_studio_template_contains_activity_drawer_and_inline_disclosures`).
  - Remove test methods that execute Node.js scripts via subprocess (`test_frontend_diff_preview_parser_execution`, `test_frontend_failing_command_auto_expansion_and_stderr_execution`).
  - In the UI test suite, remove the deprecated split-pane test class (`TestStudioSplitPaneAndDualView`), retaining only the route alias equivalence assertion and migrating it into the primary FastAPI application test suite.

## Testing Decisions

- **Testing Philosophy**:
  - Tests must only assert external behavioral contracts, user-observable interactions, and network boundaries. Tests must never assert internal implementation mechanics, variable names, or raw source file text.
- **Frontend Seam**:
  - The sole frontend seam is the Vitest suite executing against React components in a jsdom environment with React Testing Library and user interaction simulation.
  - Prior art: Existing view and component test suites in the frontend workspace (`StudioView.test.tsx`, `LivePreview.test.tsx`, `App.test.tsx`).
- **Backend Seam**:
  - The sole backend seam is the FastAPI TestClient executing against the application instance in Python.
  - Prior art: Existing endpoint and event demux test suites in the test directory (`test_ui.py`, `test_ui_events.py`).

## Out of Scope

- Rewriting Factory Studio as a full-stack TanStack Start application or introducing a Node.js SSR server daemon.
- Changing the public HTTP REST endpoint signatures or the SSE telemetry wire protocol.
- Modifying the underlying Modal sandbox orchestration, in-sandbox assembly line pipeline execution, or dev server supervision scripts.
- Altering the visual styling, theme, or component layouts of Factory Studio.

## Further Notes

- Governed by ADR 0036 (Compiled Vite SPA for Factory Studio) and the domain glossary in `CONTEXT.md`.
- Documented in ADR 0039 (Frontend and Backend Testing Boundaries and Test Suite Modernization).
