# Spec: Factory Studio Database Persistence for Chat History and Agent Telemetry

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

Currently, Factory Studio and the Factory Testing Console maintain all conversational state, pipeline jobs, preview records, and execution telemetry in volatile memory.

This in-memory architecture causes severe operational limitations:
1. **Chat Loss on Browser Refresh**: When a developer reloads the page or navigates between views, the chat timeline, Grilling Assistant question frontiers, user answers, and approved plan cards in `AppContent` are instantly lost because they only exist in client React component state.
2. **Context Loss on Server Restart**: When the developer restarts the local FastAPI server (`python3 -m factory.ui`), all historical jobs, active preview URLs, and pipeline execution logs in `JobRegistry` and `PreviewRegistry` are wiped clean from memory.
3. **Unrecorded AI Agent Telemetry**: Detailed telemetry streams emitted by the in-sandbox Pi Agent Harness (stage transitions, tool invocations, arguments, outputs, model reasoning deltas, and stdout/stderr console lines) disappear as soon as the in-memory ring buffer expires or the container finishes. Developers cannot inspect previous runs, compare attempts, or audit past tool outputs.
4. **No Cross-Session Timeline for Target Repositories**: When switching between target repositories in the UI header, there is no persistent conversational memory associated with each project, forcing developers to restart prompts and interview rounds from scratch.

## Solution

Implement **Studio Database**—an embedded, high-performance SQLite database operating in Write-Ahead Logging (WAL) mode—to persist **Studio Chat History**, **Agent Telemetry Logs**, and job execution records for Factory Studio:

1. **Embedded SQLite Database Engine (`StudioDatabase`)**:
   - Runs SQLite with WAL mode (`PRAGMA journal_mode=WAL`), high concurrency busy timeout (`PRAGMA busy_timeout=5000`), and normal synchronization (`PRAGMA synchronous=NORMAL`).
   - Persists state locally at a gitignored disk path, requiring zero external server configuration, Docker containers, or credentials.
2. **Durable Relational Schemas**:
   - `chat_messages`: Chronological prompts, Grilling Assistant interview turns (frontiers, recommended answers, options), approved plan summaries, draft ADRs, and milestone branch associations.
   - `factory_jobs`: Complete lifecycle tracking for Assembly Line Pipeline runs (job ID, target repository, milestone slug, issue number, model, VM flag, preview URL, status, stage, exit code, error message, timestamps).
   - `job_telemetry_events`: Structured event records (stage transitions, tool calls, model thoughts/deltas) emitted across Modal container standard output.
   - `job_console_logs`: Sequential terminal console stdout/stderr lines linked to the corresponding job.
   - `previews`: Active and previous preview sandbox states per target repository.
3. **Asynchronous Log & Event Batch Ingestion**:
   - High-throughput streaming logs and telemetry events pass through an in-memory queue to guarantee zero latency penalty on real-time SSE streams.
   - A background thread flushes batched records into SQLite periodically inside single atomic transactions, preventing SQLite write lock contention.
4. **Registry Startup Rehydration**:
   - On FastAPI application startup, the job registry queries the database to rehydrate recent jobs into memory, allowing `/api/jobs` and preview URLs to survive server restarts seamlessly.
5. **REST API & TanStack Query Chat Hydration**:
   - `GET /api/studio/repos/{repo}/messages`: Fetches chronological chat history for a target repository, automatically cached and rehydrated in the React frontend via TanStack Query.
   - `DELETE /api/studio/repos/{repo}/messages`: Resets conversational history for a repository when starting a clean feature without purging historical job runs or logs.
6. **Frontend Timeline Persistence & Clear Action**:
   - The Studio chat timeline rehydrates immediately upon page load or repository switch.
   - An intuitive "Clear Chat" action in the prompt composer allows developers to wipe prompt history when switching contexts.

## User Stories

1. As a developer using Factory Studio, I want my chat conversation with the Grilling Assistant to survive browser refreshes, so that I never lose interview progress or pending question frontiers.
2. As a developer switching between multiple target repositories in the Studio header, I want each project to retain its own persistent chat history, so that I can resume work on an application without re-explaining context.
3. As a developer reviewing a past feature, I want to see previously approved plans, draft ADRs, and question answers in the timeline, so that I have a durable record of why decisions were made.
4. As a developer restarting the local Factory Studio server, I want previous assembly line jobs and active preview URLs to reload automatically, so that ongoing work is not interrupted by server restarts.
5. As a developer debugging a failed assembly line build, I want all console stdout/stderr logs and Pi Agent tool calls to be saved in the database, so that I can inspect complete failure traces after the job has stopped.
6. As a developer viewing real-time SSE logs, I want log persistence to happen asynchronously in batches, so that writing to SQLite does not introduce lag or stutter to the live terminal viewer.
7. As a developer starting a completely new feature on an existing repository, I want a "Clear Chat" button in the prompt toolbar, so that I can clear the conversation history without wiping historical job records.
8. As a developer approving a grilled plan, I want the approval event and resulting job reference to be saved to the database, so that the link between prompt discussion and pipeline run is permanently maintained.
9. As an automated test running in CI, I want Factory Studio to support an isolated in-memory SQLite database (`:memory:`), so that unit and integration tests run fast and parallel without creating leftover database files on disk.
10. As a developer working in a single-instance local environment, I want the database to use Write-Ahead Logging (WAL) mode, so that concurrent background writes and SSE reads never produce database lock errors.
11. As a developer inspecting telemetry in the Activity Drawer, I want structured telemetry events partitioned separately from raw console output, so that stage badges and tool invocations load instantly without scanning through thousands of raw log lines.
12. As a security-conscious engineer, I want the local database file ignored in version control, so that local chat transcripts and logs are never accidentally checked into Git.

## Implementation Decisions

- **Embedded SQLite with Write-Ahead Logging (WAL)**:
  Use Python's built-in `sqlite3` engine configured with `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, and `PRAGMA synchronous=NORMAL`. The database file is located at `factory/ui/data/factory_studio.db` and excluded via `.gitignore`.
- **Relational Schema Separation**:
  Separate high-volume raw console terminal output from structured agent telemetry events:
  - `chat_messages` table stores `id` (text UUID), `repo` (text), `milestone_slug` (text nullable), `issue_number` (int nullable), `role` (text), `content` (text), `turn_data_json` (text nullable), and `created_at` (float).
  - `factory_jobs` table stores job execution parameters, status, stage, exit code, error message, and lifecycle timestamps.
  - `job_telemetry_events` table stores parsed agent events (stage transitions, tool calls, reasoning tokens) with `seq` integer ordering.
  - `job_console_logs` table stores streaming lines with `line_num` ordering and `stream_type` (`stdout`/`stderr`).
  - `previews` table stores repository preview states, branches, and active preview URLs.
  Indexes are maintained on `(repo, created_at)` for messages, and `(job_id, seq)` / `(job_id, line_num)` for telemetry.
- **Asynchronous Batch Buffer Ingestion**:
  Logging methods in the job registry push lines and structured events into in-memory worker queues. A background flushing task commits batches to SQLite inside atomic transactions every 250 milliseconds or whenever 50 items accumulate, preventing lock contention and file I/O overhead.
- **Write-Through Registry Pattern**:
  The job registry maintains its in-memory lookup cache for active sandboxes and real-time listeners. On startup, it queries the database for the 50 most recent jobs to populate the in-memory cache. Mutating actions update the in-memory state and trigger asynchronous persistence to SQLite.
- **Decoupled REST Chat Hydration**:
  Add `GET /api/studio/repos/{repo}/messages` and `DELETE /api/studio/repos/{repo}/messages`. The React frontend uses TanStack Query (`useQuery({ queryKey: studioQueryKeys.messages(repo) })`) to fetch messages upon selecting a repository. New user prompts and assistant turns update the query cache and are written through to SQLite.
- **Dependency Injection for Testing**:
  The application factory function accepts an optional database instance (`create_app(db=...)`). Production uses disk SQLite; test suites inject an isolated in-memory SQLite database (`:memory:`).

## Testing Decisions

- **Good Test Criteria**:
  Tests must verify external behavioral contracts across API endpoints, database persistence across restarts, concurrent write safety, and UI hydration. Tests must NOT assert on internal SQL queries or private class properties.
- **Modules Tested**:
  1. `StudioDatabase` service: Schema creation, message persistence, query filtering by repo, job creation/update, log batch ingestion, and clear operations.
  2. `FastAPI` routes: `GET /api/studio/repos/{repo}/messages`, `DELETE /api/studio/repos/{repo}/messages`, prompt persistence in `POST /api/studio/prompt`, and approval persistence in `POST /api/studio/approve`.
  3. `JobRegistry` integration: Rehydration on initialization, async log batching, and survival across simulated restarts.
  4. Frontend components: Rehydrating chat messages on repository change, optimistic message sending, and "Clear Chat" mutation.
- **Prior Art**:
  - `tests/test_ui.py`: Existing FastAPI test suites using `starlette.testclient.TestClient`.
  - `tests/test_ui_events.py`: Existing telemetry event streaming and stage transition tests.
  - `factory/ui/frontend/src/App.test.tsx`: Existing React Testing Library tests for Studio view and drawer state.

## Out of Scope

- Multi-tenant cloud SQL (PostgreSQL/MySQL) hosting or remote database clusters.
- End-to-end full-text vector search or embedding generation across historical chat messages.
- Multi-user authentication/session isolation (Factory Studio uses single-tenant HTTP Basic Auth per deployment).
- Automatic database compaction/vacuuming triggers during active container execution.

## Further Notes

- Adheres strictly to the domain glossary in `CONTEXT.md` (`Studio Database`, `Studio Chat History`, `Agent Telemetry Log`).
- Follows the architectural decisions recorded in `docs/adr/0041-factory-studio-database-persistence.md`.
