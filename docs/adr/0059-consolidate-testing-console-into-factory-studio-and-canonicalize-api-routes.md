# Consolidate Testing Console into Factory Studio and Canonicalize API Routes

**Status**: Accepted (Supersedes [ADR 0032](0032-factory-testing-console.md), Amends [ADR 0034](0034-factory-studio-and-live-preview-workspace.md), [ADR 0036](0036-vite-spa-for-factory-studio.md), and [ADR 0052](0052-unified-studio-sandbox-and-simplified-web-lifecycle.md))

To eliminate UI, state, and route duplication between Factory Studio and the Factory Testing Console, we decided to retire Factory Testing Console as a separate view and tab, consolidate all testing, manual dispatch, and telemetry capabilities into Factory Studio, and canonicalize all backend REST endpoints and frontend API clients on flat `/api/*` routes.

## Context

In ADR 0032, the **Factory Testing Console** was introduced to verify assembly line execution against the Test Organization (`software-factory-09-test`). In ADR 0034 and ADR 0036, **Factory Studio** was introduced as a conversational workspace, with a top navigation switcher allowing toggling between Studio View and Testing Console View within the same Vite SPA.

In ADR 0052, container lifecycles were unified so both the Testing Console and Factory Studio execute exclusively within the **Unified Studio Sandbox** via `sandbox.exec()`. Despite running against the identical container infrastructure, substantial duplication remained across the codebase:

1. **UI & State Duplication**:
   - Both views maintained separate repository selector dropdowns, lock badges, and TanStack compatibility markers (`StudioHeader.tsx` vs `TestingConsoleView.tsx`).
   - Testing Console used an inline parameter form (`JobConfigPanel.tsx`) to manually pick milestones, tickets, and models, duplicating the `Studio Issue Drawer` which already allowed browsing issues and triggering instant dispatch.
   - Live telemetry was fragmented: Testing Console rendered an inline `StageStepper` and `TerminalLogViewer` band, while Studio used the floating status badge and slide-over `ActivityDrawer`. Clicking "Logs" in Studio navigated away to the Console tab.
2. **Backend Route & API Duplication**:
   - Backend routes under `factory/ui/routes/` duplicated endpoints under dual prefixes: `@router.get("/api/repos")` and `@router.get("/api/studio/repos")`, `@router.get("/api/repos/{repo}/branches")` and `@router.get("/api/studio/repos/{repo}/branches")`.
   - Dispatch routes were fragmented between `/api/jobs` (used by Console) and `/api/studio/dispatch` / `/api/studio/approve` (used by Studio).
   - Frontend `api.ts` maintained duplicate client functions (`fetchRepos` and `fetchStudioRepos`).

## Decision

1. **Retire Standalone Testing Console View**:
   - The top-level tab switcher in `AppNavigation.tsx` is removed. Factory Studio is the sole interactive web interface for the Software Factory.
   - The `/console` URL route automatically redirects to `/` while preserving query parameters (e.g. `?repo=...`).
   - `TestingConsoleView.tsx`, `JobConfigPanel.tsx`, and associated obsolete test files are deleted.

2. **Unified Telemetry and Job History in Activity Drawer**:
   - The slide-over `ActivityDrawer` is expanded from two tabs (`Timeline`, `Logs`) to three tabs: `Timeline`, `Logs`, and `History`.
   - The `History` tab presents the multi-run job history table, enabling developers to monitor past runs, inspect status and stages, cancel running jobs, and switch the active log stream in place without navigating away from the Studio workspace.

3. **Consolidate Execution Controls into Studio Issue Drawer**:
   - `Studio Issue Drawer` is enhanced with a collapsible "Execution Settings" panel providing Model selection (DeepSeek V4.1 Flash vs MiMo-V2.6-Flash) and VM Sandbox virtualization toggles.
   - These execution settings are passed directly to Instant Dispatch and Milestone batch runs, eliminating the need for `JobConfigPanel`.

4. **Canonicalize on Flat `/api/*` Endpoints**:
   - All backend routes are unified under clean, RESTful `/api/*` paths, completely removing the legacy `/api/studio/*` prefix:
     - Repositories: `/api/repos`, `/api/repos/{repo}/branches`, `/api/repos/{repo}/milestones`, `/api/repos/{repo}/issues`
     - Live Preview: `/api/repos/{repo}/preview`, `/api/repos/{repo}/preview/stream`, `/api/repos/{repo}/preview/branch`, `/api/repos/{repo}/preview/sync`
     - Pull Requests: `/api/repos/{repo}/pulls`, `/api/repos/{repo}/pulls/{pull_number}/merge`, `/api/repos/{repo}/pulls/{pull_number}/ready`
     - Rollback: `/api/repos/{repo}/rollback`, `/api/repos/{repo}/rollback/preview`
     - Chat & Synthesis: `/api/prompt`, `/api/approve`, `/api/dispatch`, `/api/repos/{repo}/messages`
     - Jobs & SSE Streaming: `/api/jobs`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/cancel`, `/api/jobs/{job_id}/stream`
   - Route modules in `factory/ui/routes/` are renamed to clean domain names: `preview.py`, `chat.py`, `pulls.py`, `rollback.py`, `repos.py`, and `jobs.py`.

5. **Frontend API Client Simplification**:
   - `api.ts` and `useStudioQueries.ts` are streamlined to use canonical `/api/*` endpoints, removing duplicate query hooks and fetch functions.

## Consequences

- **Domain Model**: `Factory Testing Console` is marked deprecated and superseded by `Factory Studio` in `CONTEXT.md`.
- **Eliminated Cognitive Overhead**: Developers no longer switch between two disparate tabs to monitor jobs, inspect logs, or dispatch tickets. All operations occur within the unified split-pane Studio with focused slide-over drawers.
- **Codebase Reductions**: Over 600 lines of redundant frontend and backend view code, forms, duplicate routes, and wrappers are excised.
- **Line Budgets**: All new and modified TypeScript and Python files strictly adhere to the <= 500 lines budget.
