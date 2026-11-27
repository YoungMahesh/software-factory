# ADR 0099: Standalone Dashboard Deployer and Staging Dashboard Removal

**Status**: Accepted (Amends [ADR 0098](0098-simplified-infra-cli-and-isolated-dashboard-deploys.md)).

We retire the staging **Sandbox Web Dashboard** stack (`/opt/sandbox-dashboard-staging`, `https://dashboard.<APPS_BASE_DOMAIN>`, `modal-sandbox infra dashboard --subdomain`, and the in-dashboard header deploy buttons) and introduce **Dashboard Deployer** (`dashboard-deployer/`), a standalone Next.js 16 + React 19 deployment console hosted on the VPS at `/opt/dashboard-deployer` (`https://deploy.<APPS_BASE_DOMAIN>`).

## Context

[ADR 0098](0098-simplified-infra-cli-and-isolated-dashboard-deploys.md) duplicated the full **Sandbox Web Dashboard** runtime into `/opt/sandbox-dashboard-staging` on `dashboard.<APPS_BASE_DOMAIN>` and placed opposite-target deploy buttons in `DashboardShell` so operators could trigger apex deployments without restarting the container handling the request. Maintaining an entire second staging copy of the dashboard solely to host a deploy trigger created unnecessary duplication and operational surface area when deployments always pull the latest `main` branch to the **App Base Domain**.

## Decisions

1. **Retire Staging Sandbox Web Dashboard**:
   - Remove `--subdomain`, `sandbox-dashboard-staging`, `/opt/sandbox-dashboard-staging`, and `"subdomain"` deploy targets from `sandboxes/sandbox/dashboard_deploy.py` and `sandboxes/sandbox/dashboard_self_deploy.py`.
   - Remove the header deploy buttons and `@dashboard/types` deploy schemas from `dashboard/`.
   - Automatically clean up any leftover `/opt/sandbox-dashboard-staging` Compose stack and `conf/apps/sandbox-dashboard.caddy` route when `modal-sandbox infra dashboard` or `modal-sandbox infra deployer` runs.

2. **Standalone `dashboard-deployer/` App**:
   - Add a dedicated top-level Next.js 16 + React 19 application (`dashboard-deployer/`, registered in root `pnpm-workspace.yaml`) with its own `Dockerfile`, `docker-compose.prod.yml`, and `deploy.sh`, protected by the same `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` HTTP Basic Auth middleware.
   - Add `modal-sandbox infra deployer` to sync `dashboard-deployer/` to `/opt/dashboard-deployer` (`dashboard-deployer-web:3000`) and expose it at `https://deploy.<APPS_BASE_DOMAIN>` via Caddy wildcard snippet `conf/apps/dashboard-deployer.caddy`.
   - Keep deployment execution inside the **Hosted Sandbox Control Plane** (`POST /api/dashboard/deploy` defaulting to `"apex"`, plus `GET /api/dashboard/deploy/{deploy_id}`), called via `dashboard-deployer/`'s server-side BFF proxy so the web container never holds VPS SSH keys or Docker socket access.

## Consequences

- `dashboard/` and `dashboard-deployer/` build, sync, and restart independently; deploying `main` to `https://<APPS_BASE_DOMAIN>` never interrupts the **Dashboard Deployer** UI, and vice versa.
- Operators have a single focused deployment surface at `https://deploy.<APPS_BASE_DOMAIN>` showing the live **Sandbox Web Dashboard** commit, Control Plane commit, confirmation prompt, and live deployment logs.
