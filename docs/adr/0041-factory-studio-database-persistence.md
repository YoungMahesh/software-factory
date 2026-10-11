# Factory Studio Database Persistence for Chat History and Agent Telemetry

**Status**: Accepted

To ensure durable state across page reloads and server restarts without adding external service dependencies, we decided to implement **Studio Database** using an embedded SQLite database in Write-Ahead Logging (WAL) mode to persist **Studio Chat History**, **Agent Telemetry Logs**, and job execution records.

## Considered Options

- **Ephemeral In-Memory Registries and Client State (Prior Behavior)**: Storing chat history exclusively in React state and job logs in in-memory queues. Rejected because reloading the browser or restarting the FastAPI server wipes conversational context, question frontiers, approved plan records, and pipeline execution logs.
- **External PostgreSQL / Cloud Database**: Using an external relational database service. Rejected because Factory Studio runs as a local developer workspace and testing console; requiring PostgreSQL or Docker adds unnecessary operational friction, credentials, and network prerequisites for developers.
- **Embedded SQLite with Write-Ahead Logging (WAL)**: Using an embedded SQLite database (`factory/ui/data/factory_studio.db`) with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`. Fast, zero-dependency, self-contained, and permits concurrent SSE reading alongside asynchronous batch writes from worker processes. Accepted.

## Consequences

- The canonical domain terms **Studio Database**, **Studio Chat History**, and **Agent Telemetry Log** are incorporated into `CONTEXT.md`.
- **Database Architecture & Location**:
  - The database file resides at `factory/ui/data/factory_studio.db` (gitignored).
  - Schema initialization runs idempotently on startup with indexes on repository names, job IDs, and timestamps.
- **Database Schema**:
  - `chat_messages`: Stores user prompts, Grilling Assistant interview turns (question frontiers, recommended answers), approved plan summaries, draft ADRs, and milestone tags (`id`, `repo`, `milestone_slug`, `issue_number`, `role`, `content`, `turn_data_json`, `created_at`).
  - `factory_jobs`: Stores Assembly Line Pipeline run metadata (`id`, `repo`, `feature`, `issue`, `model`, `vm`, `dev`, `preview_url`, `status`, `stage`, `exit_code`, `error_message`, `created_at`, `started_at`, `ended_at`).
  - `job_telemetry_events`: Stores structured JSON telemetry records for stage transitions, tool calls, and LLM thoughts/deltas (`id`, `job_id`, `seq`, `event_type`, `stage`, `data_json`, `created_at`).
  - `job_console_logs`: Stores streaming raw terminal output (`id`, `job_id`, `line_num`, `text`, `stream_type`, `created_at`).
  - `previews`: Stores active and previous preview sandbox states per target repository (`repo`, `branch`, `preview_url`, `status`, `stage`, `updated_at`).
- **High-Velocity Log Ingestion**:
  - High-velocity stdout and telemetry streams pass through an in-memory queue to maintain sub-second SSE responsiveness, with a background task flushing batches into SQLite within batched transactions.
- **Frontend Hydration & Controls**:
  - `GET /api/studio/repos/{repo}/messages` allows the React frontend to rehydrate the full conversational timeline upon page load or repository selection via TanStack Query (`studioQueryKeys.messages(repo)`).
  - `DELETE /api/studio/repos/{repo}/messages` provides a "Clear Chat" action in the prompt composer toolbar to reset the conversation for new features while preserving historical job runs.
- **Registry & Testing Seams**:
  - `JobRegistry` operates as a write-through adapter, rehydrating recent jobs into memory on startup.
  - `create_app(db=...)` accepts an optional `StudioDatabase` instance, enabling test suites to inject an isolated in-memory SQLite database (`:memory:`) with zero disk footprint.
