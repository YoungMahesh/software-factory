# 01: Factory Studio Turso Cloud Database Persistence

**What to build:**
Migrate Factory Studio's storage engine from a local SQLite file to a cloud-hosted Turso (libSQL) database for development and production environments, while retaining hermetic in-memory SQLite (`:memory:`) for automated test suites. Connect directly over TLS via `libsql-experimental`, configure credentials (`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`) through a root `.env` file and `.env.example` template with `.gitignore` enforcement, and fail fast on startup if credentials are missing in dev/prod mode. Enhance the background batch flusher with retry backoff for network resilience. Document the transition in ADR 0058 (superseding ADR 0041 for dev/prod) and update `CONTEXT.md`.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Add `libsql-experimental>=0.0.55` to `requirements.txt`.
- [x] Add `.env*` to `.gitignore` to prevent secret commits, write `.env` containing the Turso credentials, and provide `.env.example`.
- [x] Update `StudioDatabase` in `factory/ui/db/__init__.py` to load `.env` on startup, connect directly to Turso via `libsql_experimental.connect(url, auth_token=token)` in development and production, and initialize schemas idempotently on Turso.
- [x] Validate credentials on startup in non-test mode, raising a descriptive `RuntimeError` if `TURSO_DATABASE_URL` or `TURSO_AUTH_TOKEN` is missing.
- [x] Maintain hermetic `:memory:` SQLite connections when `db_path=":memory:"` is provided, requiring no network or credentials for test suites.
- [x] Enhance `_run_batch_flusher` with retry logic and exponential backoff (up to 3 attempts) for transient remote network errors.
- [x] Create `docs/adr/0058-factory-studio-turso-cloud-database-persistence.md` documenting the transition to cloud Turso persistence and superseding ADR 0041 for dev/prod.
- [x] Update the `Studio Database` definition in `CONTEXT.md` to reflect cloud-hosted Turso persistence.
- [x] Add automated tests in `tests/test_ui_db.py` verifying fail-fast credential validation in dev/prod and confirming all existing database/app tests pass hermetically in `:memory:` mode.
