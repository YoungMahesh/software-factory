# Sandbox Web Dashboard

Next.js 16 + React 19 web dashboard and same-origin Basic-Auth BFF proxy for the Hosted Sandbox Control Plane ([sandboxes/sandbox/web.py](../sandboxes/sandbox/web.py) and [sandboxes/sandbox/function.py](../sandboxes/sandbox/function.py)).

## Pages & BFF Routes

- **`/` (Builder)**: Prompt-first Builder Workspace launcher with Prime Sandbox reuse, Repository Catalog picker (`GET /api/github/repos`, `POST /api/github/repos/refresh`), model/provider selection, and opt-in `web_app` mode.
- **`/sandboxes` (Sandboxes)**: Active sandbox discovery, Prime Sandbox badges, live 24-hour lifespan progress bars, per-sandbox accrued Modal costs (`GET /api/sandboxes/costs`), **T3Code Pairing Links** modal (`GET/POST /api/sandboxes/{id}/t3-links`), SSE streaming launch modal (`POST /api/sandboxes/stream`), terminate, and snapshot capture.
- **`/snapshots` (Snapshots)**: Persistent snapshot registry listing, snapshot launch modal, and record deletion.
- **`/scratchpad` (Scratchpad)**: **Ideas** (`config/scratchpad/`) with AI-assisted refinement (`POST /api/scratchpad/suggest`) and **Raw** (`config/raw/`) verbatim notes indexed by the Scratchpad Catalog.
- **API Proxy & Health**: `/api/health` provides an unauthenticated container health check (including `apps_base_domain` and `dashboard_commit` metadata for the UI); `/api/[...path]` forwards `GET`, `POST`, and `DELETE` requests to `SANDBOX_CONTROL_PLANE_URL` with Basic Auth and unbuffered SSE pass-through. Next.js middleware enforces Basic Auth against `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` (returning `500` in production if unset).
- **Standalone Deployment Console**: Production deploys from GitHub `main` to `https://<APPS_BASE_DOMAIN>` can be triggered from the standalone **Dashboard Deployer** app ([dashboard-deployer/README.md](../dashboard-deployer/README.md), hosted at `https://deploy.<APPS_BASE_DOMAIN>`).

## Local Development

Install dependencies from the monorepo root:

```bash
pnpm install
```

Ensure `SANDBOX_CONTROL_PLANE_URL`, `WEB_UI_USERNAME`, and `WEB_UI_PASSWORD` are configured in `dashboard/apps/web/.env` (see [dashboard/.env.example](.env.example)) or the environment:

```bash
pnpm --dir dashboard dev
```

Run tests, typechecks, and production build:

```bash
pnpm --dir dashboard test
pnpm --dir dashboard typecheck
pnpm --dir dashboard build
```

## Production Deployment

Deploy the production **Sandbox Web Dashboard** and standalone **Dashboard Deployer** from `.env` configuration (`RESOURCE_PLANE_SSH_*`, `APPS_BASE_DOMAIN`, Cloudflare DNS-01 token):

```bash
# Build and deploy production dashboard to /opt/sandbox-dashboard (https://<APPS_BASE_DOMAIN>)
modal-sandbox infra dashboard

# Build and deploy standalone Dashboard Deployer to /opt/dashboard-deployer (https://deploy.<APPS_BASE_DOMAIN>)
modal-sandbox infra deployer
```

Apex deployment wires `/opt/caddy/conf/sites/apps-wildcard.caddy` to route `https://<APPS_BASE_DOMAIN>` to `sandbox-dashboard-web:3000` while forwarding `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` directly to the Hosted Sandbox Control Plane origin, and cleans up any retired `/opt/sandbox-dashboard-staging` stack or route. Each deploy bakes `NEXT_PUBLIC_DASHBOARD_COMMIT` so the UI displays its deployed commit beside the Hosted Sandbox Control Plane commit badge.
