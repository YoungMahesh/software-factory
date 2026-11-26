# ADR 0096: Next.js Sandbox Dashboard and Same-Origin Control Plane BFF

**Status**: Accepted (Amends [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md), [ADR 0092](0092-host-sandbox-dashboard-on-base-domain.md), and [ADR 0095](0095-scratchpad-ideas-raw-split-and-catalog-cache.md)).

We migrate the **Sandbox Web Dashboard** from the monolithic `sandboxes/sandbox/static/index.html` Alpine.js page to a modular **Next.js 16 + React 19** application at `dashboard/` inside the monorepo, backed by the existing Modal FastAPI Control Plane (`sandboxes/sandbox/web.py` and `sandboxes/sandbox/function.py`) through a same-origin Backend-for-Frontend (BFF) proxy.

## Context

The embedded single-file `sandboxes/sandbox/static/index.html` grew to 2,769 lines across four distinct workflows (**Builder**, **Sandboxes**, **Snapshots**, and **Scratchpad** Ideas/Raw), duplicating mobile/desktop layouts and mixing form state, SSE stream parsing, and polling logic in a flat Alpine object. Meanwhile, `resource-plane/` and `app-template/` standardize Software Factory web UIs on Next.js 16, React 19, Zod contracts, Warm Canvas (`@dashboard/theme`), and Vitest.

At the same time, the Control Plane API on Modal owns `factory-state-v1` (`FactoryStateStore`), `run_launch_request.spawn()`, OpenCode Scratchpad synthesis, and Modal SDK credentials, while CLI clients (`modal-sandbox --remote`, `codexprofile`) rely on `MODAL_SANDBOX_ENDPOINT_URL=https://<APPS_BASE_DOMAIN>` routing `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles`.

## Decisions

1. **In-Monorepo `dashboard/` Workspace (`--no-db`, Warm Canvas, Basic Auth)**:
   - Place the dashboard at `dashboard/` (sibling to `resource-plane/`, registered in root `pnpm-workspace.yaml` with distinct package names `@dashboard/web`, `@dashboard/theme`, and `@dashboard/types` to avoid colliding with `resource-plane`'s `@repo/*` packages while remaining standalone-buildable via `dashboard/Dockerfile`).
   - Omit PostgreSQL (`--no-db`) because durable app/sandbox/catalog state stays on Modal (`factory-state-v1`, `modal.Dict`) and GitHub (`config`).
   - Adopt Warm Canvas styling from `app-template/` (`@dashboard/theme`) and protect the Next.js edge with HTTP Basic Auth (`middleware.ts` validating `WEB_UI_USERNAME` / `WEB_UI_PASSWORD`).

2. **Same-Origin BFF Proxy (`app/api/[...path]/route.ts`)**:
   - Forward browser `/api/*` requests (except `/api/health`) to `SANDBOX_CONTROL_PLANE_URL` (`*.modal.run`) with server-side Basic Auth header injection, self-proxy loop validation against `APPS_BASE_DOMAIN`, and unbuffered SSE passthrough for `POST /api/sandboxes/stream`.

3. **App Router Routes & Split Caddy Cutover**:
   - Partition the dashboard into `/` (Builder), `/scratchpad` (Ideas & Raw split per ADR 0095), `/sandboxes`, and `/snapshots`, sharing global profile/filter/refresh/modal state via `DashboardProvider` and porting `launch-observer.js` to `useLaunchObserver`.
   - Deploy `dashboard/` to `/opt/sandbox-dashboard` via `modal-sandbox infra dashboard` (`sandboxes/sandbox/dashboard_deploy.py`), supporting staged subdomain verification (`--subdomain dashboard`) before apex cutover (`--cutover`).
   - Extend `render_wildcard_site()` in `sandboxes/sandbox/caddy_wildcard.py` with split apex routing: `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` proxy directly to Modal (`*.modal.run`), while all UI and `/api/*` traffic routes to `sandbox-dashboard-web:3000`.
   - Retire legacy `sandboxes/sandbox/static/index.html` and `sandboxes/sandbox/static/launch-observer.js` after live apex cutover verification, leaving FastAPI `GET /` as a minimal authenticated API status page.

## Consequences

- Python Control Plane routes, Zod schemas (`@dashboard/types`), and React views evolve together in single PRs.
- `modal-sandbox --remote` and `codexprofile` remain unaffected across staging and apex cutover.
- UI logic, Launch Request observation lifetimes, Basic Auth middleware, and SSE streaming are verified directly with Vitest alongside Python `pytest` suites.
