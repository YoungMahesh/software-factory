# Dashboard Deployer

Standalone Next.js 16 + React 19 deployment console for independently triggering and monitoring GitHub `main` deployments of:

- **Sandbox Web Dashboard** (`dashboard/`) to the **App Base Domain** (`https://<APPS_BASE_DOMAIN>`)
- **Documentation Web App** (`docs/` built with Zensical) to Cloudflare Pages at `https://docs.<APPS_BASE_DOMAIN>`

## Routes & BFF

- **`/`**: Single-page deployment console with independent **Sandbox Web Dashboard** and **Documentation Web App** stack cards, live commit probes, **Hosted Sandbox Control Plane** commit badge, confirmation-guarded deploy buttons, `2.5s` status polling, and deployment log viewers.
- **`/api/health`**: Unauthenticated container health endpoint (`status`, `apps_base_domain`, `deployer_commit`).
- **`/api/status`**: Authenticated status endpoint aggregating Hosted Sandbox Control Plane `/api/version`, `/api/dashboard/deploy`, `/api/docs/deploy`, live `https://<APPS_BASE_DOMAIN>/api/health`, and live `https://docs.<APPS_BASE_DOMAIN>/deploy-info.json`.
- **`/api/deploy`** (`POST`) and **`/api/deploy/[deployId]`** (`GET`): Authenticated BFF proxies to `POST /api/dashboard/deploy` and `GET /api/dashboard/deploy/{deploy_id}` on `SANDBOX_CONTROL_PLANE_URL`.
- **`/api/docs/deploy`** (`POST`) and **`/api/docs/deploy/[deployId]`** (`GET`): Authenticated BFF proxies to `POST /api/docs/deploy` and `GET /api/docs/deploy/{deploy_id}` on `SANDBOX_CONTROL_PLANE_URL`.

## Local Development

Install workspace dependencies from the repository root:

```bash
pnpm install
```

Configure `SANDBOX_CONTROL_PLANE_URL`, `APPS_BASE_DOMAIN`, `WEB_UI_USERNAME`, and `WEB_UI_PASSWORD` in `dashboard-deployer/.env` (see [dashboard-deployer/.env.example](.env.example)) or the root `.env`:

```bash
pnpm --dir dashboard-deployer dev
```

Run tests, typechecks, lint, and production build:

```bash
pnpm --dir dashboard-deployer test
pnpm --dir dashboard-deployer typecheck
pnpm --dir dashboard-deployer lint
pnpm --dir dashboard-deployer build
```

## Production Deployment

Deploy to `/opt/dashboard-deployer` on the VPS (`https://deploy.<APPS_BASE_DOMAIN>`):

```bash
modal-sandbox infra deployer
```
