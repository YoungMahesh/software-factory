# Spec: Consolidate Testing Console into Factory Studio and Canonicalize API Routes

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

The Software Factory web workspace currently presents two competing top-level interfaces: Factory Studio and the Factory Testing Console. Although ADR 0052 unified the background container execution lifecycle so that all interactive and testing workflows run exclusively inside the Unified Studio Sandbox via in-sandbox process execution (`sandbox.exec`), the application surface continues to suffer from severe UI, state, and route duplication:

1. **Fragmented Developer Experience**: Developers must switch between two top-level navigation tabs ("Factory Studio" and "Factory Testing Console") to perform related tasks. Factory Studio provides conversational grilling and live application preview, but hides raw execution logs behind a switch to the console. The Factory Testing Console provides raw execution logs and job history, but duplicates repository selection and lacks conversational context.
2. **Duplicated Frontend Controls and Forms**: Both views maintain independent repository selector dropdowns, private repository indicator badges, and TanStack compatibility chips. Furthermore, the Testing Console features an isolated parameter form for selecting milestones and tickets, directly duplicating the Studio Issue Drawer which already lists GitHub issues and supports instant dispatch.
3. **Fragmented Telemetry Surfaces**: Telemetry is divided between an inline terminal log feature band in the Testing Console and a slide-over Activity Drawer in Factory Studio. When viewing an active job in Studio, clicking "Logs" forces a tab switch to the Testing Console rather than displaying the logs in place.
4. **Backend REST Route and Client Duplication**: Backend routers duplicate identical handlers under dual route prefixes (`/api/repos` vs `/api/studio/repos`, `/api/repos/{repo}/branches` vs `/api/studio/repos/{repo}/branches`). In addition, job dispatch is split between `/api/jobs` and `/api/studio/dispatch`, while the frontend client library exports redundant fetching functions (`fetchRepos` and `fetchStudioRepos`).

## Solution

Retire the Factory Testing Console as a standalone view and navigation tab, consolidate all testing, manual parameter configuration, and multi-run job history into Factory Studio, and canonicalize all backend REST routes on flat `/api/*` endpoints:

1. **Unified Studio Workspace**:
   - Remove the top navigation tab switcher. Factory Studio becomes the single, unified web workspace.
   - Redirect any incoming requests to `/console` seamlessly to the root application view `/`, preserving repository query parameters (`?repo=...`).
   - Remove the obsolete Testing Console view component and its separate job configuration form.

2. **Multi-Run History and Telemetry in Activity Drawer**:
   - Expand the slide-over Activity Drawer from two tabs (`Timeline`, `Logs`) to three tabs: `Timeline`, `Logs`, and `History`.
   - The `History` tab displays all past pipeline execution runs for the target repository, showing job identifiers, status badges, pipeline stage indicators, and timestamps.
   - Selecting a past job switches the active log and timeline viewer in place, allowing developers to inspect prior terminal outputs and cancel active runs without leaving Factory Studio.

3. **Consolidated Execution Settings in Studio Issue Drawer**:
   - Enhance the Studio Issue Drawer with a collapsible execution settings bar containing Model selection (toggling between DeepSeek V4.1 Flash and MiMo-V2.6-Flash) and VM Sandbox virtualization toggles.
   - Wire these parameters directly into the Instant Dispatch action and the milestone batch execution control, eliminating the need for a separate manual launch form.

4. **Canonical Flat `/api/*` Routes**:
   - Canonicalize all backend REST endpoints under `/api/*`, removing all `/api/studio/*` route prefixes and duplicate decorators.
   - Reorganize route modules to clean domain names: `preview.py`, `chat.py`, `pulls.py`, `rollback.py`, `repos.py`, and `jobs.py`.
   - Streamline the frontend API client and query hooks to call canonical `/api/*` endpoints.

## User Stories

1. As a software factory developer, I want a single unified web workspace in Factory Studio, so that I don't have to navigate between two separate tabs to prompt, preview, and monitor tests.
2. As a developer navigating to `/console` via bookmarks or browser history, I want to be redirected to the main Studio view while keeping my selected repository query parameter, so that my workflow is not interrupted.
3. As a developer monitoring an active Assembly Line Pipeline run, I want to inspect terminal logs directly inside the Activity Drawer in Factory Studio, so that I don't have to switch away from my conversational prompt history and live application preview.
4. As a developer troubleshooting a failed pipeline run, I want to view a History tab in the Activity Drawer listing recent runs, so that I can easily select previous jobs and inspect their terminal outputs and telemetry events.
5. As a developer running an active job, I want to be able to cancel the running job from either the Studio header badge or the Activity Drawer History tab, so that I can stop runaway jobs immediately.
6. As a developer browsing issues in the Studio Issue Drawer, I want to see an expandable execution settings panel, so that I can choose whether to dispatch an issue with DeepSeek V4.1 Flash or MiMo-V2.6-Flash.
7. As a developer testing complex workloads, I want to toggle VM Sandbox mode from the Studio Issue Drawer settings, so that I can dispatch jobs requiring Docker virtualization directly from the issue list.
8. As a developer dispatching an entire feature milestone, I want my selected model and VM execution settings to apply to the milestone batch run, so that all issues in the batch execute with the specified configuration.
9. As a developer switching repositories, I want a single canonical repository selector in the Studio header, so that repository switching is unambiguous and state is never duplicated across disparate selectors.
10. As a frontend engineer developing the UI, I want the top navigation bar to display only the product branding, active job indicator, and current repository, so that the navigation interface is clean and clutter-free.
11. As an API client consuming the backend, I want all repository endpoints to live under `/api/repos`, so that I don't need to guess whether to query `/api/repos` or `/api/studio/repos`.
12. As an API client managing live previews, I want preview control and SSE streaming endpoints to reside under `/api/repos/{repo}/preview`, so that preview endpoints follow consistent REST hierarchy.
13. As an API client managing pull requests, I want pull request endpoints to reside under `/api/repos/{repo}/pulls`, so that branch merging and status checks use clean canonical paths.
14. As an API client triggering turns or dispatching jobs, I want chat and dispatch endpoints to reside under `/api/prompt`, `/api/approve`, and `/api/dispatch`, so that action routes are clean, direct, and non-duplicated.
15. As a developer reading the codebase, I want route modules in the backend to be named after their domain responsibilities (`preview.py`, `chat.py`, `pulls.py`, `rollback.py`) rather than prefixed with `studio_`, so that the directory structure is modular and deep.
16. As a maintainer running test suites, I want automated frontend tests to drive the complete application through `<App />` and `<ActivityDrawer />` rather than testing redundant standalone console views, so that tests assert realistic developer interactions.
17. As a maintainer ensuring code quality, I want all deleted view and form components removed completely rather than left as dead code, so that file budget ratchets and maintenance overhead remain minimal.
18. As a developer reviewing domain documentation, I want `CONTEXT.md` to clearly mark the Factory Testing Console as deprecated and superseded by Factory Studio, so that terminology across the team remains precise and aligned.

## Implementation Decisions

- **Single Application Root**:
  - The application navigation component will render only the product logo/title, active pipeline status indicator, and active repository badge, completely omitting the tab switcher.
  - The application root will render the split-pane Studio view as the primary workspace.
  - History state handling will redirect any navigation to `/console` directly to `/` while retaining the `?repo=` parameter.

- **Activity Drawer Tab Architecture**:
  - The slide-over Activity Drawer will manage an active tab state supporting three tabs: `Timeline`, `Logs`, and `History`.
  - The `History` tab will display a table of recent jobs for the current repository, populated from the jobs query.
  - Each job row will display the Job ID, repository, feature/issue name, status badge, stage, and relative timestamp.
  - An eye icon button will allow selecting any job to view its terminal logs in the `Logs` tab.
  - A cancel button will be displayed for jobs currently in `RUNNING` status.

- **Studio Issue Drawer Execution Settings**:
  - The issue drawer header will include a collapsible "Execution Settings" section containing:
    - A model selection dropdown with options for DeepSeek V4.1 Flash and MiMo-V2.6-Flash.
    - A checkbox for VM Sandbox virtualization with Docker support.
  - When triggering Instant Dispatch on an issue or executing an entire milestone, these configured parameters will be passed in the dispatch payload.

- **Backend Route Reorganization & Endpoint Canonicalization**:
  - Route modules in the web package will be renamed from `studio_<domain>.py` to `<domain>.py`:
    - `studio_preview.py` → `preview.py`
    - `studio_chat.py` → `chat.py`
    - `studio_pulls.py` → `pulls.py`
    - `studio_rollback.py` → `rollback.py`
  - All endpoint decorators will be canonicalized under flat `/api/*`:
    - Repositories: `GET /api/repos`, `POST /api/repos`, `GET /api/repos/{repo}/branches`, `GET /api/repos/{repo}/milestones`, `GET /api/repos/{repo}/issues`, `GET /api/repos/{repo}/issues/{issue_number}`
    - Live Preview: `GET /api/repos/{repo}/preview`, `POST /api/repos/{repo}/preview`, `DELETE /api/repos/{repo}/preview`, `GET /api/repos/{repo}/preview/stream`, `POST /api/repos/{repo}/preview/branch`, `POST /api/repos/{repo}/preview/sync`
    - Pull Requests: `GET /api/repos/{repo}/pulls`, `POST /api/repos/{repo}/pulls/{pull_number}/merge`, `POST /api/repos/{repo}/pulls/{pull_number}/ready`
    - Rollback: `POST /api/repos/{repo}/rollback`, `POST /api/repos/{repo}/rollback/preview`
    - Chat & Execution: `POST /api/prompt`, `POST /api/approve`, `POST /api/dispatch`, `GET /api/repos/{repo}/messages`, `DELETE /api/repos/{repo}/messages`
    - Job Telemetry: `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel`, `GET /api/jobs/{job_id}/stream`
  - The legacy `/api/studio/*` routes will be completely removed without redirects.

- **Frontend API and Query Hook Streamlining**:
  - The client API library will export singular fetch functions targeting canonical `/api/*` endpoints.
  - Duplicate functions like `fetchStudioRepos` will be removed in favor of `fetchRepos`.
  - React Query keys and custom hooks will be simplified to refer to canonical endpoints.

- **Component Deletion**:
  - `TestingConsoleView.tsx` and its test suite `TestingConsoleView.test.tsx` will be deleted.
  - `JobConfigPanel.tsx` under the console components directory will be deleted.
  - Unused console-specific hooks will be retired or integrated into the Activity Drawer.

## Testing Decisions

- **Testing Philosophy**:
  - Tests will assert external behavior through user interactions and network API contracts, never asserting private component state or internal helper functions.
  - Tests must respect the two highest possible seams in the architecture:
    1. **Frontend Highest Seam**: Testing Library integration tests rendering `<App />` and component subtrees (`<ActivityDrawer />`, `<IssueDrawer />`), verifying user interactions, URL parameter synchronization, drawer state transitions, and server event handling against mocked HTTP endpoints.
    2. **Backend Highest Seam**: FastAPI `TestClient` tests verifying HTTP status codes, JSON response schemas, parameter validations, and SSE event streaming against the FastAPI application mounted with in-memory database persistence.

- **Frontend Test Suite Updates**:
  - `App.navigation.test.tsx` and `App.routing.test.tsx` will be updated to verify that the application renders the unified Factory Studio directly, that `/console` paths redirect cleanly to `/` with query parameters intact, and that the top navigation switcher is absent.
  - `ActivityDrawer.test.tsx` will be expanded to verify the `History` tab, testing job list rendering, job selection for log inspection, and job cancellation.
  - `IssueDrawer.test.tsx` will be expanded to verify execution settings toggling and payload forwarding during instant dispatch and milestone execution.

- **Backend Test Suite Updates**:
  - FastAPI endpoint integration tests (`test_fastapi_app.py`, `test_dispatch_endpoint.py`, `test_approve_endpoint.py`, `test_fastapi_preview.py`, `test_pull_requests_endpoints.py`, `test_turn_rollback.py`) will be updated to assert canonical flat `/api/*` routes.
  - Tests will assert that legacy `/api/studio/*` paths return 404 Not Found.

- **Prior Art**:
  - Frontend integration tests in `App.navigation.test.tsx` and `App.routing.test.tsx`.
  - Backend integration tests in `tests/test_ui/test_fastapi_app.py` and `tests/test_ui/test_dispatch_endpoint.py`.

## Out of Scope

- Modifying the in-sandbox assembly line pipeline (`pipeline.ts`) or agent harness stages.
- Altering the Modal cloud infrastructure, spawner, or sandbox virtualization definitions.
- Introducing multi-organization support beyond `software-factory-09-test`.
- Modifying the underlying database schema (`chat_messages`, `factory_jobs`, `previews`).

## Further Notes

- Architectural Decision Record [`0059-consolidate-testing-console-into-factory-studio-and-canonicalize-api-routes.md`](file:///root/software-factory/docs/adr/0059-consolidate-testing-console-into-factory-studio-and-canonicalize-api-routes.md) documents the architectural consensus and context.
- Domain glossary [`CONTEXT.md`](file:///root/software-factory/CONTEXT.md) has been updated to mark `Factory Testing Console` as deprecated.
