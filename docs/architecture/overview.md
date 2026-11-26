# Architecture Overview

Software Factory provides a cohesive monorepo architecture partitioning cloud execution environments, persistent database and storage infrastructure, and the starter application blueprint (see [ADR 0081](../adr/0081-monorepo-architecture-for-execution-and-resource-planes.md) and [ADR 0087](../adr/0087-app-template-and-scaffolder-integration.md)):

1. **Execution Plane (`sandboxes/`)**: Ephemeral, isolated cloud containers and Linux VMs running on [Modal](https://modal.com) with OpenSSH, Cloudflare ingress, integrated AI developer tooling, and the Python App Scaffolder (`create-app`).
2. **Resource Plane (`resource-plane/`)**: Stateful persistence and control plane subsystem hosted on a dedicated Linux VPS or local Docker environment, providing isolated PostgreSQL 16 databases, SeaweedFS S3 object storage buckets, root TLS CA generation, interactive web console, and an MCP server (`POST /api/mcp`).
3. **App Template (`app-template/`)**: Canonical Next.js 16 + optional Expo React Native starter blueprint materialized by `create-app` (and staged into `/opt/app-template` inside Modal sandboxes).

---

## System Topology

```mermaid
flowchart TD
    subgraph ControlSurfaces["Control Surfaces"]
        CLI["modal-sandbox & deploy-infra CLI<br/>(sandboxes/sandbox/main.py)"]
        Dashboard["Serverless Control Plane Web UI<br/>(sandboxes/sandbox/function.py)"]
        RPConsole["Resource Plane Console & MCP<br/>(resource-plane/apps/web)"]
    end

    subgraph ExecutionPlane["Execution Plane (Modal Cloud Infrastructure)"]
        Launcher["Unified Launcher<br/>(sandboxes/sandbox/launcher.py)"]
        ImageBuilder["Image Factory<br/>(sandboxes/shared/image.py)"]
        ProfileManager["Profile Manager<br/>(sandboxes/sandbox/profiles.py)"]
        EnvStore["Host-Side Secrets Decryption<br/>(sandboxes/sandbox/env_store.py)"]

        subgraph SandboxRuntime["Modal Sandbox (Container or VM)"]
            direction TB
            Init["startup.sh Bootstrapper"]
            SSHd["OpenSSH Daemon (:2222)"]
            CF["Optional Cloudflared (:3000)<br/>Configured tunnel token required"]
            WorkspaceDir["/root/<workspace>"]
            AIStack["T3 Code providers<br/>Antigravity / OpenCode / Codex"]
        end
        Volumes["Modal Volumes (t3code-usage-v1)"]
        SnapshotStorage["Modal Image Registry (from_id)"]
    end

    subgraph ResourcePlane["Resource Plane (Linux VPS / Docker Host)"]
        RPDeploy["Turnkey VPS Deploy Pipeline<br/>(sandboxes/sandbox/infra_deploy.py)"]
        RPPostgres["PostgreSQL 16 Cluster<br/>(configured port, TLS)"]
        RPStorage["SeaweedFS S3 Engine<br/>(:8333 S3 API)"]
        RPCA["Root CA Authority<br/>(/api/ca.crt)"]
    end

    CLI --> Launcher
    CLI -- "SSH Automation (deploy)" --> RPDeploy
    RPDeploy --> RPConsole
    Dashboard --> Launcher
    Launcher --> ImageBuilder
    Launcher --> ProfileManager
    Launcher --> EnvStore
    Launcher --> SandboxRuntime
    SandboxRuntime -.-> Volumes
    SandboxRuntime -.-> SnapshotStorage

    SandboxRuntime -- "TLS Connection (configured port)" --> RPPostgres
    SandboxRuntime -- "S3 API (:8333)" --> RPStorage
    Launcher -- "JSON-RPC (POST /api/mcp)" --> RPConsole
```

---

## Architectural Subsystems

### 1. Execution Plane (`sandboxes/`)

- **`sandboxes/sandbox/main.py`**: The primary CLI entrypoint (`modal-sandbox`). Parses runtime flags, resolves local configuration, triggers snapshots, and dispatches subcommands (including `modal-sandbox infra deploy`).
- **`sandboxes/sandbox/function.py`**: Serverless FastAPI control plane hosted via `@modal.asgi_app()`. Exposes the prompt-first **Factory App** Builder homepage and operator dashboard (`GET /`), spawned `Launch Request` worker (`run_launch_request`), and REST API (`POST /api/apps`, `POST /api/sandboxes`, `POST /launch`, etc.).
- **`sandboxes/sandbox/launcher.py`**: Unified sandbox runner orchestrating container and Linux VM creation via the Modal client SDK.
- **`sandboxes/shared/image.py`**: Composable base and runtime image definitions with prebaked developer utilities and toolchains.
- **`sandboxes/sandbox/env_store.py`**: Retrieves and decrypts target repository secrets host-side from the Central Config Store (`config` under `env/<repo>/`) before injecting them into sandboxes via `modal.Secret`.
- **`sandboxes/shared/startup.sh`**: Runs as the entrypoint inside the sandbox container. Starts `sshd`, executes cloudflared ingress, configures AI developer harnesses, clones target repositories, and materializes local `.env` files.
- **Filesystem Snapshots & Volumes**: Copy-on-write image capture leveraging `modal.Image.from_id()` and persistent storage for agent usage metrics (`t3code-usage-v1`) and Factory App metadata (`factory-state-v1`) via `modal.Volume`.

### 2. Resource Plane (`resource-plane/`)

- **Dedicated Persistence Architecture**: Outlined in detail in the [Resource Plane Architecture](resource-plane.md).
- **Turnkey Infrastructure Deployment**: Automated remote VPS provisioning via `modal-sandbox infra deploy` (see [Resource Plane VPS Deployment Guide](../guides/resource-plane-deployment.md)).
- **Dual Runtimes**: Production deployment to Linux VPS over SSH, or a local Next.js development server whose Auto-Bootstrapper manages Docker services. Default Compose alone provides only PostgreSQL and SeaweedFS.

### 3. App Template and Hosted Apps

`app-template/` is excluded from the factory pnpm workspace and copied into independent projects by `create-app`. Cloud wiring can create GitHub repositories, persistence resources, vault files, and a development sandbox. Host-side `deploy-app` transfers a generated app or pulls its GitHub source to `/root/<repo-name>` on the VPS, builds it, and routes it through wildcard Caddy ingress at `/opt/caddy`.

See [application creation and deployment](../guides/applications.md). The Caddy and app deployment configuration is separate from sandbox Cloudflare tunnels. Filesystem snapshots and persistent volumes may retain credentials; see [secrets](secrets.md) before sharing them.
