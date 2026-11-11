# Architecture Overview

Modal Sandboxes provides a unified architecture for spinning up, connecting to, and managing isolated cloud execution environments.

## System Topology

```mermaid
flowchart TD
    subgraph ControlSurfaces["Control Surfaces"]
        CLI["modal-sandbox CLI<br/>(sandbox/main.py)"]
        Dashboard["Web UI & REST API<br/>(sandbox/function.py)"]
    end

    subgraph CoreRunner["Execution Core"]
        Launcher["Unified Launcher<br/>(sandbox/launcher.py)"]
        ImageBuilder["Image Factory<br/>(sandbox/image.py)"]
        ProfileManager["Profile Manager<br/>(sandbox/profiles.py)"]
        ConfigStaging["Config & Staging<br/>(sandbox/config_and_staging.py)"]
    end

    subgraph CloudInfra["Modal Cloud Infrastructure"]
        subgraph SandboxRuntime["Modal Sandbox (Container or VM)"]
            direction TB
            Init["startup.sh Bootstrapper"]
            SSHd["OpenSSH Daemon (:2222)"]
            CF["Cloudflared (:3000)"]
            WorkspaceDir["/root/<workspace>"]
            AIStack["AI Agents (T3 / OpenCode / Pi)"]
        end
        Volumes["Modal Volumes (t3code-usage-v1)"]
        SnapshotStorage["Modal Image Registry"]
    end

    CLI --> Launcher
    Dashboard --> Launcher
    Launcher --> ImageBuilder
    Launcher --> ProfileManager
    Launcher --> ConfigStaging
    Launcher --> SandboxRuntime
    SandboxRuntime -.-> Volumes
    SandboxRuntime -.-> SnapshotStorage
```

## Architectural Components

### 1. Control Surfaces
- **`modal-sandbox` CLI**: The primary entry point for developers. Parses flags, resolves local configuration, establishes SSH keys, and interacts with Modal's API.
- **Serverless Web Control Plane**: A FastAPI application hosted via `modal.fastapi_endpoint` in `sandbox/function.py`. Exposes an authenticated dashboard (`GET /`) and REST API (`POST /api/sandboxes`, `POST /launch`, etc.).

### 2. Execution Core
- **`sandbox/launcher.py`**: The unified sandbox runner. Orchestrates sandbox creation for both standalone and repository-backed runs, whether targeting standard containers or Linux VMs.
- **`sandbox/image.py`**: Composable image definitions using `modal.Image`. Prebakes dependencies, developer utilities, and optional toolchains.
- **`sandbox/config_and_staging.py`**: Stages configuration files, environment variables, startup scripts, and credentials into sandbox directories (`.secrets/`, `.scripts/`).

### 3. In-Sandbox Bootstrap
- **`startup.sh`**: Runs as the entrypoint inside the sandbox. Starts `sshd`, executes cloudflared ingress, provisions optional agent tools, clones target repositories, and scrubs sensitive bootstrapping keys.

### 4. Storage & Persistence
- **Filesystem Snapshots**: Fast copy-on-write filesystem images leveraging `modal.Image.from_id()`.
- **Persistent Volumes**: Dedicated Modal volumes (e.g., `t3code-usage-v1`) that preserve agent transcripts and cache data across sandboxes.
