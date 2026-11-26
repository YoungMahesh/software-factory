# Wildcard Host Ingress and Hosted App Deployment

**Status**: Accepted (Amends [ADR 0085](0085-host-ingress-proxy-in-opt-caddy.md) and [ADR 0087](0087-app-template-and-scaffolder-integration.md)).

## Context

[ADR 0085](0085-host-ingress-proxy-in-opt-caddy.md) standardized `/opt/caddy` using the upstream `caddy:2-alpine` image and per-domain site files in `/opt/caddy/conf/sites/*.caddy`, while [ADR 0087](0087-app-template-and-scaffolder-integration.md) integrated `app-template/` and `create-app` (where `--launch` provisions an ephemeral Modal Sandbox).

Deploying scaffolded applications live to the internet on the Resource Plane VPS exposed four gaps:
1. **Per-Domain ACME Churn**: Separate `<app>.<base-domain>` site blocks in `sites/*.caddy` trigger individual HTTP-01 Let's Encrypt certificate requests per app, creating issuance latency and rate-limit risk.
2. **Missing DNS-01 Wildcard Support**: Standard `caddy:2-alpine` lacks DNS provider modules required by Let's Encrypt for wildcard certificates (`*.<base-domain>`).
3. **Secret Isolation in `caddy-store`**: [ADR 0086](0086-host-ingress-store-for-opt-caddy.md) prohibits storing credentials inside `/opt/caddy/conf/` because `caddy-store` mirrors `conf/` as plaintext in GitHub.
4. **No Production Runtime or Deploy Pipeline for `app-template/`**: `app-template/` lacked a production `Dockerfile`, `docker-compose.yml`, standalone Next.js build configuration, and a host-side CLI to deploy apps to `/root/<repo-name>` with production URLs and TLS CA certs.

## Decision

1. **App Base Domain (`APPS_BASE_DOMAIN`)**:
   - Introduce `APPS_BASE_DOMAIN` in `.env` (e.g., `apps.example.com`), kept independent from `RESOURCE_PLANE_DOMAIN`.
   - Each **Hosted App** defaults to `<sanitized-repo-name>.<APPS_BASE_DOMAIN>` with `--subdomain <label>` override, idempotent redeploys for the same app, and collision rejection across distinct apps.
   - The apex `<APPS_BASE_DOMAIN>` stays minimal/reserved under the wildcard block unless explicitly routed.

2. **Cloudflare DNS-01 Wildcard Certificate & `/opt/caddy/.env` Secret Isolation**:
   - Build `/opt/caddy` from `resource-plane/caddy/Dockerfile` (`xcaddy` with `github.com/caddy-dns/cloudflare`) so first-time bootstrap—and idempotent in-place upgrades of an existing `/opt/caddy`—can issue and renew a single wildcard Let's Encrypt certificate for `<APPS_BASE_DOMAIN>` and `*.<APPS_BASE_DOMAIN>`.
   - Configure `CLOUDFLARE_DNS_API_TOKEN` in root `.env` (falling back to `CLOUDFLARE_API_TOKEN`) and write it exclusively to `/opt/caddy/.env` (`0600`) outside `/opt/caddy/conf/`, referencing `{env.CLOUDFLARE_DNS_API_TOKEN}` in Caddyfile so `caddy-store` remains secret-free.

3. **Wildcard Subdomain Routing (`conf/apps/*.caddy`)**:
   - Generate a wildcard site block in `/opt/caddy/conf/sites/apps-wildcard.caddy` that owns the single wildcard TLS certificate and imports `/etc/caddy/apps/*.caddy` host-matcher `handle` snippets (`@<app> host <subdomain>.<base-domain>`).
   - Adding, updating, or removing a Hosted App modifies only `/opt/caddy/conf/apps/<app>.caddy` and reloads Caddy with zero new Let's Encrypt calls.

4. **Containerized Hosted Apps at `/root/<repo-name>` on `dbhost-network`**:
   - Add Next.js `output: "standalone"`, `Dockerfile`, and `docker-compose.yml` to `app-template/`, joining external `dbhost-network` with unique `${APP_CONTAINER_NAME}` names so every Hosted App listens internally on port `3000` without host port conflicts.
   - During deployment, write remote `/root/<repo-name>/.env` with `NODE_ENV=production`, `NEXT_PUBLIC_APP_URL=https://<domain>`, and `EXPO_PUBLIC_API_URL=https://<domain>` (passed into the Docker build without altering local dev `.env`), stage Resource Plane `ca.crt` at `/root/<repo-name>/.certs/ca.crt` when `RESOURCE_PLANE_DOMAIN` is set, and run `drizzle-kit migrate` when SQL migrations exist (`--skip-migrate` to opt out).

5. **Host-Only Deployment CLI (`deploy-app` & `create-app --deploy`)**:
   - Provide `deploy-app` / `modal-sandbox deploy-app` (plus `create-app --deploy` and teardown `down`), leaving `create-app --launch` strictly for Modal Sandboxes.
   - Execute strictly from the host over SSH (`RESOURCE_PLANE_SSH_KEY`) per [ADR 0081](0081-monorepo-architecture-for-execution-and-resource-planes.md) and [ADR 0083](0083-mandatory-resource-plane-ssh-key-and-secrets-directory.md), supporting both local directory `tar` sync and `--repo <name>` GitHub + `env-store` deployment for sandbox-developed apps.

## Considered Options

- **Per-App HTTP-01 Site Blocks (`conf/sites/*.caddy`)**: Rejected because every new app triggers Let's Encrypt issuance and risks rate-limit exhaustion.
- **Cloudflare Origin CA Static Certificate**: Rejected because it binds TLS validation to Cloudflare's proxy mode rather than standard publicly trusted Let's Encrypt certificates in Caddy.
- **Bare-Metal Node/PM2 with Host Port Allocation**: Rejected because host port bookkeeping and shared Node runtime state drift across co-located apps compared to isolated `dbhost-network` containers.
- **In-Sandbox VPS Deployment**: Rejected because exposing `RESOURCE_PLANE_SSH_KEY` inside ephemeral Modal Sandboxes violates [ADR 0081](0081-monorepo-architecture-for-execution-and-resource-planes.md) and [ADR 0083](0083-mandatory-resource-plane-ssh-key-and-secrets-directory.md).

## Consequences

- Fresh VPS setups obtain a single wildcard certificate once via `modal-sandbox infra caddy --bootstrap`, and subsequent `deploy-app` or `create-app --deploy` runs publish apps at `https://<repo-name>.<APPS_BASE_DOMAIN>` without Let's Encrypt round-trips.
- Existing `/opt/caddy` deployments upgrade in place without losing `caddy_data` certificates or existing `sites/*.caddy` routes, and `caddy-store` retains zero plaintext secrets.
