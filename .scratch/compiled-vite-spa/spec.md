# Spec: Compiled Vite React SPA for Factory Studio and Testing Console

Status: ready-for-agent

## Problem Statement

The Factory Studio and Factory Testing Console currently run as a monolithic Jinja2 template containing over 3,100 lines of mixed HTML and imperative JavaScript. Over 80% of this file is client-side code managing Server-Sent Events, ANSI terminal decoding, multi-turn chat timelines, expandable activity drawers, and view navigation through manual DOM manipulation and custom event handling.

As complex features like real-time LLM reasoning disclosures, synchronized command timelines, diff viewers, and live application preview controls continue to expand, this monolithic architecture creates significant engineering friction:
1. Imperative DOM manipulation leads to state desynchronization, race conditions with streaming telemetry, and memory leaks.
2. The lack of standard component abstractions forces custom, uncoordinated implementations for accordions, tabs, drawer slide-overs, and virtualized log streaming.
3. The lack of compile-time type safety allows schema mismatches between backend telemetry envelopes and frontend renderers to fail silently at runtime.
4. Autonomous coding agents modifying individual UI capabilities struggle with cognitive overload and context boundaries when editing a 3,100+ line monolith, increasing token consumption and the risk of accidental regressions.

## Solution

Decompose and modernize the control plane web interface by transitioning from the monolithic template to a compiled Vite React Single Page Application (SPA) colocated within the UI package, statically served by the existing FastAPI backend.

1. **Declarative Component Hierarchy**: Rebuild the UI using React 19, TypeScript, Tailwind CSS, TanStack Router, and TanStack Query, separating concerns into modular, typed components (chat conversation, live preview iframe controller, command execution timeline, collapsible thought disclosures, activity drawer, and testing console forms/steppers).
2. **FastAPI Static Serving**: Configure the FastAPI backend to mount and statically serve the compiled production assets from a dedicated static distribution directory, preserving the zero-overhead, single-process Python runtime for CLI and local workstation execution.
3. **Dual-Route Strangler Cutover**: Mount the compiled SPA at a secondary route (`/v2`) alongside the legacy template at `/`, allowing live side-by-side verification and zero disruption to ongoing assembly line validation while achieving full feature parity.
4. **Vite Dev Server Proxy**: Support hot-module replacement (HMR) during frontend development by proxying REST API endpoints and real-time Server-Sent Event (SSE) streams from Vite to the running FastAPI server on port 3010.

## User Stories

1. As a frontend engineer, I want the UI organized into modular TypeScript React components, so that I can modify the activity drawer or chat view without navigating a 3,100-line monolithic file.
2. As an autonomous coding agent, I want bounded component files with clear TypeScript interfaces, so that I can implement UI features without risking regressions across unrelated sections of the codebase.
3. As a developer launching the software factory locally via the CLI or Python module, I want the web interface to serve immediately from a single Python command without needing to launch a separate Node server, so that my operational workflow remains simple.
4. As a developer watching an active job, I want streaming thought disclosures, command chips, and terminal logs to update reactively through declarative state, so that the UI never suffers from DOM desynchronization or race conditions.
5. As a developer building frontend features on the control plane, I want instant Hot Module Replacement (HMR) when saving TSX and CSS files, so that I receive immediate feedback without full page reloads.
6. As a developer inspecting large test suites or long compilation logs, I want a virtualized terminal log viewer, so that tens of thousands of log lines do not cause browser scrolling lag or memory bloat.
7. As a Factory Studio user, I want a responsive slide-over Agent Activity drawer that smoothly opens and closes while keeping the live application preview iframe intact, so that I can inspect execution traces without losing context.
8. As a Factory Studio user, I want the live application preview iframe to provide reload triggers, responsive viewport toggles (mobile, tablet, desktop), and external link opening, so that I can test generated frontend applications thoroughly.
9. As a developer using the Factory Testing Console, I want repository selection, feature/ticket discovery, model selection, and launch parameters to exist in a dedicated, validated form view, so that I can dispatch test assembly lines reliably.
10. As a developer monitoring multi-stage pipeline runs, I want visual stage steppers and status badges to transition smoothly between Preflight, Planner, Coder, Verifier, and Reviewer stages, so that job progression is obvious at a glance.
11. As a developer reviewing generated code changes, I want a unified diff viewer component for file modifications, so that code patches are syntax-highlighted and readable.
12. As an operator verifying the new SPA before cutover, I want to access the React interface at `/v2` while retaining the existing template at `/`, so that I can compare functionality side-by-side against active sandboxes.
13. As a developer reconnecting to an ongoing or completed job, I want the SPA to rehydrate its entire state from cached telemetry envelopes and terminal backlogs via SSE, so that refreshing the page never loses run history.
14. As an administrator accessing Factory Studio, I want HTTP Basic Authentication to protect both the SPA and underlying API endpoints consistently, so that unauthorized users cannot dispatch jobs or inspect repositories.
15. As a developer running tests in CI, I want automated backend tests to verify static asset serving and SPA index fallback routing, so that deployment packaging errors are caught immediately.

## Implementation Decisions

- **Frontend Workspace Colocation**:
  The frontend source workspace will be established directly within the UI package directory, keeping all web interface concerns encapsulated and preventing root-level clutter. The package will define standard build scripts (`pnpm build`, `pnpm dev`, `pnpm test`).

- **Target Build Directory & Production Artifacts**:
  The frontend build pipeline compiles static HTML, JavaScript, and CSS assets directly into a dedicated distribution directory within the UI static assets folder. These build artifacts are served directly by the backend web server.

- **FastAPI Static Files & Catch-All Routing**:
  The Python application mounts a static file handler pointing to the compiled distribution directory. To support client-side routing, an endpoint handler serves the compiled HTML shell for unmatched non-API routes under the SPA path prefix, while all `/api/*` endpoints retain precedence.

- **Strangler Cutover Architecture**:
  The application maintains dual-route capability during development. The legacy template is served on the root path `/` until the React SPA reaches 100% verified feature parity, while the compiled SPA is served on `/v2`. Once verified, the SPA transitions to the default root handler, and the monolithic template is decommissioned.

- **Vite Development Proxy Configuration**:
  The frontend build tool is configured with a development proxy that forwards API requests (`/api/*`) and real-time event streams (`/api/jobs/{id}/stream`) to the backend web server on port 3010, enabling hot-reloading on port 5173 without cross-origin configuration hassles.

- **State Management & Stream Consumption**:
  The client uses query management hooks for cached server state (repository listings, milestone metadata, ticket lists) and custom event-source hooks for the real-time agent event stream. Telemetry events update a centralized client-side job store, driving UI components reactively.

## Testing Decisions

- **Testing Philosophy**:
  Tests must exercise external behavioral contracts rather than internal component implementation details. Backend tests verify route resolution, static header delivery, SPA fallback, and API stability. Frontend tests verify user-facing behavior, event rehydration, and component interactions using accessible queries.

- **Backend Seams (`tests/test_ui.py`)**:
  - Test static directory mounting and asset delivery via the existing FastAPI test client seam.
  - Verify that requests to `/v2` (and child SPA routes) return the compiled HTML document with appropriate content types.
  - Verify that legacy routes (`/`) continue serving the existing dashboard without regression while dual-routing is active.
  - Verify that all `/api/*` endpoints and `/api/jobs/{id}/stream` behave identically regardless of whether accessed by the legacy template or the SPA.

- **Frontend Component Seams**:
  - Unit and component tests for individual widgets (Thought Accordion, Step Chip, Activity Drawer, Status Badge, Form Stepper).
  - Telemetry hook tests asserting correct state transitions and message accumulation given mock SSE event streams.
  - Prior art: existing Python unit tests in `tests/test_ui.py` and `tests/test_ui_events.py`.

## Out of Scope

- Rewriting the Python backend or Modal sandbox orchestrator in Node.js/TypeScript.
- Changing the wire format or payload schema of the Agent Event Stream.
- Modifying target sandbox application templates or in-sandbox TanStack Start generators.
- Adding user accounts or multi-tenant database authentication beyond the existing Basic Auth mechanism.

## Further Notes

- Governed by ADR 0036 (`docs/adr/0036-vite-spa-for-factory-studio.md`), which formally amends ADR 0032.
- The canonical domain glossary in `CONTEXT.md` applies to all component names and labels: use Factory Testing Console and Factory Studio; avoid deprecated terms like Factory UI.
