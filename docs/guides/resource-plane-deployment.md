# Resource Plane VPS Deployment Guide

This guide walks through deploying the **Resource Plane** (PostgreSQL 16, SeaweedFS S3 object storage, and Next.js management console) to a dedicated Linux VPS or local Docker environment.

---

## 1. Automated VPS Deployment (`modal-sandbox infra deploy`)

Software Factory includes a turnkey infrastructure deployment command:

```bash
modal-sandbox infra deploy
```

The deployment automation operates entirely over SSH using native `subprocess` and `tar`, verifying remote requirements, synchronizing the `resource-plane/` directory to canonical `/opt/resource-plane`, and executing the production startup script remotely.

### Prerequisites

1. **Linux VPS**: A clean or existing VPS running Debian 12+ or Ubuntu 22.04+ (minimum 2 CPU cores, 4 GB RAM recommended).
2. **Docker & Docker Compose**: Docker daemon installed and running (`docker compose` v2 available).
3. **SSH Access**: Public key authentication enabled for a privileged user (`root` or user with passwordless Docker permissions).

### Environment Configuration

Add your VPS connection details to your local `.env` file:

```env
# ------------------------------------------------------------------------------
# Resource Plane VPS Deployment Automation
# ------------------------------------------------------------------------------
RESOURCE_PLANE_SSH_HOST=203.0.113.10
RESOURCE_PLANE_SSH_USER=root
RESOURCE_PLANE_SSH_PORT=22
RESOURCE_PLANE_SSH_KEY=.secrets/resource_plane_ssh
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `RESOURCE_PLANE_SSH_HOST` | *(Required)* | IP address or hostname of the target Linux VPS. |
| `RESOURCE_PLANE_SSH_USER` | `root` | SSH user with permissions to run Docker. |
| `RESOURCE_PLANE_SSH_PORT` | `22` | Remote SSH port. |
| `RESOURCE_PLANE_SSH_KEY` | *(Required)* | Path to private SSH key file (canonically placed in `.secrets/resource_plane_ssh`). Ambient fallbacks are disabled. |

#### SSH Key Storage and Central Config Store (`config/env/`)

Keep the multi-line SSH private key in a separate file; the factory configuration parser handles single-line values rather than embedding multi-line keys in `.env`. Under [ADR 0083](../adr/0083-mandatory-resource-plane-ssh-key-and-secrets-directory.md) and [ADR 0093](../adr/0093-central-config-store-and-dashboard-scratchpad.md):

1. **In-Repo Placement**: Save the private key to `.secrets/resource_plane_ssh` (extensionless per Linux conventions). The `.secrets/` directory is excluded in `.gitignore`.
2. **Automatic Permission Hardening**: `modal-sandbox infra deploy` validates that the key exists and normalizes its permissions to `0600` and adds a missing trailing newline to a recognized private-key file.
3. **Synchronize to `config/env/`**: Push the key to the central config store with the `--allow-binary` flag:
   ```bash
   push-repo-env -e .secrets/resource_plane_ssh -d resource_plane_ssh --allow-binary
   ```
   When pulling secrets via `pull-repo-env`, the key is automatically restored to `.secrets/resource_plane_ssh` with `0600` permissions.

---

## 2. Deployment Workflow

### Step 1: Pre-flight Verification (`--check-only`)
Before synchronizing files or running containers, verify SSH reachability and remote Docker status:

```bash
modal-sandbox infra deploy --check-only
```

Expected output:
```text
Probing root@203.0.113.10:22...
✓  Docker daemon is active and responsive.
```

### Step 2: Run Full Automated Deployment
Execute the complete deployment:

```bash
modal-sandbox infra deploy
```

The pipeline executes the following stages automatically:
1. **Connectivity Check**: Tests SSH reachability.
2. **Environment Validation**: Runs `docker info` remotely to verify the daemon.
3. **File Synchronization**: Streams `resource-plane/` to `/opt/resource-plane` using SSH and tar. The archive excludes `.env`, `.data`, `.git`, `node_modules`, and `.next`.
4. **Idempotent Container Orchestration**: Executes `./deploy.sh` remotely, ensuring the `dbhost-network` Docker bridge network exists, starting/rebuilding containers via Docker Compose, applying migrations, and polling the health endpoint.
5. **Deterministic Credential Synchronization**: Automatically retrieves the remote `ADMIN_TOKEN` and writes `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` into the local root `.env` (preserving any existing values).

   Output on completion:
```text
✅ Resource Plane successfully deployed to VPS!
   Dashboard / Web UI: http://203.0.113.10:3000
   PostgreSQL Port:   <read the remote .env / Compose binding>
   SeaweedFS S3 Port: 8333

   ✓ Synchronized RESOURCE_PLANE_DOMAIN, RESOURCE_PLANE_ADMIN_TOKEN to .env
```

Fresh production setup generates `.env` with PostgreSQL port **5432**, web port 3000, and S3 port 8333. Existing installations may use 54320 or other ports. The deployment CLI banner has a legacy 54320 label; read the remote `.env`, Compose bindings, and issued connection details for the actual port.

Before distributing database credentials, set `PUBLIC_POSTGRES_HOST` in the remote `/opt/resource-plane/.env` to the hostname or IP used by clients, then rerun deployment so certificate SANs and connection details match. Its generated default is `localhost`. Preserve the generated passwords and tokens when editing this file.

### Step 3: Configure Host Ingress Proxy & HTTPS (`modal-sandbox infra caddy`)

Point your DNS A record (`RESOURCE_PLANE_DOMAIN`, and optionally an S3 subdomain) at the VPS IP, then configure Caddy at `/opt/caddy`:

```bash
# On a fresh VPS (provisions /opt/caddy via Docker Compose + dbhost-network):
modal-sandbox infra caddy --bootstrap --domain db-host.example.com

# Optional ACME email during initial bootstrap and optional S3 domain:
modal-sandbox infra caddy --bootstrap --email ops@example.com \
  --domain db-host.example.com \
  --s3-domain s3.example.com

# Subsequent route updates (or when /opt/caddy is already running):
modal-sandbox infra caddy --domain db-host.example.com

# Provision /opt/caddy on a brand-new VPS with a single wildcard certificate for APPS_BASE_DOMAIN:
modal-sandbox infra caddy --bootstrap --wildcard --domain db-host.example.com

# Or configure/upgrade wildcard ingress from APPS_BASE_DOMAIN + CLOUDFLARE_DNS_API_TOKEN in .env:
modal-sandbox infra caddy --wildcard

# Verify running container, network attachment, and Caddyfile validity:
modal-sandbox infra caddy --check-only
```

- `/opt/caddy` lives as a sibling stack to `/opt/resource-plane` (strictly canonical with no `.env` path overrides).
- Resource Plane routes are isolated in `/opt/caddy/conf/sites/resource-plane.caddy` via `import /etc/caddy/sites/*.caddy`, keeping co-located VPS apps isolated. `--domain` and `--s3-domain` are normalized (stripping accidental schemes/paths) and never fall back implicitly to `RESOURCE_PLANE_DOMAIN` in `.env`.
- Wildcard Hosted App ingress uses `resource-plane/caddy/Dockerfile` (`caddy-dns/cloudflare`), writes `CLOUDFLARE_DNS_API_TOKEN` to `/opt/caddy/.env` (`0600`), configures `/opt/caddy/conf/sites/apps-wildcard.caddy` for `<APPS_BASE_DOMAIN>, *.<APPS_BASE_DOMAIN>`, and imports per-app snippets from `/opt/caddy/conf/apps/*.caddy` so new apps add zero Let's Encrypt round-trips. `modal-sandbox infra caddy --wildcard` configures Modal CLI apex routes (`/launch`, `/snapshot`, `/health`, `/api/codex/profiles`) with HTTP `404` on browser paths until `modal-sandbox infra dashboard` deploys the apex Next.js Sandbox Web Dashboard (`sandbox-dashboard-web:3000`).

#### Persisting and Restoring `/opt/caddy` via Central Config Store (`config/caddy/`)

Declarative `/opt/caddy` files (`conf/Caddyfile`, `conf/sites/*.caddy`, nested `conf/` includes, and `docker-compose.override.yml`) are persisted in the private `github.com/${GH_ORG_NAME}/config` repository under `caddy/<profile>/` (`CADDY_STORE_PROFILE`, default `default`):

```bash
# Idempotently capture live /opt/caddy/conf/ and docker-compose.override.yml into config/caddy/<profile>/:
modal-sandbox infra caddy backup

# Optional profile override (e.g., staging vs default production VPS):
modal-sandbox infra caddy backup --profile staging

# Provision /opt/caddy on a brand-new VPS and restore all stored routes + Caddyfile + active networks:
modal-sandbox infra caddy restore --bootstrap

# Idempotently converge an existing running VPS from config/caddy/<profile>/ (--prune removes extra local *.caddy files):
modal-sandbox infra caddy restore
modal-sandbox infra caddy restore --prune
```

- **Fresh-VPS Network Filtering**: If `docker-compose.override.yml` declares `external: true` networks for co-located apps not yet deployed on a new VPS, `restore` filters them to networks already present on the host (reporting any skipped networks). Re-run `modal-sandbox infra caddy restore` after deploying those co-located stacks to attach their networks.
- **Validation and recovery**: Managed changes validate and activate Caddy under a lock. Failed activation attempts rollback; interrupted changes leave `/opt/caddy/.factory-ingress-pending` for recovery by the next mutating ingress operation. Preserve that journal if recovery reports an error.
- **Backup scope**: Caddy Store captures declarative configuration, not the VPS application data, `/opt/caddy/.env` DNS token, app ownership registry, or `caddy_data` / `caddy_config` ACME volumes. Ownership receipts in app routes can help restore identity, but do not restore application source or data. Restore secrets separately and allow certificates to reissue after DNS switches.

---

## 3. Configuring Execution Sandboxes to Use the Deployed Resource Plane

`modal-sandbox infra deploy` fills missing connection variables in your root `.env` and preserves existing nonempty values. After adding HTTPS, set `RESOURCE_PLANE_DOMAIN` to the HTTPS hostname. For direct local HTTP testing use an explicit URL such as `http://127.0.0.1:3000`; a bare hostname is normalized to HTTPS by clients. If you manage `.env` manually, ensure the following are set:

```env
# HTTPS URL of the Resource Plane deployment
RESOURCE_PLANE_DOMAIN=https://resources.example.com
# Admin bearer token configured in resource-plane/.env
RESOURCE_PLANE_ADMIN_TOKEN=your-generated-admin-token
```

Now `create-db` and `create-s3` will provision against your hosted Resource Plane:

```bash
# Provision a PostgreSQL database
create-db app-db --write-env

# Provision an S3 bucket
create-s3 app-assets --write-env
```

---

## Local development

For local development, use the Next.js server plus its Docker Auto-Bootstrapper. From the monorepo root:

```bash
pnpm install
cd resource-plane/apps/web
```

Create `.env.local` in this web application directory:

```env
CONTROL_PLANE_USERNAME=admin
CONTROL_PLANE_PASSWORD=replace-with-a-strong-local-password
ADMIN_TOKEN=replace-with-a-random-local-mcp-token
```

```bash
pnpm dev
```

Open `http://localhost:3000`. Resource operations trigger Docker service initialization and migrations. Master database/storage credentials are generated into `.env.local` when missing. Dashboard authentication requires the password configured above. Development data defaults to `resource-plane/apps/web/.data/`; PostgreSQL prefers 5432 and can fall back to 54320, while S3 uses 8333. Inspect `/api/health` and issued credentials for selected ports.

The default `resource-plane/docker-compose.yml` defines only PostgreSQL and SeaweedFS, not the web service or the full TLS/S3 initialization workflow. `docker compose up` alone is not a complete console quickstart. For a complete local production-style stack, run `./deploy.sh` from `resource-plane/` on a host with Docker, rather than copying its incomplete `.env.example` into a production `.env`.

## Network exposure and backups

Allow SSH for the deployment host and public HTTP/HTTPS for Caddy. Expose the configured PostgreSQL port only to clients that need it. Route console and S3 traffic through Caddy for HTTPS; their direct ports speak HTTP. Keep internal filer port 8888 private. Production Compose publishes listeners on `0.0.0.0` unless `HOST_BIND_IP` is configured, so host firewall policy must match the intended exposure.

Back up `/opt/resource-plane/.env` and `.data/` separately from `config/caddy/`, including database, S3, and CA state. Use logical PostgreSQL backups or a consistent stopped/filesystem snapshot procedure. Keep the Caddy DNS token and certificate volumes in a separate sensitive backup process.

Continue to [application creation and deployment](applications.md) to deploy apps using the database, buckets, and wildcard ingress. The [Resource Plane README](https://github.com/YoungMahesh/software-factory/blob/main/resource-plane/README.md) covers MCP connections and operational commands.
