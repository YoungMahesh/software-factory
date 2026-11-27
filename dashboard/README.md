# Sandbox Web Dashboard

Next.js 16 + React 19 web dashboard and same-origin Basic-Auth BFF proxy for the Modal Sandbox Control Plane ([sandboxes/sandbox/web.py](../sandboxes/sandbox/web.py) and [sandboxes/sandbox/function.py](../sandboxes/sandbox/function.py)).

## Pages & BFF Routes

- **`/` (Builder)**: Prompt-first Factory App launcher with Prime Sandbox reuse, GitHub Repository Catalog picker (`GET /api/github/repos`, `POST /api/github/repos/refresh`), model/provider selection, and opt-in `web_app` mode.
- **`/sandboxes` (Sandboxes)**: Active sandbox discovery, Prime Sandbox badges, live 24-hour lifespan progress bars, per-sandbox accrued Modal costs (`GET /api/sandboxes/costs`), SSE streaming launch modal (`POST /api/sandboxes/stream`), terminate, and snapshot capture.
- **`/snapshots` (Snapshots)**: Persistent snapshot registry listing, snapshot launch modal, and record deletion.
- **`/scratchpad` (Scratchpad)**: **Ideas** (`config/scratchpad/`) with AI-assisted refinement (`POST /api/scratchpad/suggest`) and **Raw** (`config/raw/`) verbatim notes behind a persisted cache.
- **API Proxy & Health**: `/api/health` provides an unauthenticated container health check; `/api/[...path]` forwards `GET`, `POST`, and `DELETE` requests to `SANDBOX_CONTROL_PLANE_URL` with Basic Auth and unbuffered SSE pass-through. Next.js middleware enforces Basic Auth against `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` (returning `500` in production if unset).

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

Deploy to `/opt/sandbox-dashboard` on the VPS (with SSH/Docker preflight via `--check-only`), stage on a preview subdomain, or cut over the apex domain (and optionally `--sync` `/opt/caddy` to Central Config Store):

```bash
modal-sandbox infra dashboard --check-only
modal-sandbox infra dashboard --subdomain dashboard
modal-sandbox infra dashboard --cutover --sync
```

When `--cutover` runs, Caddy at `/opt/caddy/conf/sites/apps-wildcard.caddy` routes `https://<APPS_BASE_DOMAIN>` to `sandbox-dashboard-web:3000` while forwarding `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` directly to the Modal Control Plane origin.
