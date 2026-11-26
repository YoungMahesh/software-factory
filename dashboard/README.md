# Sandbox Dashboard

Next.js 16 + React 19 web dashboard and same-origin BFF proxy for the Modal Sandbox Control Plane (`sandboxes/sandbox/web.py` and `sandboxes/sandbox/function.py`).

## Local Development

Install dependencies from the monorepo root (or inside `dashboard/`):

```bash
pnpm install
cd dashboard/apps/web
```

Ensure `SANDBOX_CONTROL_PLANE_URL`, `WEB_UI_USERNAME`, and `WEB_UI_PASSWORD` are configured in `.env` (or root `.env`):

```bash
pnpm --filter @dashboard/web dev
```

Run tests, typechecks, and production build:

```bash
pnpm --dir dashboard test
pnpm --dir dashboard typecheck
pnpm --dir dashboard build
```

## Production Deployment

Deploy to `/opt/sandbox-dashboard` on the VPS and optionally expose on a staging subdomain or cut over the apex domain:

```bash
modal-sandbox infra dashboard --subdomain dashboard
modal-sandbox infra dashboard --cutover
```
