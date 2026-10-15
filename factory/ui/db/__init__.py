"""Embedded SQLite Database Service for Factory Studio.

Provides durable persistence for chat history, job metadata, telemetry events,
terminal console logs, and active preview states using SQLite with WAL mode.
"""

from contextlib import contextmanager
from pathlib import Path
import queue
import sqlite3
import threading

from ._schema import DEFAULT_DB_DIR, DEFAULT_DB_PATH, init_db_schema
from ._models import _row_to_job_dict, _row_to_preview_dict
from ._chat import ChatStorageMixin
from ._jobs import JobsStorageMixin
from ._preview import PreviewStorageMixin


class StudioDatabase(ChatStorageMixin, JobsStorageMixin, PreviewStorageMixin):
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
]
