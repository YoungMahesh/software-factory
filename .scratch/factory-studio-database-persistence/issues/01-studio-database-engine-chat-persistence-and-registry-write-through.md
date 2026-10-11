# 01: Studio Database Engine, Chat Persistence, and Registry Write-Through

**What to build:**
An embedded SQLite database service operating in Write-Ahead Logging (WAL) mode that durably persists Factory Studio chat messages, job execution records, active preview states, and agent telemetry logs across server restarts. Connect the database to the FastAPI endpoints so that user prompts, Grilling Assistant question frontiers, user responses, and plan approvals are automatically recorded and retrievable via REST. Integrate the database with the Job Registry as a write-through adapter with startup rehydration, and ingest high-velocity stdout/stderr logs and Pi Agent telemetry events asynchronously via a buffered worker without slowing down real-time SSE streaming.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] An embedded SQLite database engine (`StudioDatabase`) initializes automatically with WAL mode (`PRAGMA journal_mode=WAL`), `PRAGMA busy_timeout=5000`, and `PRAGMA synchronous=NORMAL` at `factory/ui/data/factory_studio.db` (gitignored).
- [x] Idempotent relational schemas exist for `chat_messages`, `factory_jobs`, `job_telemetry_events`, `job_console_logs`, and `previews` with indexes on repository names, job IDs, and created timestamps.
- [x] Submitting prompts via `POST /api/studio/prompt` (including fast-guard rejections, interactive Grilling Assistant question frontiers, and recommended answers) records the user prompt and assistant turn in `chat_messages`.
- [x] Approving plans via `POST /api/studio/approve` updates `chat_messages` with the approved plan status and creates a durable `factory_jobs` record linked to the target repository and synthesized issue.
- [x] `GET /api/studio/repos/{repo}/messages` returns the chronological chat message history for the requested repository, including parsed turn metadata, draft ADR info, and timestamps.
- [x] `DELETE /api/studio/repos/{repo}/messages` deletes conversational messages for the specified repository while preserving historical `factory_jobs` and telemetry logs.
- [x] `JobRegistry` rehydrates active and recent jobs from the database on startup so `/api/jobs` and preview states survive server restarts.
- [x] Streaming stdout/stderr output lines and structured telemetry events are pushed to an in-memory queue and periodically flushed into SQLite in atomic batches without degrading SSE streaming latency.
- [x] Automated tests in `tests/test_ui_db.py` and `tests/test_ui.py` verify schema initialization, CRUD operations, concurrency under WAL mode, simulated server restarts, and API endpoint behavior using an isolated in-memory SQLite database (`:memory:`).

## Answer

Implemented the embedded SQLite database engine (`StudioDatabase`) with Write-Ahead Logging (WAL) mode, relational schemas, chat history persistence, REST endpoints, and asynchronous batch ingestion:

1. **Database Service (`factory/ui/db.py`)**:
   - Implemented `StudioDatabase` with automatic WAL mode (`PRAGMA journal_mode=WAL`), busy timeout (`PRAGMA busy_timeout=5000`), and synchronous mode (`PRAGMA synchronous=NORMAL`).
   - Supports both on-disk database at `factory/ui/data/factory_studio.db` (gitignored) and in-memory databases (`:memory:`).
   - Created idempotent relational schemas and indexes for `chat_messages`, `factory_jobs`, `job_telemetry_events`, `job_console_logs`, and `previews`.
   - Built thread-safe CRUD methods for chat messages, jobs, previews, telemetry events, and console logs with normalized dictionary conversion helpers (`_row_to_job_dict`, `_row_to_preview_dict`).
   - Built an asynchronous batch queue worker (`enqueue_log`, `enqueue_event`, `flush_batches`) that writes console logs and telemetry in atomic transactions periodically or when queue size reaches 50 items.

2. **Registry Write-Through & Startup Rehydration (`factory/ui/registry.py`)**:
   - Injected `StudioDatabase` into `JobRegistry` and `PreviewRegistry`.
   - Implemented startup rehydration: jobs, preview states, console logs, and full telemetry event dictionaries are loaded from SQLite on startup.
   - Connected write-through persistence to job state transitions, cancellations, sandbox execution outcomes, and exception handlers.
   - Connected log streaming (`stdout` and `stderr`) and Pi Agent telemetry (`__SF_EVENT__:`) into asynchronous database queues without blocking real-time SSE broadcast.

3. **FastAPI Endpoints & Chat Persistence (`factory/ui/app.py`)**:
   - Added `GET /api/studio/repos/{repo}/messages` to return chronological chat history with parsed turn metadata and draft ADR info.
   - Added `DELETE /api/studio/repos/{repo}/messages` to wipe conversational chat history for a repo while preserving historical jobs and logs.
   - Persisted user prompts and assistant interview turns on `POST /api/studio/prompt` (including fast-guard rejections, interactive Grilling Assistant frontiers, and direct plan passes).
   - Persisted approved plan cards and triggered jobs on `POST /api/studio/approve`.

4. **Automated Verification**:
   - Added 10 tests in `tests/test_ui_db.py` covering WAL mode, idempotent schemas, CRUD operations, WAL concurrency, asynchronous batch flushes, and simulated server restart rehydration.
   - Added 6 tests in `tests/test_ui.py` covering message REST endpoints, prompt recording across guard outcomes, approval recording, and simulated server restart.
   - Verified that all 238 unit tests pass across the codebase.
