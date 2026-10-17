# Factory Studio Cloud Turso Database Persistence

**Status**: Accepted (Supersedes [ADR 0041](0041-factory-studio-database-persistence.md) for development and production environments)

To provide unified, persistent state across developer workspaces, cloud development sandboxes, and ephemeral VM environments without data loss or sync drift, we decided to migrate Factory Studio's storage engine from a local embedded SQLite file to a cloud-hosted Turso (libSQL) database over TLS for development and production, while preserving hermetic in-memory SQLite (`:memory:`) for automated test suites.

## Context

In ADR-0041, we established an embedded local SQLite file (`factory/ui/data/factory_studio.db`) in WAL mode for Factory Studio chat history, job metadata, and telemetry logs. While zero-dependency for a single machine, this architecture introduced operational limitations:

1. **State Trapped in Ephemeral Sandboxes**: When running Factory Studio in cloud developer environments (such as Modal development sandboxes), destroying or recycling the container wiped all conversational prompts, Grilling Assistant question frontiers, approved plans, and execution logs.
2. **Fragmented Developer Observability**: Developers running jobs across multiple machines or cloud instances could not view or collaborate on past pipeline runs or preview states from a central source of truth.
3. **Local Replica Drift Risks**: Distributed local replica approaches risk database cache corruption and synchronization divergence across simultaneous worker instances.

## Decision

1. **Cloud-Hosted Turso (libSQL) Persistence**:
   - In development and production environments, Factory Studio connects directly over TLS to a cloud-hosted Turso database using `libsql-experimental` (`libsql_experimental.connect(url, auth_token=token)`).
   - Direct remote connections eliminate local replica cache corruption and multi-node synchronization drift.
   - Relational schemas (`chat_messages`, `factory_jobs`, `job_telemetry_events`, `job_console_logs`, `previews`) and corresponding indexes are initialized idempotently on startup directly against the Turso database.

2. **Hermetic In-Memory Testing Seam**:
   - Automated unit and integration test suites retain standard in-memory SQLite (`:memory:`).
   - When initialized with `db_path=":memory:"`, `StudioDatabase` bypasses all network drivers and credential checks, ensuring tests remain 100% offline, hermetic, fast, and free of remote state pollution.

3. **Fail-Fast Credential Configuration**:
   - In development and production mode (`db_path is None`), `StudioDatabase` reads credentials from the root `.env` file (falling back to process environment variables).
   - Missing `TURSO_DATABASE_URL` or `TURSO_AUTH_TOKEN` causes an immediate, descriptive `RuntimeError` on startup explaining how to configure the environment.

4. **Credential Security**:
   - `.env*` is added to `.gitignore` to prevent secret commits to version control, while `!.env.example` allows tracking the `.env.example` configuration template.

5. **Resilient High-Velocity Batch Flusher**:
   - High-throughput terminal logs and agent telemetry events continue to pass through an in-memory queue to maintain SSE responsiveness.
   - The background batch worker flushes records in atomic batches over remote HTTPS with retry logic and exponential backoff (up to 3 attempts), retaining uncommitted items in the queue if transient network hiccups occur.

## Consequences

- **Supersession**: ADR 0041 is formally superseded for development and production environments. Local SQLite file creation at `factory/ui/data/factory_studio.db` is replaced by remote Turso persistence.
- **Domain Modeling**: The **Studio Database** glossary definition in `CONTEXT.md` is updated to specify cloud-hosted Turso persistence with in-memory SQLite reserved for testing.
- **Reliability & Portability**: Chat history, question frontiers, approved architectural plans, and pipeline job records persist durably across machine reboots, container destruction, and team developer instances.
