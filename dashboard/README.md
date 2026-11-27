# Sandbox Web Dashboard

Next.js 16 + React 19 web dashboard and same-origin Basic-Auth BFF proxy for the Modal Sandbox Control Plane ([sandboxes/sandbox/web.py](../sandboxes/sandbox/web.py) and [sandboxes/sandbox/function.py](../sandboxes/sandbox/function.py)).

## Pages & BFF Routes

- **`/` (Builder)**: Prompt-first Factory App launcher with Prime Sandbox reuse, GitHub Repository Catalog picker (`GET /api/github/repos`, `POST /api/github/repos/refresh`), model/provider selection, and opt-in `web_app` mode.
- **`/sandboxes` (Sandboxes)**: Active sandbox discovery, Prime Sandbox badges, live 24-hour lifespan progress bars, per-sandbox accrued Modal costs (`GET /api/sandboxes/costs`), **T3Code Pairing Links** modal (`GET/POST /api/sandboxes/{id}/t3-links`), SSE streaming launch modal (`POST /api/sandboxes/stream`), terminate, and snapshot capture.
- **`/snapshots` (Snapshots)**: Persistent snapshot registry listing, snapshot launch modal, and record deletion.
- **`/scratchpad` (Scratchpad)**: **Ideas** (`config/scratchpad/`) with AI-assisted refinement (`POST /api/scratchpad/suggest`) and **Raw** (`config/raw/`) verbatim notes behind a persisted cache.
- **API Proxy & Health**: `/api/health` provides an unauthenticated container health check (including `apps_base_domain` and `dashboard_commit` metadata for the UI); `/api/[...path]` forwards `GET`, `POST`, and `DELETE` requests to `SANDBOX_CONTROL_PLANE_URL` with Basic Auth and unbuffered SSE pass-through. Next.js middleware enforces Basic Auth against `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` (returning `500` in production if unset).
- **UI Self-Deploy Header Action**: Each hosted dashboard shows an opposite-target deploy button in its header (`Deploy dashboard.<APPS_BASE_DOMAIN>` when browsing the apex, or `Deploy <APPS_BASE_DOMAIN>` when browsing the staging subdomain) backed by `POST /api/dashboard/deploy` on the Modal Control Plane. Triggering it prompts for confirmation, clones `main` asynchronously inside Modal, rebuilds only that isolated `dashboard/` VPS stack and Caddy route (without redeploying Modal functions), and polls until completion.

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

Deploy isolated production and staging dashboard stacks from `.env` configuration (`RESOURCE_PLANE_SSH_*`, `APPS_BASE_DOMAIN`, Cloudflare DNS-01 token):

```bash
# Deploy isolated staging build to /opt/sandbox-dashboard-staging (https://dashboard.<APPS_BASE_DOMAIN>)
modal-sandbox infra dashboard --subdomain

# Build and deploy production dashboard to /opt/sandbox-dashboard (https://<APPS_BASE_DOMAIN>)
modal-sandbox infra dashboard
```

Apex deployment wires `/opt/caddy/conf/sites/apps-wildcard.caddy` to route `https://<APPS_BASE_DOMAIN>` to `sandbox-dashboard-web:3000` while forwarding `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` directly to the Modal Control Plane origin, leaving `/opt/sandbox-dashboard-staging` untouched. Staging (`--subdomain`) builds `sandbox-dashboard-staging-web:3000` and routes `https://dashboard.<APPS_BASE_DOMAIN>` without modifying the apex stack. Each deploy bakes `NEXT_PUBLIC_DASHBOARD_COMMIT` so the UI displays its deployed commit beside the Control Plane commit badge.
