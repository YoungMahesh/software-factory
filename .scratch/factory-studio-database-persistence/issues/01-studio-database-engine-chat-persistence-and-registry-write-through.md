# 01: Studio Database Engine, Chat Persistence, and Registry Write-Through

**What to build:**
An embedded SQLite database service operating in Write-Ahead Logging (WAL) mode that durably persists Factory Studio chat messages, job execution records, active preview states, and agent telemetry logs across server restarts. Connect the database to the FastAPI endpoints so that user prompts, Grilling Assistant question frontiers, user responses, and plan approvals are automatically recorded and retrievable via REST. Integrate the database with the Job Registry as a write-through adapter with startup rehydration, and ingest high-velocity stdout/stderr logs and Pi Agent telemetry events asynchronously via a buffered worker without slowing down real-time SSE streaming.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] An embedded SQLite database engine (`StudioDatabase`) initializes automatically with WAL mode (`PRAGMA journal_mode=WAL`), `PRAGMA busy_timeout=5000`, and `PRAGMA synchronous=NORMAL` at `factory/ui/data/factory_studio.db` (gitignored).
- [ ] Idempotent relational schemas exist for `chat_messages`, `factory_jobs`, `job_telemetry_events`, `job_console_logs`, and `previews` with indexes on repository names, job IDs, and created timestamps.
- [ ] Submitting prompts via `POST /api/studio/prompt` (including fast-guard rejections, interactive Grilling Assistant question frontiers, and recommended answers) records the user prompt and assistant turn in `chat_messages`.
- [ ] Approving plans via `POST /api/studio/approve` updates `chat_messages` with the approved plan status and creates a durable `factory_jobs` record linked to the target repository and synthesized issue.
- [ ] `GET /api/studio/repos/{repo}/messages` returns the chronological chat message history for the requested repository, including parsed turn metadata, draft ADR info, and timestamps.
- [ ] `DELETE /api/studio/repos/{repo}/messages` deletes conversational messages for the specified repository while preserving historical `factory_jobs` and telemetry logs.
- [ ] `JobRegistry` rehydrates active and recent jobs from the database on startup so `/api/jobs` and preview states survive server restarts.
- [ ] Streaming stdout/stderr output lines and structured telemetry events are pushed to an in-memory queue and periodically flushed into SQLite in atomic batches without degrading SSE streaming latency.
- [ ] Automated tests in `tests/test_ui_db.py` and `tests/test_ui.py` verify schema initialization, CRUD operations, concurrency under WAL mode, simulated server restarts, and API endpoint behavior using an isolated in-memory SQLite database (`:memory:`).
