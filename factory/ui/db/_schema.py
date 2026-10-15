"""SQLite relational schema and DDL definitions for Factory Studio."""

from pathlib import Path
import sqlite3

DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "factory_studio.db"

SCHEMA_STATEMENTS = [
    # 1. Chat Messages
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        repo TEXT NOT NULL,
        milestone_slug TEXT,
        issue_number INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        turn_data_json TEXT,
        created_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_messages_repo_created
    ON chat_messages(repo, created_at ASC);
    """,
    # 2. Factory Jobs
    """
    CREATE TABLE IF NOT EXISTS factory_jobs (
        id TEXT PRIMARY KEY,
        repo TEXT NOT NULL,
        feature TEXT NOT NULL,
        issue TEXT,
        model TEXT NOT NULL,
        vm INTEGER NOT NULL DEFAULT 0,
        dev INTEGER NOT NULL DEFAULT 0,
        preview_url TEXT,
        status TEXT NOT NULL,
        stage TEXT NOT NULL,
        exit_code INTEGER,
        error_message TEXT,
        created_at REAL NOT NULL,
        started_at REAL,
        ended_at REAL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_factory_jobs_repo
    ON factory_jobs(repo, created_at DESC);
    """,
    # 3. Job Telemetry Events
    """
    CREATE TABLE IF NOT EXISTS job_telemetry_events (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        stage TEXT,
        data_json TEXT,
        created_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_job_telemetry_job_seq
    ON job_telemetry_events(job_id, seq ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_job_telemetry_created
    ON job_telemetry_events(created_at ASC);
    """,
    # 4. Job Console Logs
    """
    CREATE TABLE IF NOT EXISTS job_console_logs (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        line_num INTEGER NOT NULL,
        text TEXT NOT NULL,
        stream_type TEXT NOT NULL DEFAULT 'stdout',
        created_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_job_console_logs_job_line
    ON job_console_logs(job_id, line_num ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_job_console_logs_created
    ON job_console_logs(created_at ASC);
    """,
    # 5. Previews
    """
    CREATE TABLE IF NOT EXISTS previews (
        repo TEXT PRIMARY KEY,
        branch TEXT,
        preview_url TEXT,
        status TEXT NOT NULL,
        stage TEXT NOT NULL,
        updated_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_previews_updated
    ON previews(updated_at DESC);
    """,
]


def init_db_schema(cursor: sqlite3.Cursor) -> None:
    """Executes all schema creation statements on the given database cursor."""
    for stmt in SCHEMA_STATEMENTS:
        cursor.execute(stmt)
