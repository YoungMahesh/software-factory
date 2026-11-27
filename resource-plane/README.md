# Resource Plane

The persistence subsystem of Software Factory: a Next.js 16 / React 19 application providing the Resource Plane Console and Resource Plane Management API over MCP for PostgreSQL 16 databases and SeaweedFS S3 buckets.

Resource Plane Projects group application databases and object storage. They are separate from T3 Projects and Builder Workspaces. See the [factory glossary](../GLOSSARY.md) for shared terms.

The factory monorepo also contains Modal sandbox tooling in `sandboxes/` and an application blueprint in `app-template/`. See the [root README](../readme.md), [architecture](../docs/architecture/resource-plane.md), and [deployment guide](../docs/guides/resource-plane-deployment.md).

## Local development

Use Docker Engine with an accessible Docker socket, OpenSSL, Node.js compatible with the Next.js package, and pnpm 10.31.0. Install dependencies from the monorepo root:

```bash
git clone https://github.com/YoungMahesh/software-factory.git
cd software-factory
pnpm install
cd resource-plane/apps/web
```

Create `.env.local` in that web application directory with your chosen local credentials:

```env
CONTROL_PLANE_USERNAME=admin
CONTROL_PLANE_PASSWORD=replace-with-a-strong-local-password
ADMIN_TOKEN=replace-with-a-random-local-mcp-token
```

```bash
pnpm dev
```

Visit `http://localhost:3000`. Resource operations trigger the Auto-Bootstrapper, which creates/starts `neon-postgres` and `neon-seaweedfs`, initializes the `neon_control_plane` metadata database, applies migrations, and generates TLS certificates. Master database and storage credentials are generated into the web process's `.env.local` when absent. Explicit Resource Plane Console Credentials above ensure the Next.js middleware requires authentication.

Development data defaults to `resource-plane/apps/web/.data/`. PostgreSQL uses port 5432 when available, falls back to 54320, or honors `POSTGRES_PORT`; inspect `/api/health` for the selected port. S3 uses port 8333. Containers bind to loopback by default in development.

The root `resource-plane/.env.example` is inherited application-template configuration, not a complete production credential file. Default `docker-compose.yml` defines only PostgreSQL and SeaweedFS; `docker compose up` alone does not launch the Resource Plane Console or perform its full bootstrap.

Run Resource Plane tests from the monorepo root with `pnpm --dir resource-plane test`.

## Production deployment

The factory CLI deploys this subsystem to `/opt/resource-plane` using an explicit host SSH private key:

```bash
modal-sandbox infra deploy --check-only
modal-sandbox infra deploy
```

Alternatively, from the `resource-plane/` directory in a full checkout on the VPS:

```bash
./deploy.sh
```

`deploy.sh` generates production `.env` credentials on first run, prepares TLS/S3 configuration and `dbhost-network`, builds the web container, and launches all three services with `docker-compose.prod.yml`. Existing `.env` and `.data/` are reused. Do not overwrite an existing credential file when upgrading.

Fresh production setup writes host ports 5432 (PostgreSQL), 3000 (web), and 8333 (S3). Existing deployments may use 54320 or other configured ports. Set `PUBLIC_POSTGRES_HOST` in the generated `.env` to the hostname/IP used by clients, then rerun deployment before distributing database connections; its initial value is `localhost`.

Public HTTPS uses the sibling Caddy stack at `/opt/caddy`. See [VPS and ingress setup](../docs/guides/resource-plane-deployment.md) for proxy routes, firewall boundaries, backups, and restore. Configure factory clients with the resulting `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN`.

## Authentication and MCP

- Resource Plane Console Credentials: `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD`, falling back to `CONTROL_PLANE_USERNAME` / `CONTROL_PLANE_PASSWORD`.
- Resource Plane Management API: server `ADMIN_TOKEN` (fallback `NEON_ADMIN_TOKEN`); clients pass it as `Authorization: Bearer <token>` to `POST /api/mcp` or `POST /mcp`.
- Public metadata: `GET /api/ca.crt` and `GET /api/health` bypass Basic authentication.

The HTTP handler accepts JSON-RPC POST requests; a GET SSE stream is not implemented. For stdio, run `pnpm --filter @repo/web mcp` from `resource-plane/`, with its service environment configured. Set the MCP client's working directory to your actual checkout rather than an old standalone `/opt/db-host` path.

| MCP tool | Purpose |
| :--- | :--- |
| `list_projects` | List Resource Plane Projects |
| `create_project` | Create a Resource Plane Project |
| `create_database` | Create an isolated database and role |
| `list_databases` | List Resource Plane Project databases |
| `get_database_credentials` | Retrieve database credentials |
| `create_object_storage` | Create a bucket and IAM credentials |
| `list_object_storages` | List Resource Plane Project buckets |
| `get_storage_credentials` | Retrieve storage credentials |

## Client connections

Download `/api/ca.crt` from the Resource Plane and use the host, port, role, and database from the issued connection details:

```bash
curl -o ca.crt https://resources.example.com/api/ca.crt
psql 'postgresql://<role>:<password>@<database-host>:<published-port>/<database>?sslmode=verify-full&sslrootcert=ca.crt'
```

The S3 API speaks HTTP on port 8333; use the configured proxy hostname for HTTPS. Supply the issued bucket credentials, region (normally `us-east-1`), and path-style addressing to your SDK. Factory commands `create-db` and `create-s3` can provision resources and write application `.env` values; see the [CLI reference](../docs/guides/cli.md).

## Operations and backups

On the production VPS:

```bash
cd /opt/resource-plane
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 web
curl http://127.0.0.1:3000/api/health
```

The health response contains top-level `postgres` and `seaweedfs` status objects, including their ports and container state. It does not require Basic authentication.

Back up `.env`, `.data/postgres/`, `.data/seaweedfs/`, and `.data/certs/` as sensitive state. Use PostgreSQL logical backups or a consistent stopped/filesystem snapshot procedure; copying a live database directory is not a standalone recovery strategy. Protect the CA private key and stored service credentials. Caddy declarations and certificate volumes require separate backups; Central Config Store (`config/caddy/`) excludes secret environment files and ACME volumes.

For canonical terms, use the repository [glossary](../GLOSSARY.md). Historical subsystem decisions remain under [docs/adr/](docs/adr/); current platform architecture decisions are in the [root ADR index](../docs/adr/index.md).
