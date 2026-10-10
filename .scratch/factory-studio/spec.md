# Spec: Factory Studio for Interactive Frontend Application Generation

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

Building frontend applications with the Software Factory currently requires manually defining GitHub Milestones and Issues in advance, configuring parameters through the CLI or Factory Testing Console, and waiting for pipeline completion without immediate visual feedback. Developers who want an iterative, conversational creation experience—similar to Lovable.dev where a prompt on the left sidebar immediately updates a live web preview on the right—cannot interactively shape and observe UI changes in real time. Furthermore, the web console lacks access control for remote developer environments and defaults to port 3000, colliding with the sandbox dev server ingress on Cloudflare Tunnel.

## Solution

**Factory Studio** is an interactive, prompt-driven frontend application builder and preview workspace hosted on port 3010 (`http://127.0.0.1:3010`), integrated into the Software Factory web service alongside the Factory Testing Console.

The studio delivers:
1. **Lovable-Style Split-Pane Interface**: A left sidebar with conversation history and a prompt bar ("type what you want to build") and a right workspace displaying a live interactive `<iframe>` preview of the running web application served via Cloudflare Tunnel at `https://3000.mahesh0.dev`.
2. **TanStack Start Base Scaffolding**: Standardizes on `https://tanstack.com/start/latest` for all generated web applications, initialized from a canonical template repository (`software-factory-09-test/tanstack-start-template`).
3. **Automated Milestone and Issue Synthesis**: Converts chat prompts into GitHub Milestones (e.g. `v1: Initial App`) and sequential Issues (`#1`, `#2`...) under the target repository in `software-factory-09-test`, accumulating commits on `factory/<feature>` and maintaining Draft Feature PRs.
4. **Strict Frontend-Only Guardrail**: Enforces a strict client-side boundary via an immediate pre-flight LLM check; prompts requesting non-frontend capabilities (databases, backend APIs, server storage) are immediately rejected in chat with an explicit explanation, preventing unsupported sandbox dispatches.
5. **Persistent Preview Keep-Alive**: The sandbox container executes the assembly line stages (Planner, Coder, Verifier, Reviewer), verifies the changes, starts `pnpm dev --port 3000 --host 0.0.0.0` in the background, and keeps the container alive for live interactive testing over Cloudflare Tunnel until cancelled or timed out.
6. **Unified SPA View Toggle**: A top navigation switcher allows instantaneous toggling between "Studio View" (Prompt + Live Preview) and "Console View" (Detailed Launch Form + Full Terminal Streaming), sharing real-time job and SSE connection state.
7. **HTTP Basic Authentication**: Secures all routes and APIs for single-user access using environment credentials (`FACTORY_AUTH_USER` and `FACTORY_AUTH_PASS`).

## User Stories

1. As a developer, I want to access Factory Studio at `http://localhost:3010`, so that the web interface does not collide with the preview dev server on port 3000.
2. As a developer, I want the web interface to require HTTP Basic Authentication, so that only I can access the studio when exposed to the internet.
3. As a developer, I want unauthenticated requests to be rejected with HTTP 401 Unauthorized, so that unauthorized users cannot inspect projects or dispatch jobs.
4. As a developer, I want to switch between "Studio View" and "Console View" via a single click in the top navigation bar, so that I can seamlessly view detailed logs or build apps conversationally.
5. As a developer, I want to see a project dropdown in Studio View listing all available repositories in `software-factory-09-test`, so that I can choose which application to work on.
6. As a developer, I want a "+ New App" button in Studio View, so that I can create a new project repository without opening the GitHub web UI.
7. As a developer, I want the "+ New App" modal to ask for an application name and automatically initialize the repository from `software-factory-09-test/tanstack-start-template`, so that the new project has working dependencies and scripts out of the box.
8. As a developer, I want a left sidebar in Studio View with an input box to type what I want to build, so that I can describe UI features in natural language.
9. As a developer, I want my initial prompt to automatically generate Milestone `v1: Initial App` and GitHub Issue `#1`, so that the assembly line starts building the initial version on `factory/v1`.
10. As a developer, I want subsequent chat prompts in the same project to append sequential GitHub Issues (`#2`, `#3`...) to the active milestone, so that changes accumulate incrementally on the feature branch.
11. As a developer, I want the chat input to evaluate my prompt for backend or database requests before starting a sandbox, so that I don't waste cloud compute on unsupported architectures.
12. As a developer, if I request non-frontend features like databases, backend APIs, or server storage, I want to receive an immediate chat refusal message stating that non-frontend features are not supported, so that I can re-craft my prompt to be strictly client-side.
13. As a developer, I want to see a live preview `<iframe>` on the right side of the screen pointing to `https://3000.mahesh0.dev`, so that I can interact with the app as soon as the sandbox runs it.
14. As a developer, I want the sandbox container to start the TanStack Start dev server (`pnpm dev`) on port 3000 and remain alive after verification, so that I can preview and test the running app live.
15. As a developer, I want the preview frame to include a toolbar with a reload button and an external link icon, so that I can manually refresh or open the live site in a new tab.
16. As a developer, I want device viewport toggles (Desktop, Tablet, Mobile) above the preview frame, so that I can test responsive layouts across different screen sizes.
17. As a developer, I want a floating status badge in Studio View showing the active assembly line stage (e.g. `⚡ Coder Stage (Issue #1)`), so that I know what the agents are currently doing.
18. As a developer, I want a "Inspect Logs" button on the status badge that switches directly to Console View, so that I can inspect the terminal stream if a stage is running or failing.
19. As a developer, I want a "Cancel Run" button readily available, so that I can terminate the running Modal Sandbox at any time if I change my mind.
20. As a developer, I want the chat history to display previous prompts and completed issue summaries, so that I have a clear context of what has already been built.
21. As a developer, I want the application state to remain synchronized when toggling between Studio View and Console View, so that active jobs, log streams, and timers do not reset or reload.

## Implementation Decisions

- **Dedicated Port Reservation**: The web application server binds to port 3010 by default (configurable via environment variable), preserving port 3000 strictly for the sandbox dev server and Cloudflare Ingress.
- **Single-Page Application Architecture**: Studio View and Console View are implemented as client-side views within a unified HTML template, toggled via navigation tabs without page refreshes, sharing global state for active jobs, selected repository, and SSE log listeners.
- **FastAPI HTTP Basic Auth Middleware**: Global middleware intercepts requests to routes and API endpoints, verifying against configured username and password credentials. When environment variables are absent, a local development fallback is used with a startup warning.
- **Template-Based Repository Provisioning**: A dedicated repository creation handler calls GitHub API using the organization credentials to generate repositories from the canonical TanStack Start template repository under the test organization.
- **Fast Intent Classification Guard**: A pre-flight API endpoint evaluates the prompt against client-side constraints using a fast LLM inference call prior to creating GitHub tickets or spawning sandboxes. If backend, database, or server storage keywords/intents are detected, it returns an explicit rejection payload.
- **Conversational Ticket Lifecycle Orchestration**: Submitting a valid prompt translates into GitHub Milestone and Issue creation using the organization token, followed by job registration and sandbox dispatch through the existing job registry and spawner.
- **Sandbox Dev Daemon Keep-Alive**: The factory container entrypoint is augmented to launch the target project dev server on port 3000 following verification stages, maintaining a persistent wait loop until the sandbox reaches its idle timeout or receives a termination signal.

## Testing Decisions

- **What makes a good test**: Tests should verify observable HTTP contracts, authentication responses, API status codes, and JSON payload structures, rather than internal function calls or private state.
- **Modules to be tested**:
  - Web application authentication layer (verifying 401 on missing credentials, 200 on valid credentials across both views and APIs).
  - Studio API endpoints: App listing, app creation from template, and prompt submission with intent classification.
  - Intent classification guard: Verifying that prompts containing backend/database requests return strict refusal responses, while frontend prompts trigger milestone and job creation.
  - Container entrypoint script logic: Validating that dev server keep-alive execution is triggered when verification completes.
- **Prior art**:
  - `tests/test_ui.py`: Existing tests for `FastAPI` routes using `TestClient`, GitHub discovery mocking, and `JobRegistry` interaction.
  - `tests/test_spawner.py` and `tests/test_entrypoint.py`: Existing tests for Modal sandbox provisioning arguments and entrypoint flags.

## Out of Scope

- Multi-user authentication, roles, or permissions (strictly single-user for the developer).
- Deployment of generated applications to production hosting (Vercel, Cloudflare Pages, etc.).
- Backend, database, serverless function, or persistent server-side storage features (strictly client-side frontend apps).
- Organizations other than `software-factory-09-test` in the initial phase.
- Live collaborative multi-cursor code editing.

## Further Notes

- In accordance with ADR 0021, all sandbox public web traffic routes through Cloudflare Tunnel at `https://3000.mahesh0.dev`.
- All target applications will be seeded with TanStack Start, providing standard Vite scripts (`pnpm dev`, `pnpm build`, `pnpm test`).
