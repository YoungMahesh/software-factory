"""Embedded SQLite Database Service for Factory Studio.

Provides durable persistence for chat history, job metadata, telemetry events,
terminal console logs, and active preview states using SQLite with WAL mode.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
from typing import Any
import uuid

DEFAULT_DB_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "factory_studio.db"


def _row_to_job_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "repo": row["repo"],
        "feature": row["feature"],
        "issue": row["issue"],
        "model": row["model"],
        "vm": bool(row["vm"]),
        "dev": bool(row["dev"]),
        "preview_url": row["preview_url"],
        "status": row["status"],
        "stage": row["stage"],
        "exit_code": row["exit_code"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
    }


def _row_to_preview_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "repo": row["repo"],
        "branch": row["branch"],
        "preview_url": row["preview_url"],
        "status": row["status"],
        "stage": row["stage"],
        "updated_at": row["updated_at"],
    }


class StudioDatabase:
    """Thread-safe SQLite database manager operating in WAL mode."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            self.db_path = str(DEFAULT_DB_PATH)
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
            self._is_memory = True
        else:
            self.db_path = str(db_path)
            parent = Path(self.db_path).parent
            parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False

        self._lock = threading.RLock()
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []

        if self._is_memory:
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
            self._connections.append(self._shared_conn)

        self.init_schema()

        self._batch_queue: queue.Queue = queue.Queue()
        self._batch_stop_event = threading.Event()
        self._batch_flusher_thread = threading.Thread(
            target=self._run_batch_flusher,
            daemon=True,
            name="studio-db-batch-flusher",
        )
        self._batch_flusher_thread.start()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            return self._shared_conn

        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
            with self._lock:
                self._connections.append(conn)
        return conn

    @contextmanager
    def _cursor(self):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def init_schema(self) -> None:
        """Idempotently initializes SQLite relational schemas and indexes."""
        with self._cursor() as cur:
            # 1. Chat Messages
            cur.execute(
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
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_repo_created
                ON chat_messages(repo, created_at ASC);
                """
            )

            # 2. Factory Jobs
            cur.execute(
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
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_factory_jobs_repo
                ON factory_jobs(repo, created_at DESC);
                """
            )

            # 3. Job Telemetry Events
            cur.execute(
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
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_telemetry_job_seq
                ON job_telemetry_events(job_id, seq ASC);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_telemetry_created
                ON job_telemetry_events(created_at ASC);
                """
            )

            # 4. Job Console Logs
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_console_logs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    line_num INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    stream_type TEXT NOT NULL DEFAULT 'stdout',
                    created_at REAL NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_console_logs_job_line
                ON job_console_logs(job_id, line_num ASC);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_console_logs_created
                ON job_console_logs(created_at ASC);
                """
            )

            # 5. Previews
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS previews (
                    repo TEXT PRIMARY KEY,
                    branch TEXT,
                    preview_url TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_previews_updated
                ON previews(updated_at DESC);
                """
            )

    # -------------------------------------------------------------------------
    # Chat Messages CRUD
    # -------------------------------------------------------------------------

    def save_chat_message(
        self,
        repo: str,
        role: str,
        content: str,
        milestone_slug: str | None = None,
        issue_number: int | None = None,
        turn_data: dict[str, Any] | None = None,
        message_id: str | None = None,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        """Saves a conversational chat message and returns its serialized representation."""
        msg_id = message_id or str(uuid.uuid4())
        ts = created_at if created_at is not None else time.time()
        turn_data_json = json.dumps(turn_data) if turn_data is not None else None

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (id, repo, milestone_slug, issue_number, role, content, turn_data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    repo=excluded.repo,
                    milestone_slug=excluded.milestone_slug,
                    issue_number=excluded.issue_number,
                    role=excluded.role,
                    content=excluded.content,
                    turn_data_json=excluded.turn_data_json,
                    created_at=excluded.created_at;
                """,
                (msg_id, repo, milestone_slug, issue_number, role, content, turn_data_json, ts),
            )

        return {
            "id": msg_id,
            "repo": repo,
            "milestone_slug": milestone_slug,
            "issue_number": issue_number,
            "role": role,
            "content": content,
            "turn_data": turn_data,
            "created_at": ts,
        }

    def get_chat_messages(self, repo: str) -> list[dict[str, Any]]:
        """Retrieves chronological chat messages for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, milestone_slug, issue_number, role, content, turn_data_json, created_at
                FROM chat_messages
                WHERE repo = ?
                ORDER BY created_at ASC;
                """,
                (repo,),
            )
            rows = cur.fetchall()

        messages = []
        for r in rows:
            turn_data = None
            if r["turn_data_json"]:
                try:
                    turn_data = json.loads(r["turn_data_json"])
                except Exception:
                    turn_data = None

            draft_adr = turn_data.get("draft_adr") if isinstance(turn_data, dict) else None

            messages.append(
                {
                    "id": r["id"],
                    "repo": r["repo"],
                    "milestone_slug": r["milestone_slug"],
                    "issue_number": r["issue_number"],
                    "role": r["role"],
                    "content": r["content"],
                    "turn_data": turn_data,
                    "draft_adr": draft_adr,
                    "created_at": r["created_at"],
                }
            )
        return messages

    def delete_chat_messages(self, repo: str) -> int:
        """Deletes chat messages for a repository while keeping jobs and logs."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM chat_messages WHERE repo = ?;", (repo,))
            return cur.rowcount

    # -------------------------------------------------------------------------
    # Factory Jobs CRUD
    # -------------------------------------------------------------------------

    def save_job(self, job_dict: dict[str, Any]) -> None:
        """Inserts or updates a factory job record."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO factory_jobs (
                    id, repo, feature, issue, model, vm, dev, preview_url,
                    status, stage, exit_code, error_message, created_at, started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    repo=excluded.repo,
                    feature=excluded.feature,
                    issue=excluded.issue,
                    model=excluded.model,
                    vm=excluded.vm,
                    dev=excluded.dev,
                    preview_url=excluded.preview_url,
                    status=excluded.status,
                    stage=excluded.stage,
                    exit_code=excluded.exit_code,
                    error_message=excluded.error_message,
                    created_at=excluded.created_at,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at;
                """,
                (
                    job_dict["id"],
                    job_dict["repo"],
                    job_dict.get("feature", ""),
                    str(job_dict["issue"]) if job_dict.get("issue") is not None else None,
                    job_dict.get("model", ""),
                    1 if job_dict.get("vm") else 0,
                    1 if job_dict.get("dev") else 0,
                    job_dict.get("preview_url"),
                    job_dict.get("status", "QUEUED"),
                    job_dict.get("stage", "IDLE"),
                    job_dict.get("exit_code"),
                    job_dict.get("error_message"),
                    job_dict.get("created_at", time.time()),
                    job_dict.get("started_at"),
                    job_dict.get("ended_at"),
                ),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Fetches a job record by ID."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, feature, issue, model, vm, dev, preview_url,
                       status, stage, exit_code, error_message, created_at, started_at, ended_at
                FROM factory_jobs
                WHERE id = ?;
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_job_dict(row)

    def get_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieves recent jobs in descending created order."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, feature, issue, model, vm, dev, preview_url,
                       status, stage, exit_code, error_message, created_at, started_at, ended_at
                FROM factory_jobs
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()

        return [_row_to_job_dict(row) for row in rows]

    # -------------------------------------------------------------------------
    # Previews CRUD
    # -------------------------------------------------------------------------

    def save_preview(self, preview_dict: dict[str, Any]) -> None:
        """Inserts or updates preview state for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO previews (repo, branch, preview_url, status, stage, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    branch=excluded.branch,
                    preview_url=excluded.preview_url,
                    status=excluded.status,
                    stage=excluded.stage,
                    updated_at=excluded.updated_at;
                """,
                (
                    preview_dict["repo"],
                    preview_dict.get("branch"),
                    preview_dict.get("preview_url"),
                    preview_dict.get("status", "IDLE"),
                    preview_dict.get("stage", "IDLE"),
                    preview_dict.get("updated_at", time.time()),
                ),
            )

    def get_preview(self, repo: str) -> dict[str, Any] | None:
        """Fetches preview state for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, branch, preview_url, status, stage, updated_at
                FROM previews
                WHERE repo = ?;
                """,
                (repo,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_preview_dict(row)

    def get_all_previews(self) -> list[dict[str, Any]]:
        """Retrieves all preview states."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, branch, preview_url, status, stage, updated_at
                FROM previews
                ORDER BY updated_at DESC;
                """
            )
            rows = cur.fetchall()

        return [_row_to_preview_dict(row) for row in rows]

    # -------------------------------------------------------------------------
    # Telemetry Events & Console Logs CRUD
    # -------------------------------------------------------------------------

    def append_telemetry_events(self, job_id: str, events: list[dict[str, Any]]) -> None:
        """Appends a batch of telemetry events for a job."""
        if not events:
            return
        now = time.time()
        params = []
        for e in events:
            e_id = e.get("id") or str(uuid.uuid4())
            seq = e.get("seq", 0)
            event_type = e.get("type") or e.get("event_type", "unknown")
            stage = e.get("stage")
            data_json = json.dumps(e)
            ts = e.get("created_at", now)
            params.append((e_id, job_id, seq, event_type, stage, data_json, ts))

        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO job_telemetry_events (id, job_id, seq, event_type, stage, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                params,
            )

    def get_telemetry_events(self, job_id: str) -> list[dict[str, Any]]:
        """Retrieves structured telemetry events for a job ordered by seq."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, seq, event_type, stage, data_json, created_at
                FROM job_telemetry_events
                WHERE job_id = ?
                ORDER BY seq ASC;
                """,
                (job_id,),
            )
            rows = cur.fetchall()

        result = []
        for r in rows:
            event_obj = {}
            if r["data_json"]:
                try:
                    event_obj = json.loads(r["data_json"])
                except Exception:
                    event_obj = {}
            if not isinstance(event_obj, dict):
                event_obj = {"data": event_obj}
            event_obj.setdefault("id", r["id"])
            event_obj.setdefault("job_id", r["job_id"])
            event_obj.setdefault("seq", r["seq"])
            event_obj.setdefault("type", r["event_type"])
            event_obj.setdefault("event_type", r["event_type"])
            event_obj.setdefault("stage", r["stage"])
            event_obj.setdefault("created_at", r["created_at"])
            result.append(event_obj)
        return result

    def append_console_logs(
        self,
        job_id: str,
        logs: list[tuple[int, str, str] | dict[str, Any]],
    ) -> None:
        """Appends a batch of console logs for a job."""
        if not logs:
            return
        now = time.time()
        params = []
        for item in logs:
            log_id = str(uuid.uuid4())
            if isinstance(item, tuple):
                line_num, text, stream_type = item[0], item[1], item[2]
                ts = now
            else:
                line_num = item.get("line_num", 0)
                text = item.get("text", "")
                stream_type = item.get("stream_type", "stdout")
                ts = item.get("created_at", now)
            params.append((log_id, job_id, line_num, text, stream_type, ts))

        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO job_console_logs (id, job_id, line_num, text, stream_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                params,
            )

    def get_console_logs(self, job_id: str) -> list[dict[str, Any]]:
        """Retrieves raw console logs for a job ordered by line_num."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, line_num, text, stream_type, created_at
                FROM job_console_logs
                WHERE job_id = ?
                ORDER BY line_num ASC;
                """,
                (job_id,),
            )
            rows = cur.fetchall()

        return [
            {
                "id": r["id"],
                "job_id": r["job_id"],
                "line_num": r["line_num"],
                "text": r["text"],
                "stream_type": r["stream_type"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # -------------------------------------------------------------------------
    # Asynchronous Batch Queue Methods
    # -------------------------------------------------------------------------

    def enqueue_log(
        self,
        job_id: str,
        line_num: int,
        text: str,
        stream_type: str = "stdout",
    ) -> None:
        """Enqueues a console log line to be flushed asynchronously in batches."""
        self._batch_queue.put(("log", job_id, line_num, text, stream_type, time.time()))
        if self._batch_queue.qsize() >= 50:
            self.flush_batches()

    def enqueue_event(
        self,
        job_id: str,
        seq: int,
        event_dict: dict[str, Any],
    ) -> None:
        """Enqueues a structured telemetry event to be flushed asynchronously in batches."""
        self._batch_queue.put(("event", job_id, seq, event_dict, time.time()))
        if self._batch_queue.qsize() >= 50:
            self.flush_batches()

    def flush_batches(self) -> None:
        """Synchronously drains and writes all pending batch items to the database."""
        items = []
        while True:
            try:
                items.append(self._batch_queue.get_nowait())
            except queue.Empty:
                break
        if not items:
            return

        logs_by_job: dict[str, list[tuple[int, str, str]]] = {}
        events_by_job: dict[str, list[dict[str, Any]]] = {}

        for item in items:
            kind = item[0]
            if kind == "log":
                _, job_id, line_num, text, stream_type, ts = item
                logs_by_job.setdefault(job_id, []).append((line_num, text, stream_type))
            elif kind == "event":
                _, job_id, seq, event_dict, ts = item
                evt = dict(event_dict)
                evt["seq"] = seq
                evt["created_at"] = ts
                events_by_job.setdefault(job_id, []).append(evt)

        for j_id, logs in logs_by_job.items():
            self.append_console_logs(j_id, logs)
        for j_id, evts in events_by_job.items():
            self.append_telemetry_events(j_id, evts)

    def _run_batch_flusher(self) -> None:
        while not self._batch_stop_event.is_set():
            time.sleep(0.25)
            try:
                self.flush_batches()
            except Exception:
                pass

    def close(self) -> None:
        """Flushes remaining batches and closes database connections."""
        self._batch_stop_event.set()
        try:
            self.flush_batches()
        except Exception:
            pass
        if self._batch_flusher_thread.is_alive():
            self._batch_flusher_thread.join(timeout=1.0)

        with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
            if hasattr(self._local, "conn"):
                del self._local.conn

