# Host Sandbox Web Dashboard on App Base Domain via Caddy Reverse Proxy

**Status**: Accepted (Amends [ADR 0088](0088-wildcard-host-ingress-and-hosted-app-deployment.md))

We host the **Sandbox Web Dashboard** (`sandboxes/sandbox/function.py`) on the apex of the **App Base Domain** (`https://<APPS_BASE_DOMAIN>`) by configuring the VPS **Host Ingress Proxy** (`/opt/caddy/conf/sites/apps-wildcard.caddy`) to reverse-proxy apex traffic directly to the deployed Modal Control Plane origin URL (`*.modal.run`).

## Context

Under [ADR 0088](0088-wildcard-host-ingress-and-hosted-app-deployment.md), `/opt/caddy/conf/sites/apps-wildcard.caddy` obtained a single Cloudflare DNS-01 wildcard certificate for `<APPS_BASE_DOMAIN>, *.<APPS_BASE_DOMAIN>`, routed `<app>.<APPS_BASE_DOMAIN>` to **Hosted Apps**, and left the apex `<APPS_BASE_DOMAIN>` returning HTTP `404`. Meanwhile, the **Sandbox Web Dashboard** and Hosted Sandbox Control Plane API remained accessible only at Modal's auto-generated `*.modal.run` URL (`MODAL_SANDBOX_ENDPOINT_URL`).

Serving the **Sandbox Web Dashboard** at `https://<APPS_BASE_DOMAIN>` surfaced three architectural constraints:
1. **Modal Plan Lock-In on Native Custom Domains**: Unlike `docs.py` (`DOCS_CUSTOM_DOMAIN`), Modal's `@modal.asgi_app(custom_domains=[...])` requires a Team or Enterprise workspace plan rather than the free Starter plan, and splitting apex DNS away from the VPS would decouple the apex from `/opt/caddy`'s wildcard ingress stack.
2. **Self-Proxy Loop Hazard**: Once operators set `MODAL_SANDBOX_ENDPOINT_URL=https://<APPS_BASE_DOMAIN>` for `modal-sandbox --remote` and `codexprofile` status, Caddy cannot treat `MODAL_SANDBOX_ENDPOINT_URL` as its upstream target without looping onto itself.
3. **Caddy Site Block Ownership**: Because `apps-wildcard.caddy` already declares the `{base_domain}, *.{base_domain}` site block, placing the apex route in a separate `conf/sites/*.caddy` file causes a Caddy duplicate site-address error, while placing it under `conf/apps/*.caddy` risks slug collisions with **Hosted Apps**.

## Decisions

1. **Reverse-Proxy Apex of `APPS_BASE_DOMAIN` via `/opt/caddy` to Modal**:
   - Extend `render_wildcard_site()` in `sandboxes/sandbox/caddy_wildcard.py` to emit an inline `@sandbox_dashboard host <base_domain>` `handle` block inside `conf/sites/apps-wildcard.caddy` (preceding the `404` fallback and after `import /etc/caddy/apps/*.caddy`, which only matches subdomains).
   - Proxy all dashboard, API, and SSE routes (`/`, `/api/*`, `/launch`, `/snapshot`, `/health`, `/api/codex/profiles`) transparently with `header_up Host {upstream_hostport}` (matching Modal's edge SNI/routing expectations) and `flush_interval -1` (unbuffered SSE streaming), retaining Modal-side HTTP Basic Auth (`WEB_UI_USERNAME` / `WEB_UI_PASSWORD`) and scoped Bearer authentication per [ADR 0046](0046-retire-local-web-ui-and-enforce-basic-auth.md).

2. **Modal Origin Discovery, Self-Loop Validation, and `.env` Sync**:
   - Auto-discover the deployed Modal origin URL via `modal.Function.from_name("sandbox-control-plane", "fastapi_app").get_web_url()` using the active Modal profile, with an explicit override via `--dashboard-upstream` / `SANDBOX_DASHBOARD_UPSTREAM` in root `.env` (falling back to `MODAL_SANDBOX_ENDPOINT_URL` only when it does not point to `<APPS_BASE_DOMAIN>` or a subdomain).
   - Reject any configured upstream whose host matches `<APPS_BASE_DOMAIN>` or its subdomains to prevent proxy loops.
   - Extend `modal-sandbox infra caddy` with `--dashboard`, `--dashboard-upstream`, `--no-dashboard`, and `--no-sync-env`: `--wildcard` wires the apex route automatically when the Modal origin resolves (preserving any existing remote route if lookup is unavailable, or warning with `404` on pre-Modal VPS bootstraps unless `--dashboard` is explicit), and idempotently fills empty `MODAL_SANDBOX_ENDPOINT_URL` in root `.env` with `https://<APPS_BASE_DOMAIN>`.

3. **Keep Base Domain Configuration in Root `.env` and Out of Public Docs**:
   - Keep `APPS_BASE_DOMAIN`, `SANDBOX_DASHBOARD_UPSTREAM`, and `MODAL_SANDBOX_ENDPOINT_URL` exclusively in root **Factory Environment Configuration** (`.env.example` / `.env`) rather than duplicating them into `resource-plane/.env.example` or `/opt/resource-plane/.env`.
   - Scrub personal domains from tracked code, documentation, ADRs, and test fixtures, using generic domains such as `apps.example.com` and `db-host.example.com` across all tracked repository files.

## Considered Options

- **Modal Native `custom_domains` (`@modal.asgi_app(custom_domains=[...])`)**: Rejected because Modal custom domains require a paid Team/Enterprise plan and split apex DNS away from the VPS wildcard proxy.
- **Self-Host FastAPI Dashboard Container Directly on VPS**: Rejected because the control plane relies on `factory-state-v1` `modal.Volume`, `run_launch_request.spawn()`, and Modal secret injection established in [ADR 0046](0046-retire-local-web-ui-and-enforce-basic-auth.md) and [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md).
- **Route File Under `/opt/caddy/conf/apps/*.caddy`**: Rejected because `/opt/caddy/conf/apps/<slug>.caddy` is reserved for **Hosted Apps** and risks filename collisions.

## Consequences

- Operators access the **Sandbox Web Dashboard** at `https://<APPS_BASE_DOMAIN>` using the existing VPS wildcard TLS certificate without paying for Modal Team custom domains or modifying Modal deployment architecture.
- `caddy-store` (`conf/sites/apps-wildcard.caddy`) captures and restores the apex dashboard route alongside wildcard TLS declarations.
- **App Base Domain** in `GLOSSARY.md` covers both the apex **Sandbox Web Dashboard** and `<app>.<APPS_BASE_DOMAIN>` **Hosted Apps**.
