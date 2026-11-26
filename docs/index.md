# Software Factory

Software Factory combines development environments, persistent application resources, and an application starter:

1. **Execution Plane (`sandboxes/`)**: Modal containers and VMs with SSH, T3 Code, filesystem snapshots, and optional Cloudflare application ingress, backed by the hosted FastAPI control plane (`sandboxes/sandbox/function.py`).
2. **Sandbox Dashboard (`dashboard/`)**: A Next.js 16 + React 19 web dashboard and same-origin BFF proxy deployed to `/opt/sandbox-dashboard` and exposed at `https://<APPS_BASE_DOMAIN>` for launching Factory Apps, monitoring sandboxes and Modal costs, managing snapshots, and editing Scratchpad notes.
3. **Resource Plane (`resource-plane/`)**: A Next.js console and MCP API managing PostgreSQL 16 databases and SeaweedFS S3 buckets. Run it locally with the Node development server and Docker, or deploy the production stack to a VPS.
4. **App Template (`app-template/`)**: A Next.js 16 starter with optional Expo mobile, database, authentication, and agent skills. Materialize it with `create-app`, then optionally provision resources and deploy a Hosted App.

## Choose a workflow

- [Prerequisites and setup](getting-started/prerequisites.md): install the CLI and prepare Modal authentication and SSH access.
- [First sandbox](getting-started/quickstart.md): launch a standalone workspace and use its printed connection details.
- [Application creation and deployment](guides/applications.md): scaffold locally, wire cloud resources, and deploy to wildcard HTTPS.
- [Resource Plane deployment](guides/resource-plane-deployment.md): run persistence services locally or deploy them over SSH.
- [Hosted control plane and dashboard](guides/control-plane.md): deploy the Modal control plane and Next.js dashboard, and use the REST API.
- [AI tooling](guides/ai-tooling.md): configure T3 Code providers and Codex login profiles.

## Reference

- [CLI commands and options](guides/cli.md)
- [Environment variables and precedence](reference/environment.md)
- [Architecture overview](architecture/overview.md)
- [Ingress and connectivity](architecture/ingress.md)
- [Filesystem snapshots and persistence](architecture/snapshots.md)
- [Secrets and credential lifecycle](architecture/secrets.md)
- [Documentation build and deployment](guides/deploying-documentation.md)
- [Architecture decision history](adr/index.md)

The guides describe current behavior. ADRs record decisions at the time they were made; later decisions may amend or supersede them.
