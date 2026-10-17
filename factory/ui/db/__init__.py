"""Embedded SQLite and Cloud Turso Database Service for Factory Studio.

Provides durable persistence for chat history, job metadata, telemetry events,
terminal console logs, and active preview states using Turso (libSQL) in dev/prod
and hermetic SQLite in-memory for testing.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import queue
import sqlite3
import threading
from typing import Any

from ._schema import DEFAULT_DB_DIR, DEFAULT_DB_PATH, init_db_schema
from ._models import _row_to_job_dict, _row_to_preview_dict
from ._chat import ChatStorageMixin
from ._jobs import JobsStorageMixin
from ._preview import PreviewStorageMixin
from ._adapter import _load_env_file, _LibsqlRow, _LibsqlCursorAdapter


class StudioDatabase(ChatStorageMixin, JobsStorageMixin, PreviewStorageMixin):
    """Database persistence service supporting cloud Turso and in-memory SQLite."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        db_url: str | None = None,
        auth_token: str | None = None,
        env_file: str | Path | None = None,
    ):
        self._lock = threading.RLock()
        self._local = threading.local()
        self._connections: list[Any] = []

        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
            self._is_memory = True
            self._is_turso = False
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
            self._connections.append(self._shared_conn)
        elif db_path is not None:
            self.db_path = str(db_path)
            parent = Path(self.db_path).parent
            parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._is_turso = False
        else:
            # Development / Production Turso mode
            self.db_path = None
            self._is_memory = False
            self._is_turso = True

            _load_env_file(env_file)
            resolved_url = db_url or os.environ.get("TURSO_DATABASE_URL")
            resolved_token = auth_token or os.environ.get("TURSO_AUTH_TOKEN")

            if not resolved_url or not resolved_token:
                raise RuntimeError(
                    "Missing Turso database credentials: TURSO_DATABASE_URL and TURSO_AUTH_TOKEN "
                    "must be configured via environment variables or root .env file. "
                    "For automated test suites, initialize StudioDatabase(':memory:')."
                )

            import libsql_experimental as libsql

            self.db_url = resolved_url
            self.auth_token = resolved_token
            self._shared_conn = libsql.connect(self.db_url, auth_token=self.auth_token)
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

    def _get_connection(self) -> Any:
        if self._is_memory or self._is_turso:
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
            raw_cursor = conn.cursor()
            cursor = _LibsqlCursorAdapter(raw_cursor) if self._is_turso else raw_cursor
            try:
                yield cursor
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    raw_cursor.close()
                except Exception:
                    pass

    def init_schema(self) -> None:
        """Idempotently initializes relational schemas and indexes."""
        with self._cursor() as cur:
            init_db_schema(cur)

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


__all__ = [
    "StudioDatabase",
    "DEFAULT_DB_DIR",
    "DEFAULT_DB_PATH",
    "_row_to_job_dict",
    "_row_to_preview_dict",
    "_LibsqlRow",
    "_LibsqlCursorAdapter",
]
