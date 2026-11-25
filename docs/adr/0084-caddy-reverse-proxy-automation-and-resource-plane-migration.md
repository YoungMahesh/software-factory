# Caddy Reverse-Proxy Automation and Resource Plane Production Migration

**Status**: Accepted (Amends [ADR 0081](0081-monorepo-architecture-for-execution-and-resource-planes.md) Section 4 and [ADR 0082](0082-strict-resource-plane-deployment-configuration-and-idempotency.md)).

## Context

ADR 0081 established the two-subsystem monorepo architecture partitioning Software Factory into `sandboxes/` (Execution Plane) and `resource-plane/` (Resource Plane). In ADR 0081 Section 4, automated reverse-proxying was deferred in favor of direct port binding and manual host proxy management.

Prior to this decision:
1. **Unmanaged Standalone VPS Checkout (`/root/db-host`)**: The remote VPS hosted a manually cloned standalone Git repository at `/root/db-host` with active PostgreSQL databases, SeaweedFS volumes, and TLS certificates stored in `/root/db-host/.data/`. This created architectural drift from our monorepo standard destination (`/opt/resource-plane`).
2. **Manual Reverse-Proxy Maintenance**: The host VPS runs a centralized Caddy reverse-proxy in `/root/infra-stack/v1/caddy/` (`cCaddy`). Configuring ingress for the Resource Plane web console and MCP endpoint required manual SSH access, manual edits to `v1/caddy/conf/Caddyfile`, manual Docker network attachment, and manual container reloads.
3. **Risk of Data Loss / Split-Brain**: Blindly deploying from the monorepo to `/opt/resource-plane` would generate fresh credentials and an empty data directory, disconnecting existing tenant databases and causing Docker container name collisions with the old checkout.

## Decision

1. **Production State Migration to `/opt/resource-plane`**:
   - Safely migrated all persistent state (`.env`, `.data/postgres`, `.data/seaweedfs`, `.data/certs`) from `/root/db-host` to `/opt/resource-plane` with preserved credentials, database clusters, and permissions.
   - Deployed the production Docker Compose stack via the canonical pipeline (`modal-sandbox infra deploy`).
   - Archived the legacy `/root/db-host` directory to `/root/db-host.migrated` to eliminate configuration drift and prevent split-brain execution.

2. **Caddy Reverse-Proxy Automation Module (`sandbox.caddy_deploy`)**:
   - Introduced a dedicated automation module in `sandboxes/sandbox/caddy_deploy.py` (exposed via `modal-sandbox infra caddy` and standalone `setup-caddy`).
   - **Automated Health & Status Probing**: Verifies the presence and running state of the Caddy container on the remote VPS.
   - **Idempotent Network Attachment**: Guarantees that Caddy is connected to the Resource Plane Docker bridge network (`dbhost-network`).
   - **Deterministic Route Configuration**: Idempotently reads the remote `Caddyfile`, parses existing site blocks, and appends reverse-proxy configurations for the target domain (and optional S3 domain) if missing:
     ```caddyfile
     {domain} {
         reverse_proxy db-host-web:3000
     }
     ```
   - **Zero-Downtime Reload**: Automates `caddy reload` execution inside the container with immediate validation.

3. **Subcommand Dispatch & CLI Ergonomics**:
   - Added `caddy` subcommand under `modal-sandbox infra` (`modal-sandbox infra caddy --domain <domain>`), providing turnkey reverse-proxy configuration alongside `modal-sandbox infra deploy`.

## Consequences

- The remote VPS runs exclusively from the canonical `/opt/resource-plane` location managed directly by the `software-factory` monorepo tooling.
- Zero data loss was achieved: all existing PostgreSQL databases (`neon_control_plane`, `demo_db`, `demo_prod_db`, `raatu`, etc.) and SeaweedFS S3 buckets remain active and intact.
- Reverse-proxy configuration for public domains and ACME TLS termination is automated and reproducible through code.
