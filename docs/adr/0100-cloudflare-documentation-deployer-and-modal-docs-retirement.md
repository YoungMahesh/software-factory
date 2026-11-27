# ADR 0100: Cloudflare Documentation Web App in Dashboard Deployer and Modal Docs Retirement

**Status**: Accepted (Supersedes [ADR 0062](0062-publish-documentation-as-modal-web-function.md); amends [ADR 0068](0068-migrate-documentation-generator-to-zensical.md) and [ADR 0099](0099-standalone-dashboard-deployer-and-staging-removal.md)).

We retire the Modal-hosted documentation app (`sandboxes/sandbox/docs.py`), standardize the **Documentation Web App** exclusively on Cloudflare Pages at `https://docs.<APPS_BASE_DOMAIN>`, and add an independent Cloudflare deployment trigger and live status viewer for it inside **Dashboard Deployer** (`dashboard-deployer/`), backed by a dedicated **Hosted Sandbox Control Plane** build-and-publish worker.

## Context

[ADR 0062](0062-publish-documentation-as-modal-web-function.md) introduced `sandboxes/sandbox/docs.py` (`modal-sandboxes-docs`) to build and serve documentation via `@modal.asgi_app()`, and [ADR 0068](0068-migrate-documentation-generator-to-zensical.md) migrated compilation to Zensical while keeping `sandboxes/scripts/deploy-docs.sh` for manual Cloudflare Pages deploys to `*.pages.dev`. Meanwhile, [ADR 0099](0099-standalone-dashboard-deployer-and-staging-removal.md) introduced **Dashboard Deployer** (`https://deploy.<APPS_BASE_DOMAIN>`) as a credential-free Next.js BFF proxy triggering **Hosted Sandbox Control Plane** deployments from GitHub `main`.

Maintaining two separate documentation hosting mechanisms (Modal ASGI plus Cloudflare Pages) created unnecessary duplication, while deploying documentation only from a local developer shell left operators without a one-click browser deployment and live commit status surface alongside **Sandbox Web Dashboard**.

## Decisions

1. **Retire Modal Documentation Hosting and Standardize `https://docs.<APPS_BASE_DOMAIN>`**:
   - Remove `sandboxes/sandbox/docs.py`, its Modal unit tests, and `DOCS_CUSTOM_DOMAIN` from active configuration and guides, retaining Zensical strict-build verification (`zensical build --strict`) and updating `sandboxes/scripts/deploy-docs.sh` for manual CLI fallback.
   - Standardize Cloudflare Pages (`CLOUDFLARE_PAGES_PROJECT`, defaulting to `modal-sandboxes-docs`, on `CLOUDFLARE_PAGES_BRANCH`, defaulting to `main`) served at `https://docs.<APPS_BASE_DOMAIN>` with no `DOCS_PUBLIC_URL` override and no `*.pages.dev` canonical surface.
   - Keep Cloudflare Pages custom-domain binding and the explicit DNS `CNAME` (`docs` → `<project>.pages.dev` overriding the VPS `*.<APPS_BASE_DOMAIN>` wildcard) as a one-time Cloudflare setup so deploys only require Pages upload credentials, while blocking `docs` and `deploy` as reserved **Hosted App** subdomains in `deploy-app`.

2. **Dedicated Hosted Sandbox Control Plane Worker (`run_docs_deploy` & `docs_deploy_image`)**:
   - Add dedicated **Hosted Sandbox Control Plane** endpoints (`POST /api/docs/deploy`, `GET /api/docs/deploy`, `GET /api/docs/deploy/{deploy_id}`) and independent `FactoryStateStore` persistence under `docs-deploys/` so **Sandbox Web Dashboard** and **Documentation Web App** deployments use separate single-flight locks, state records, and log streams.
   - Run the worker in a separate `docs_deploy_image` (with `zensical`, Node.js, and `wrangler`) on `run_docs_deploy` inside `sandboxes/sandbox/function.py`, keeping `fastapi_app`, `run_launch_request`, and `run_dashboard_deploy` slim while reusing Wrangler rather than re-implementing Cloudflare's Direct Upload API in Python.
   - Clone GitHub `main`, run `zensical build --strict`, write `/deploy-info.json` (`commit`, `commit_short`, `deployed_at`) into `site/`, and publish via `wrangler pages deploy` using `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` from **Hosted Sandbox Control Plane** secrets.

3. **Expand Dashboard Deployer (`dashboard-deployer/`)**:
   - Keep `dashboard-deployer/` free of GitHub, SSH, and Cloudflare secrets by proxying `/api/docs/deploy` and `/api/docs/deploy/[deployId]` to the **Hosted Sandbox Control Plane** and probing `https://docs.<APPS_BASE_DOMAIN>/deploy-info.json` in `/api/status`.
   - Render two independent stacked target sections in the UI (**Sandbox Web Dashboard** and **Documentation Web App**), each with its own confirmation-guarded deploy button, live commit status, and deployment log viewer.

## Considered Options

- **Execute `zensical` and `wrangler` inside the `/opt/dashboard-deployer` container**: Rejected because it would require Python/Zensical tooling plus GitHub and Cloudflare credentials on the VPS container, breaking [ADR 0099](0099-standalone-dashboard-deployer-and-staging-removal.md)'s credential-free BFF boundary.
- **Bundle `zensical`, Node.js, and `wrangler` into the shared Hosted Sandbox Control Plane image**: Rejected to avoid image bloat and slower builds for `fastapi_app`, `run_launch_request`, and `run_dashboard_deploy`.
- **Re-implement Cloudflare Pages Direct Upload in pure Python**: Rejected because `wrangler pages deploy` handles asset hashing, manifest deduplication, and deployment output consistently with `sandboxes/scripts/deploy-docs.sh`.
- **Automate Cloudflare DNS `CNAME` and custom-domain attachment on every deploy**: Rejected so deployment tokens remain scoped to Cloudflare Pages rather than requiring Zone DNS write permissions on every deploy.

## Consequences

- Operators deploy both **Sandbox Web Dashboard** and **Documentation Web App** independently from `https://deploy.<APPS_BASE_DOMAIN>` with live commit visibility (`https://<APPS_BASE_DOMAIN>/api/health` and `https://docs.<APPS_BASE_DOMAIN>/deploy-info.json`).
- **Hosted Sandbox Control Plane** deployment (`modal deploy sandboxes/sandbox/function.py`) requires `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and `APPS_BASE_DOMAIN` in `.env` (or environment) for **Dashboard Deployer** documentation deployments to succeed.
