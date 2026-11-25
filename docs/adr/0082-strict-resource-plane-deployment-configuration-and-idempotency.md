# Strict Resource Plane Deployment Configuration and Deployment Idempotency

**Status**: Accepted (Amends [ADR 0081](0081-monorepo-architecture-for-execution-and-resource-planes.md)).

## Context

ADR 0081 established the two-subsystem monorepo architecture and standardized configuration variables under `RESOURCE_PLANE_*` while retaining transparent fallbacks to `DB_HOST_*` for backward compatibility.

As the automated VPS deployment pipeline (`modal-sandbox infra deploy` / `deploy-infra`) matured, retaining legacy `DB_HOST_SSH_*` deployment aliases introduced configuration ambiguity. Furthermore, automated deployments required deterministic idempotency: fresh VPS deployments needed reliable automatic external Docker network provisioning, and repeated deployments needed to safely converge container states without clobbering persistent volumes, existing TLS certificates, or manual credentials. Finally, users had to manually copy generated admin tokens from terminal logs into their local environment.

## Decision

1. **Remove Deployment Fallbacks**: Eliminate all legacy `DB_HOST_SSH_*` variable aliases (`DB_HOST_SSH_HOST`, `DB_HOST_SSH_USER`, `DB_HOST_SSH_PORT`, `DB_HOST_SSH_KEY`, `DB_HOST_REMOTE_DIR`) from `sandbox/infra_deploy.py`. Legacy variables are silently ignored, requiring `RESOURCE_PLANE_SSH_HOST` to be explicitly set. Standard operational defaults (`root`, `22`, `/opt/resource-plane`) are preserved. Runtime client fallbacks (`DB_HOST_DOMAIN`, `DB_HOST_ADMIN_TOKEN`) remain untouched in `sandbox/db_host_client.py` for sandbox backwards compatibility.
2. **Idempotent External Network Provisioning**: `resource-plane/deploy.sh` guarantees that the external Docker bridge network (`dbhost-network`) required by `docker-compose.prod.yml` is inspected and created if missing, ensuring clean execution on both fresh hosts and existing environments.
3. **Deterministic Credential Sync**: `deploy-infra` automatically queries the remote VPS over SSH to retrieve the generated `ADMIN_TOKEN` and updates the local `.env` with `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN`. Existing non-empty values are strictly preserved to ensure idempotency across multiple runs, with an opt-out `--no-sync-env` CLI flag.

## Consequences

- Configuration for automated infrastructure deployment is unambiguous and aligned with the canonical domain model.
- `deploy-infra` can be run repeatedly without breaking existing services, resetting databases, or overwriting custom local `.env` variables.
- Onboarding friction is reduced by automating the transfer of the generated admin token to the developer's local environment.
