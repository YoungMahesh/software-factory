# Software Factory

A unified, two-subsystem monorepo platform combining cloud execution environments on [Modal](https://modal.com) with persistent stateful database and object storage infrastructure:

1. **`sandboxes/` (Execution Plane)**: Ephemeral, isolated cloud containers and Linux VMs running on Modal with OpenSSH, Cloudflare Tunnel ingress, and integrated AI developer tooling.
2. **`resource-plane/` (Resource Plane)**: Stateful persistence and control plane subsystem hosted on a dedicated Linux VPS or local Docker environment, providing isolated PostgreSQL 16 databases, SeaweedFS S3 object storage buckets, root TLS CA generation, and an MCP server (`POST /api/mcp`).

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Control Surfaces"]
        CLI["modal-sandbox & deploy-infra CLI<br/>(sandboxes/sandbox/main.py)"]
        WebUI["Web Dashboard & REST API<br/>(sandboxes/sandbox/function.py)"]
        RPUI["Resource Plane Console & MCP<br/>(resource-plane/apps/web)"]
    end

    subgraph ModalCloud["Execution Plane (Modal Cloud Infrastructure)"]
        Runner["Unified Sandbox Runner<br/>(sandboxes/sandbox/launcher.py)"]
        
        subgraph Sandbox["Modal Sandbox Environment"]
            direction TB
            Runtime["Runtime: Standard Container or Linux VM (Docker)"]
            Workspace["Workspace (/root/<name>)<br/>Git Repository & Python Virtual Environment"]
            
            subgraph Services["Network Ingress & Services"]
                SSH["OpenSSH Server (Port 2222)"]
                Tunnel["Cloudflare Ingress (Port 3000)"]
                AgentTools["AI Dev Tooling:<br/>T3 Code (3775), Antigravity ACP,<br/>OpenCode Provider, Chrome Headless"]
            end
        end

        Volume["Persistent Modal Volumes<br/>(t3code-usage-v1, Gradle Caches)"]
        Snapshots["Filesystem Snapshots<br/>(modal.Image Copy-on-Write)"]
    end

    subgraph ResourcePlane["Resource Plane (Linux VPS / Docker Host)"]
        Postgres["PostgreSQL 16 Cluster (:54320 TLS)"]
        SeaweedFS["SeaweedFS S3 Engine (:8333 S3 API)"]
        CertAuthority["Root CA Authority (/api/ca.crt)"]
    end

    CLI --> Runner
    CLI -- "modal-sandbox infra deploy" --> RPUI
    WebUI --> Runner
    Runner --> Sandbox
    Sandbox -.-> Volume
    Sandbox -.-> Snapshots

    Sandbox -- "TLS Database Connection" --> Postgres
    Sandbox -- "S3 Object Storage API" --> SeaweedFS
```

---

## Key Capabilities

- **Zero-Config Standalone Sandboxes**: Launch disposable cloud development instances in seconds with `modal-sandbox --name <sandbox-name>`, requiring only a standard Modal account.
- **Dual Execution Runtimes**: Choose between lightweight standard container sandboxes and full Linux VM sandboxes (`--vm`) equipped with Docker-in-Docker and custom kernel privileges.
- **Hermetic Ingress**: Automatic Cloudflare Tunnel provisioned on port 3000 alongside OpenSSH on port 2222 with zero-friction SSH config registration (`ssh <sandbox-name>`).
- **Filesystem Snapshotting**: Instant copy-on-write image capture (`modal-sandbox --snapshot <id>`) and resumption (`modal-sandbox --from-snapshot <image-id>`).
- **Integrated AI Developer Tooling**: Turnkey provisioning for T3 Code with Antigravity ACP, OpenCode Go, and Playwright-ready headless Chrome.
- **Turnkey Resource Plane Deployment**: Deploy persistent PostgreSQL, SeaweedFS S3, and the Next.js control console to your Linux VPS with a single command (`modal-sandbox infra deploy`).
- **Serverless Web Control Plane**: Deploy a lightweight FastAPI control plane on Modal (`modal deploy sandboxes/sandbox/function.py`) providing a unified web dashboard and REST API.

---

## Quick Navigation

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __[Getting Started](getting-started/quickstart.md)__

    ---

    Launch your first sandbox in under 60 seconds with no credentials beyond `modal setup`.

    [:octicons-arrow-right-24: Start Quickstart](getting-started/quickstart.md)

-   :material-console:{ .lg .middle } __[CLI Reference](guides/cli.md)__

    ---

    Explore all command-line options, feature flags, snapshot actions, and infrastructure deployment commands.

    [:octicons-arrow-right-24: View CLI Guide](guides/cli.md)

-   :material-layers-outline:{ .lg .middle } __[Core Architecture](architecture/overview.md)__

    ---

    Understand the unified runner, execution runtimes, persistence plane, network ingress, and secret lifecycle.

    [:octicons-arrow-right-24: Explore Architecture](architecture/overview.md)

-   :material-server-network:{ .lg .middle } __[Resource Plane VPS Deployment](guides/resource-plane-deployment.md)__

    ---

    Deploy persistent PostgreSQL 16 and SeaweedFS S3 object storage to a Linux VPS with `modal-sandbox infra deploy`.

    [:octicons-arrow-right-24: Deploy Resource Plane](guides/resource-plane-deployment.md)

-   :material-robot-outline:{ .lg .middle } __[AI Developer Tooling](guides/ai-tooling.md)__

    ---

    Connect T3 Code with Antigravity and OpenCode agent providers to live sandboxes.

    [:octicons-arrow-right-24: Configure AI Tools](guides/ai-tooling.md)

-   :material-view-dashboard-outline:{ .lg .middle } __[Control Plane & Dashboard](guides/control-plane.md)__

    ---

    Operate the serverless web management dashboard and REST APIs across all Modal apps.

    [:octicons-arrow-right-24: Inspect Dashboard](guides/control-plane.md)

-   :material-file-document-multiple-outline:{ .lg .middle } __[ADRs](adr/index.md)__

    ---

    Browse the collection of 81+ Architecture Decision Records documenting design choices.

    [:octicons-arrow-right-24: Read ADRs](adr/index.md)

</div>
