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
RESOURCE_PLANE_SSH_KEY=~/.ssh/id_ed25519
RESOURCE_PLANE_REMOTE_DIR=/opt/resource-plane
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `RESOURCE_PLANE_SSH_HOST` | *(Required)* | IP address or hostname of the target Linux VPS. |
| `RESOURCE_PLANE_SSH_USER` | `root` | SSH user with permissions to run Docker. |
| `RESOURCE_PLANE_SSH_PORT` | `22` | Remote SSH port. |
| `RESOURCE_PLANE_SSH_KEY` | `None` | Path to private SSH key file (optional if `ssh-agent` or `~/.ssh/id_rsa` is active). |
| `RESOURCE_PLANE_REMOTE_DIR` | `/opt/resource-plane` | Destination folder on the remote VPS. |

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
4. **Container Orchestration**: Executes `./deploy.sh` remotely, starting PostgreSQL, SeaweedFS, and the Next.js web application via Docker Compose, then applies Drizzle database migrations.

Output on completion:
```text
✅ Resource Plane successfully deployed to VPS!
   Dashboard / Web UI: http://203.0.113.10:3000
   PostgreSQL Port:   54320 (or configured host port)
   SeaweedFS S3 Port: 8333

Next step: ensure RESOURCE_PLANE_DOMAIN and RESOURCE_PLANE_ADMIN_TOKEN are configured in .env
```

---

## 3. Configuring Execution Sandboxes to Use the Deployed Resource Plane

Once deployed, link your Modal sandboxes and CLI utilities to the Resource Plane by setting the connection variables in your root `.env`:

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
