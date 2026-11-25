# Host Ingress Proxy Standardization in `/opt/caddy`

**Status**: Accepted (Amends [ADR 0084](0084-caddy-reverse-proxy-automation-and-resource-plane-migration.md)).

## Context

[ADR 0084](0084-caddy-reverse-proxy-automation-and-resource-plane-migration.md) moved the Resource Plane deployment onto `/opt/resource-plane` and introduced `sandbox.caddy_deploy` (`modal-sandbox infra caddy`), but kept the reverse-proxy tied to a VPS-specific legacy installation at `/root/infra-stack/v1/caddy` (`cCaddy`) using monolithic inline edits to `Caddyfile`.

That left three architectural gaps:
1. **Host-Specific Coupling**: Fresh VPS deployments failed because `/root/infra-stack/v1/caddy` and `cCaddy` only existed on the original host.
2. **No Fresh-Host Provisioning**: `caddy_deploy.py` probed for an existing container instead of provisioning a canonical stack when bootstrapping a clean VPS.
3. **Coarse `Caddyfile` Mutation**: Appending site blocks to a shared flat `Caddyfile` made idempotent updates (e.g., changing `--upstream` or `--s3-domain`) fragile when co-located host applications shared the same proxy.

## Decision

1. **Sibling `/opt/caddy` Host Ingress Proxy**:
   - Standardize the **Host Ingress Proxy** as a standalone sibling stack at `/opt/caddy` (container name `caddy`) alongside `/opt/resource-plane`.
   - Keep it separate from `/opt/resource-plane` because only one proxy can bind ports `80`/`443` per VPS, and Resource Plane redeployments or `docker compose down` must never drop ACME certificates (`caddy_data`) or disrupt co-located host applications.

2. **Monorepo Placement under `resource-plane/caddy/`**:
   - Place the server Compose stack (`docker-compose.yml`), base `conf/Caddyfile`, and `conf/sites/` layout in `resource-plane/caddy/` since reverse-proxy runtime definitions belong to the Resource Plane VPS infrastructure rather than Modal Sandboxes.
   - Exclude `caddy/` when `infra_deploy.py` syncs `/opt/resource-plane` (`--exclude=caddy`) so `/opt/resource-plane` and `/opt/caddy` stay cleanly separated on the target VPS.

3. **Modular `sites/*.caddy` Routing & Validation**:
   - `/opt/caddy/conf/Caddyfile` holds only global options and `import /etc/caddy/sites/*.caddy`.
   - `modal-sandbox infra caddy` idempotently manages `/opt/caddy/conf/sites/resource-plane.caddy`, validates the active configuration via `caddy validate` (rolling back on syntax error), and skips `caddy reload` when unchanged.

4. **Strict Configuration & Explicit `--bootstrap`**:
   - Remove `--caddy-dir` and `--caddyfile` CLI flags and introduce zero `.env` path overrides; `/opt/caddy` is strictly canonical.
   - Fresh VPSs require an explicit `--bootstrap` flag (with optional `--email`) to guard against silent port `80`/`443` collisions on hosts running another proxy.
   - One-time migration from legacy `/root/infra-stack/v1/caddy` (`cCaddy`) is performed operationally—preserving existing site routes, `caddy_data`/`caddy_config` volumes, and all attached Docker networks—without embedding private legacy paths into permanent CLI code.

## Consequences

- Fresh VPSs can be provisioned cleanly end-to-end with `modal-sandbox infra deploy` followed by `modal-sandbox infra caddy --bootstrap --domain <domain>`.
- Existing multi-app hosts retain zero-downtime co-located routing via independent `/opt/caddy/conf/sites/*.caddy` files and preserved Docker networks.
- `sandbox.caddy_deploy` remains clean, deterministic, and free of host-specific legacy overrides.
