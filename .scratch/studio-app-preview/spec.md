# Spec: Dedicated Application Preview in Factory Studio

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When developers select an existing application repository in Factory Studio, the right-hand preview panel remains inactive and blank unless an assembly line job is actively executing. Developers who want to evaluate, demonstrate, or interact with the current state of an application—either on its canonical baseline or on its active feature branch—cannot do so without submitting a new prompt and waiting for the full multi-agent assembly line pipeline (Planner, Coder, Verifier, Reviewer) to run. Furthermore, the singleton Cloudflare Tunnel ingress causes routing collisions if multiple developers or sandboxes attempt to run dev servers simultaneously.

## Solution

Introduce a **Dedicated Preview Sandbox** capability directly accessible from Factory Studio. When a developer selects a repository, a "Preview App" button in the top control bar and a prominent "Launch Live Preview" CTA in the empty preview panel allow instant activation of the application.

The feature provisions an ephemeral Modal Standard Sandbox that bypasses all agent stages, checks out the active feature branch (or `main`), installs dependencies, runs the development server on port 3000, and exposes the app over an isolated **Modal Application Tunnel** (`https://<sandbox-id>-3000.modal.host`). Cloudflare Tunnel ingress is disabled for preview sandboxes, eliminating network collisions and enabling concurrent previews across multiple projects. The preview workspace displays startup progress, provides an inline collapsible dev server log drawer, and offers lifecycle controls including device viewport toggling, manual refresh, and an explicit stop button backed by a 30-minute idle timeout.

## User Stories

1. As a developer selecting a repository in Factory Studio, I want to see a "Preview App" button in the top control bar, so that I can launch the current version of the application on demand.
2. As a developer viewing a repository without an active preview, I want to see a prominent "Launch Live Preview" button in the right panel empty state, so that I can quickly start the app without hunting for controls.
3. As a developer launching an application preview, I want the backend to provision a Dedicated Preview Sandbox on Modal without running Planner, Coder, Verifier, or Reviewer agents, so that the app starts rapidly without consuming agent LLM tokens.
4. As a developer launching a preview, I want the sandbox to check out the active Feature Branch (`factory/<feature>`) if an active feature or milestone exists, so that I can see the latest accumulated changes.
5. As a developer previewing a clean repository without an active feature branch, I want the sandbox to check out the `main` branch, so that I can inspect the canonical production baseline.
6. As a developer previewing an application, I want the sandbox to expose port 3000 as a Modal Application Tunnel, so that each preview instance gets a unique, isolated HTTPS URL.
7. As a developer, I want the preview sandbox to disable Cloudflare Tunnel ingress, so that concurrent preview sandboxes do not collide or disrupt other running factory tasks.
8. As a developer waiting for a preview to boot, I want to see a visual progress stepper in the right panel (`Provisioning sandbox` → `Installing dependencies` → `Starting dev server`), so that I know what stage the preview startup is in.
9. As a developer waiting for a preview, I want an inline collapsible "Dev Server Logs" terminal drawer, so that I can monitor the live output of dependency installation and Vite startup.
10. As a developer whose dev server crashes or fails dependency installation, I want to see an inline failure alert with the expanded error log and a "Retry" button, so that I can diagnose and fix build issues.
11. As a developer with an active preview, I want the right panel `<iframe>` to embed the unique Modal Application Tunnel URL, so that I can interact with the live running application.
12. As a developer testing responsive layouts, I want viewport switcher buttons (Desktop, Tablet, Mobile) above the preview frame, so that I can evaluate how the app looks across various device widths.
13. As a developer with multiple projects in the Test Organization, I want to switch between repositories in the dropdown and have each project maintain its own preview state, so that I can seamlessly inspect different apps without restarting containers.
14. As a developer testing an app, I want a reload button in the preview toolbar, so that I can refresh the embedded iframe when needed.
15. As a developer, I want an external link button in the preview toolbar, so that I can open the full Modal Application Tunnel URL in a new browser tab.
16. As a developer finished with testing, I want a red "Stop" button in the toolbar and top control bar, so that I can immediately terminate the running preview sandbox.
17. As a developer who walks away from a running preview, I want the preview sandbox to automatically terminate after 30 minutes of container idle time, so that cloud resources and credits are not wasted.
18. As a developer, I want a badge in the preview toolbar displaying the active branch being previewed (`main` or `factory/<feature>`), so that I always know which codebase revision is running.
19. As a developer, I want the top control bar to show a loading spinner when a preview is provisioning and a green status dot when active, so that I have immediate status feedback.
20. As a developer using the API, I want dedicated endpoints to launch, check status of, stream logs from, and terminate previews per repository, so that frontend components have clean, isolated contracts.

## Implementation Decisions

- **Dedicated Preview Sandbox Provisioning**: The spawner engine will support a dedicated preview mode that provisions a Modal Standard Sandbox with `encrypted_ports = [3000]`, sets `ENABLE_CLOUDFLARE = "0"`, enforces a 30-minute idle timeout (`idle_timeout = 1800`), and executes the repository dev server keep-alive loop directly without invoking the multi-agent assembly line pipeline.
- **Dynamic Modal Application Tunnel Resolution**: The spawner will extract the HTTPS tunnel URL directly from the active Modal sandbox tunnels map on port 3000 and return it as the canonical preview URL.
- **Git Revision Resolution**: When provisioning a preview, the engine will query the target repository for active feature branches (`factory/<feature>`). If an active feature branch exists, it will be checked out; otherwise, the repository will be served from the default `main` branch.
- **In-Memory Preview Registry**: A thread-safe preview registry will maintain active preview sandbox references and states (`IDLE`, `PROVISIONING`, `SERVING`, `FAILED`, `STOPPED`) keyed by repository name. It will capture log lines into a ring buffer and broadcast events to connected listeners.
- **Dedicated REST and SSE API Endpoints**:
  - `POST /api/studio/repos/{repo}/preview` to dispatch a dedicated preview sandbox.
  - `GET /api/studio/repos/{repo}/preview` to retrieve the current preview status, branch name, tunnel URL, and logs.
  - `DELETE /api/studio/repos/{repo}/preview` to terminate the active preview sandbox.
  - `GET /api/studio/repos/{repo}/preview/stream` to deliver real-time Server-Sent Events during startup and execution.
- **Factory Studio UI Integration**:
  - Top control bar: A "Preview App" button with dynamic state indicators (idle, provisioning spinner, running indicator with stop option) adjacent to the repository selector.
  - Live preview workspace: An empty-state CTA card, a 3-stage provisioning stepper, a collapsible terminal logs drawer, an active branch indicator badge, and stop controls alongside existing viewport toggles.

## Testing Decisions

- **What makes a good test**: Tests should verify observable external behaviors and HTTP contracts (request/response statuses, JSON payload schema, SSE event sequences, UI rendering, button interactions, and iframe source URLs), without relying on internal function implementations or private state.
- **Modules to be tested**:
  - Backend API Layer: Integration tests covering preview creation, status queries, SSE log streaming, and termination with mocked Modal sandbox instances.
  - Spawner & Registry Layer: Unit tests verifying `encrypted_ports = [3000]`, `ENABLE_CLOUDFLARE = "0"`, idle timeout configuration, and thread-safe multi-repository state management.
  - Frontend Component Layer: Unit and component integration tests verifying button rendering, state transitions from empty state to provisioning, log drawer expansion, iframe embedding of Modal tunnel URLs, and stop button dispatch.
- **Prior art**:
  - `tests/test_ui.py`: Existing FastAPI integration test fixtures and route testing patterns.
  - `tests/test_spawner.py`: Existing Modal sandbox provisioning and argument inspection tests.
  - Frontend test suites in `StudioView.test.tsx` and `LivePreview.test.tsx`: Existing React Testing Library and Vitest component specs.

## Out of Scope

- Running multi-agent assembly line stages (Planner, Coder, Verifier, Reviewer) during dedicated preview mode.
- Deploying generated applications to external cloud providers (Vercel, Cloudflare Pages, Netlify).
- Non-frontend repositories that do not expose a web dev server on port 3000.
- Multi-user authentication, roles, or permissions beyond single-user HTTP Basic Authentication.
- Editing code directly within the live preview pane.

## Further Notes

- Amends ADR 0021 per [ADR 0037](file:///root/software-factory/docs/adr/0037-reintroduce-modal-application-tunnels-for-preview.md) by restoring Modal encrypted tunnels on port 3000 specifically for Dedicated Preview Sandboxes.
- Works in harmony with existing assembly line runs without colliding on Cloudflare Ingress.
