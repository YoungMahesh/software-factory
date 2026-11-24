# Create-DB CLI for db-host PostgreSQL Provisioning and Connection Management

**Status**: Accepted.

The software factory integrates with the hosted `db-host` control plane to provision isolated PostgreSQL databases and construct TLS-secured connection URIs for factory sandboxes and developer repositories.

## Implementation details

1. **Standalone CLI Tool (`create-db`).** Implement `create-db` as a standalone command registered in `pyproject.toml` and symlinked to `/usr/local/bin/create-db` and `/root/.scripts/create-db`. This keeps database connection management decoupled from sandbox lifecycle commands while providing immediate access inside all sandbox environments.

2. **Domain Logic Decomposition (`sandbox/db_host.py`).** Core HTTP and JSON-RPC 2.0 communication with the `db-host` MCP server (`POST /api/mcp`) resides in `sandbox/db_host.py`, respecting the universal 500-line limit. The module handles project discovery (`list_projects`, `create_project`), database provisioning (`create_database`), credential retrieval (`get_database_credentials`), and `.env` file updating.

3. **Environment & Authentication Configuration.** Reads `DB_HOST_DOMAIN` and `DB_HOST_ADMIN_TOKEN` from the ambient environment or local `.env`, with CLI flag overrides (`--domain`, `--token`).

4. **Root CA Certificate Auto-Caching.** PostgreSQL in `db-host` is served over TLS on port `54320` with self-signed certificates. `create-db` automatically fetches the root CA certificate from `https://<domain>/api/ca.crt` and caches it at `~/.config/db-host/ca.crt` (or a custom path via `--ca-path`). The generated connection URI specifies `?sslmode=verify-full&sslrootcert=<ca_path>` for instant compatibility with PostgreSQL client drivers.

5. **Project Scoping & Idempotency.** Project names default to the current Git repository name (via `detect_repo_name()`) or `"default"`, with `--project` override. Database creation is idempotent by default: if a database already exists, `create-db` retrieves the existing credentials via `get_database_credentials` and reports reuse, unless `--fail-if-exists` is explicitly passed.

6. **Local `.env` and Central Vault Integration.** `--write-env` updates or appends `DATABASE_URL` (or `--env-var <NAME>`) in `.env`. An optional `--push-vault` flag triggers `push-repo-env` to encrypt the updated `.env` directly into the organization's `env-store` vault.

7. **Machine-Readable JSON Output.** `--json` emits the full connection record as formatted JSON, and `-q` / `--quiet` emits only the connection URI string.
