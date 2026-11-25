# Resource Plane VPS Deployment Guide

This guide walks through deploying the **Resource Plane** (PostgreSQL 16, SeaweedFS S3 object storage, and Next.js management console) to a dedicated Linux VPS or local Docker environment.

---

## 1. Automated VPS Deployment (`modal-sandbox infra deploy`)

Software Factory includes a turnkey infrastructure deployment command:

```bash
modal-sandbox infra deploy
# or using the dedicated CLI alias:
deploy-infra
```

The deployment automation operates entirely over SSH using native `subprocess` and `tar` (zero third-party Python dependencies), verifying remote requirements, synchronizing the `resource-plane/` directory, and executing the production startup script remotely.

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
RESOURCE_PLANE_REMOTE_DIR=/opt/resource-plane
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `RESOURCE_PLANE_SSH_HOST` | *(Required)* | IP address or hostname of the target Linux VPS. |
| `RESOURCE_PLANE_SSH_USER` | `root` | SSH user with permissions to run Docker. |
| `RESOURCE_PLANE_SSH_PORT` | `22` | Remote SSH port. |
| `RESOURCE_PLANE_SSH_KEY` | *(Required)* | Path to private SSH key file (canonically placed in `.secrets/resource_plane_ssh`). Ambient fallbacks are disabled. |
| `RESOURCE_PLANE_REMOTE_DIR` | `/opt/resource-plane` | Destination folder on the remote VPS. |

#### SSH Key Storage and Central Vault (`env-store`)

Because OpenSSH private keys are multi-line PEM files, they cannot be stored directly inside a `.env` file without breaking dotenv and SOPS unmarshalling. Under [ADR 0083](../adr/0083-mandatory-resource-plane-ssh-key-and-secrets-directory.md):

1. **In-Repo Placement**: Save the private key to `.secrets/resource_plane_ssh` (extensionless per Linux conventions). The `.secrets/` directory is excluded in `.gitignore`.
2. **Automatic Permission Hardening**: `modal-sandbox infra deploy` validates that the key exists and automatically enforces `chmod 0600` if file permissions are overly permissive.
3. **Synchronize to `env-store`**: Push the key to the central secret vault with the `--allow-binary` flag:
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
3. **File Synchronization**: Streams `resource-plane/` to `RESOURCE_PLANE_REMOTE_DIR` using SSH and tar. The archive excludes `.env`, `.data`, `.git`, `node_modules`, and `.next`.
4. **Idempotent Container Orchestration**: Executes `./deploy.sh` remotely, ensuring the `dbhost-network` Docker bridge network exists, starting/rebuilding containers via Docker Compose, applying migrations, and polling the health endpoint.
5. **Deterministic Credential Synchronization**: Automatically retrieves the remote `ADMIN_TOKEN` and writes `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` into the local root `.env` (preserving any existing values, or bypassed via `--no-sync-env`).

   Output on completion:
```text
✅ Resource Plane successfully deployed to VPS!
   Dashboard / Web UI: http://203.0.113.10:3000
   PostgreSQL Port:   54320 (or configured host port)
   SeaweedFS S3 Port: 8333

   ✓ Synchronized RESOURCE_PLANE_DOMAIN, RESOURCE_PLANE_ADMIN_TOKEN to .env
```

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

# Verify running container, network attachment, and Caddyfile validity:
modal-sandbox infra caddy --check-only
```

- `/opt/caddy` lives as a sibling stack to `/opt/resource-plane` (strictly canonical with no `.env` path overrides).
- Resource Plane routes are isolated in `/opt/caddy/conf/sites/resource-plane.caddy` via `import /etc/caddy/sites/*.caddy`, keeping co-located VPS apps isolated.

#### Persisting and Restoring `/opt/caddy` via Host Ingress Store (`caddy-store`)

Declarative `/opt/caddy` files (`conf/Caddyfile`, `conf/sites/*.caddy`, nested `conf/` includes, and `docker-compose.override.yml`) are persisted in the private `github.com/${GH_ORG_NAME}/caddy-store` repository organized by logical VPS profile folder (`CADDY_STORE_PROFILE`, default `default`):

```bash
# Idempotently capture live /opt/caddy/conf/ and docker-compose.override.yml into caddy-store:
modal-sandbox infra caddy backup

# Optional profile override (e.g., staging vs default production VPS):
modal-sandbox infra caddy backup --profile staging

# Update Resource Plane route and immediately sync /opt/caddy to caddy-store:
modal-sandbox infra caddy --domain db-host.example.com --sync

# Provision /opt/caddy on a brand-new VPS and restore all stored routes + Caddyfile + active networks:
modal-sandbox infra caddy --bootstrap --from-store

# Idempotently converge an existing running VPS from caddy-store (--prune removes extra local *.caddy files):
modal-sandbox infra caddy restore
modal-sandbox infra caddy restore --prune
```

- **Fresh-VPS Network Filtering**: If `docker-compose.override.yml` declares `external: true` networks for co-located apps not yet deployed on a new VPS, `restore` / `--bootstrap --from-store` filters them to networks already present on the host (reporting any skipped networks). Re-run `modal-sandbox infra caddy restore` after deploying those co-located stacks to attach their networks.
- **Safety & Rollback**: `restore` validates `conf/` with `caddy validate` before reloading or applying compose overrides and rolls back automatically on validation failure. `caddy_data`/`caddy_config` ACME volumes are excluded so certificates re-issue cleanly once DNS switches.

---

## 3. Configuring Execution Sandboxes to Use the Deployed Resource Plane

`deploy-infra` automatically populates the required connection variables in your root `.env`. If you used `--no-sync-env` or manage `.env` manually, ensure the following are set:

```env
# Domain name or IP pointing to the Resource Plane deployment
RESOURCE_PLANE_DOMAIN=203.0.113.10
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

## 4. Local Evaluation Mode (`docker compose up`)

For local testing or development without a remote VPS:

```bash
cd resource-plane
cp .env.example .env
docker compose up -d
```

This starts all three services locally:
- Web Dashboard: `http://localhost:3000`
- PostgreSQL: `localhost:54320`
- SeaweedFS S3: `http://localhost:8333`
