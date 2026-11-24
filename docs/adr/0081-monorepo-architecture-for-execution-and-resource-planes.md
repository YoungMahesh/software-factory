# Monorepo Architecture for Execution Plane (Modal Sandboxes) and Resource Plane (VPS Persistence)

**Status**: Accepted (Amends [ADR 0078](0078-create-db-cli-for-db-host-postgres-connections.md), [ADR 0079](0079-create-s3-cli-for-db-host-s3-object-storage.md), and [ADR 0080](0080-consolidate-control-plane-and-configuration-seams.md)).

## Context

The software factory previously relied on an external, separately hosted control plane repository (`db-host`) to provision isolated PostgreSQL databases and SeaweedFS S3 object storage buckets via MCP tools (`POST /api/mcp`).

Preparing `software-factory` for public open-source distribution revealed three critical architectural challenges:
1. **Incomplete Open-Source Distribution**: Open-sourcing `software-factory` without the persistence control plane codebase would force users to depend on an external, proprietary, or missing repository, breaking the zero-friction onboarding goal.
2. **Domain Misnomer (`db-host`)**: The name `db-host` is a historical misnomer because the platform provisions both relational databases (PostgreSQL 16) and object storage (SeaweedFS S3), creating confusion across client libraries, CLI flags, and environment variables.
3. **Polyglot Monorepo vs. Lifecycle Coupling**: While users need a self-contained repository, the two systems have fundamentally different runtimes and operational lifecycles:
   - **Execution Plane (Modal Sandboxes)**: Ephemeral, serverless Linux containers and VMs (`modal.Sandbox`) written in Python 3.12+, spinning up and terminating dynamically.
   - **Resource Plane (VPS Persistence)**: Persistent, long-running stateful services (PostgreSQL clusters, SeaweedFS volumes, Next.js web console, Drizzle ORM) written in TypeScript/React and hosted on a persistent Docker host (VPS).

## Decision

We unify the software factory into a two-subsystem monorepo with clean architectural boundaries, automated deployment, and aligned domain language:

### 1. Two-Subsystem Monorepo Topology
The repository is partitioned into two explicit top-level subsystems sharing a single root repository:
- **`sandboxes/` (Execution Plane)**: The Python Modal sandbox engine, CLI (`modal-sandbox`, `create-db`, `create-s3`), test suites, and agent harnesses.
- **`resource-plane/` (Resource Plane)**: The TypeScript Next.js web console, Docker Compose service definitions, PostgreSQL/SeaweedFS engines, TLS certificate authority generator, and MCP server (`POST /api/mcp`).

### 2. Canonical Domain Model Rebranding
- Formalize **Resource Plane** as the canonical domain concept in `GLOSSARY.md` for the persistence control plane subsystem (`resource-plane/`).
- Aliased `DbHostClient` to `ResourcePlaneClient` across client modules.
- Standardize configuration variables to `RESOURCE_PLANE_*` (`RESOURCE_PLANE_DOMAIN`, `RESOURCE_PLANE_ADMIN_TOKEN`, `RESOURCE_PLANE_SSH_*`), retaining transparent fallbacks to `DB_HOST_*` for backward compatibility.

### 3. Strict Deployment vs. Runtime Transport Boundary
We enforce a strict separation of concerns between infrastructure provisioning and runtime sandbox access:
- **Infrastructure Deployment (SSH)**: Remote provisioning uses VPS SSH credentials configured in the host `.env` (`RESOURCE_PLANE_SSH_HOST`, `RESOURCE_PLANE_SSH_USER`, `RESOURCE_PLANE_SSH_KEY`). A dedicated CLI command (`modal-sandbox infra deploy`) uses the system's native `ssh` and `rsync` via Python `subprocess` (honoring SSH agents and `~/.ssh/config` without third-party Python SSH libraries) to verify Docker and run `deploy.sh` remotely.
- **Runtime Sandbox Access (HTTPS/MCP & Direct TLS)**: Running sandboxes never receive or use SSH keys to the VPS. They interact exclusively with the public Resource Plane MCP endpoint (`POST /api/mcp`) using `RESOURCE_PLANE_ADMIN_TOKEN` and connect directly to PostgreSQL (`port 54320` over TLS with cached Root CA) and SeaweedFS S3 (`port 8333`).

### 4. Dual-Target Development & Deferred Ingress
- Support a zero-cost local Docker Compose mode (`docker compose up` inside `resource-plane/`) for local evaluation without cloud or VPS expenses, alongside the production VPS deployment pipeline.
- Automated reverse-proxying (e.g. Caddy Let's Encrypt integration) is deferred; direct port binding and existing host proxy configurations are used in the interim.

### 5. Single-Root Developer Ergonomics & Line Budget Ratchet
- Root `pyproject.toml` references `where = ["sandboxes"]`, enabling contributors to install all Python tooling directly with `pip install -e .` from the repository root.
- Root `pnpm-workspace.yaml` references `resource-plane`, enabling TypeScript installation from the repository root. The root and Resource Plane lockfiles support frozen installs from both locations. When changing Resource Plane dependencies, update both lockfiles so the monorepo and standalone Docker build resolve the same dependencies.
- `tests/test_standards.py` scopes Python file line-budget enforcement (<= 500 lines) to `sandboxes/`, strictly excluding `resource-plane/` and `node_modules`.

## Consequences

- **Self-Contained Repository**: Open-source users can clone a single repository and have both cloud execution sandboxes and stateful persistence infrastructure ready to deploy.
- **Zero-Trust Security**: Ephemeral sandboxes remain strictly isolated from the persistent VPS infrastructure host.
- **Preserved Standards**: Python modules remain strictly under the universal 500-line limit without polyglot noise.
