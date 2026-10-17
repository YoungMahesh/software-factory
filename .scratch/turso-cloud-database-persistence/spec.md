# Spec: Factory Studio Cloud-Hosted Turso Database Persistence

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

Factory Studio currently relies on an embedded local SQLite file (`factory_studio.db`) residing on local disk. While self-contained, this creates operational hurdles in shared or multi-environment workflows:

1. **State Isolation Across Developer Workspaces and Sandboxes**: When developers run Factory Studio across multiple machines or in ephemeral cloud sandboxes (such as Modal dev instances), the conversational chat history, job execution logs, and live preview states remain trapped in each individual machine's local disk file. There is no shared source of truth.
2. **No Centralized Observability for Autonomous Pipeline Runs**: Historical pipeline runs, telemetry events, and agent thoughts cannot be inspected collaboratively or across sessions unless developers are sitting at the exact physical machine where the job was launched.
3. **Data Loss on Ephemeral Workspace Destruction**: Cloud developer environments and ephemeral VM containers discard local disk storage on termination, wiping all historical chat transcripts, architectural decision records, and pipeline logs.
4. **Credential Security Risk**: Without a standardized environment-variable configuration pattern for database connections, credentials risk being hardcoded or committed to version control.

## Solution

Migrate Factory Studio's storage engine from a local SQLite file to a cloud-hosted SQLite database powered by Turso (libSQL):

1. **Cloud-Hosted Turso Database Engine**:
   - Connect Factory Studio to a cloud-hosted Turso database over TLS using `libsql-experimental` in development and production environments.
   - Utilize direct remote connections, eliminating the risk of local replica cache corruption or synchronization drift.
   - Idempotently initialize relational schemas (`chat_messages`, `factory_jobs`, `job_telemetry_events`, `job_console_logs`, `previews`) directly on the Turso database upon startup.

2. **Dual-Mode Persistence Architecture**:
   - Development and production environments strictly require Turso credentials (`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`), failing fast with clear instructions if unconfigured.
   - Automated test suites remain isolated using standard in-memory SQLite (`:memory:`), ensuring all CI pipelines and local unit tests remain 100% offline, hermetic, fast, and free of remote state pollution.

3. **Secure Environment Configuration**:
   - Manage Turso credentials securely via environment variables and a root `.env` file that is strictly ignored by version control.
   - Provide a `.env.example` template for straightforward developer setup.

4. **Resilient High-Velocity Ingestion**:
   - High-throughput terminal console output and structured agent telemetry continue to pass through an asynchronous in-memory queue.
   - The background batch worker flushes records in atomic batches over remote HTTPS, with exponential backoff retry handling to seamlessly absorb transient network hiccups.

## User Stories

1. As a developer using Factory Studio, I want my chat conversation history and question frontiers stored in a cloud-hosted Turso database, so that my context persists across different machines and development environments.
2. As a team member, I want to view historical assembly line pipeline jobs and preview states started by other instances, so that we have a shared, collaborative view of feature progress.
3. As a developer running Factory Studio in an ephemeral cloud container, I want my chat history and logs to survive container destruction, so that valuable feature context and approved plans are never lost.
4. As an automated test runner in CI, I want test suites to run against an isolated in-memory SQLite database, so that tests execute rapidly, offline, and without requiring network credentials.
5. As a developer configuring the system, I want Factory Studio to read `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from a root `.env` file, so that I do not have to export environment variables manually in every terminal session.
6. As a security-conscious engineer, I want `.env` and credential files to be excluded from version control by default, so that cloud database tokens are never leaked to GitHub.
7. As a developer starting Factory Studio without credentials in development mode, I want the server to fail fast with an actionable error message, so that I immediately know how to set up my `.env` configuration.
8. As a developer watching live terminal logs from an assembly line build, I want remote database log writes to happen asynchronously in the background, so that cloud latency never degrades real-time streaming performance.
9. As a developer experiencing a momentary network blip, I want the background log flusher to retry transient Turso errors with backoff, so that streaming logs are not dropped during network hiccups.
10. As a developer reviewing a past feature, I want to fetch chronological chat history for a target repository from Turso, so that all decisions, recommended options, and approved plans are preserved.
11. As a developer launching multiple concurrent jobs, I want the cloud database to support concurrent connections without file locking errors, so that multiple tasks can report status simultaneously.
12. As a new developer joining the project, I want a `.env.example` file with documented variable names, so that I can configure my local environment in minutes.
13. As a developer starting a fresh feature on an existing repository, I want the clear chat action to purge messages in the cloud database, so that I can begin a clean prompt session while keeping historical jobs intact.
14. As an engineer auditing architectural decisions, I want an Architectural Decision Record (ADR) documenting why we transitioned to Turso, so that the rationale and trade-offs are clearly understood.

## Implementation Decisions

- **Direct Remote libSQL Connection**:
  Development and production environments connect directly to the cloud Turso instance via `libsql-experimental`. No local file replica or SQLite database file is created on disk.
- **Hermetic In-Memory Testing Seam**:
  The database manager detects test invocations (specifically in-memory database targets) and uses standard local in-memory SQLite. Tests never make external network calls or require Turso credentials.
- **Fail-Fast Credential Validation**:
  In non-test mode, the database initialization verifies that the database URL and authentication token are present. If missing, it immediately raises a descriptive configuration error detailing how to populate `.env`.
- **Automatic Environment File Loading**:
  Factory Studio automatically reads `.env` on startup, falling back to existing process environment variables, ensuring seamless developer ergonomics.
- **Version Control Protection**:
  Ensure `.env` patterns are present in `.gitignore` to prevent credential leakage.
- **Batch Worker Retry Resilience**:
  The background batch ingestion thread incorporates retry logic with exponential backoff (up to 3 attempts) for batch flushes, retaining uncommitted events in the in-memory queue until successfully written.
- **Dependency Specification**:
  `libsql-experimental` is added to repository dependencies with appropriate version constraints.
- **Domain Modeling & ADR Alignment**:
  ADR 0041 is superseded for development and production environments by a new ADR, and the Studio Database glossary entry in the project domain context is updated.

## Testing Decisions

- **What makes a good test**:
  Tests must exercise the external observable contract of the database service (saving messages, fetching chronological history, persisting jobs, batch ingestion order, clearing chat, and fail-fast validation behavior) without coupling to internal network drivers or implementation details.
- **Modules tested**:
  - Studio Database Engine: Verify schema initialization, chat CRUD operations, job persistence, telemetry ingestion, thread safety, and batch flushing.
  - Configuration Validator: Verify that missing credentials raise an informative error when connecting to cloud Turso, while in-memory test setups bypass credential checks.
  - Application Integration: Verify that API routes and registries operate seamlessly with the database abstraction layer.
- **Prior art**:
  Existing test suites for database persistence, job registries, and chat rollback.

## Out of Scope

- Migrating legacy historical rows from local disk databases to Turso (a fresh start approach is taken on Turso).
- Multi-region database replication routing beyond standard Turso endpoint resolution.
- Dynamic user authentication or role-based access control inside the Turso database itself.

## Further Notes

- The credentials tested and verified for this database:
  - Database URL: `libsql://software-factory-anveshak.aws-ap-south-1.turso.io`
  - Auth Token: Stored locally in `.env`.
- All production code and test files modified or created will adhere strictly to the universal file line budget of <= 500 physical lines.
