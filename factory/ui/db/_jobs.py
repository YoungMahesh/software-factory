"""Job and telemetry persistence for Factory Studio Database."""

import json
import queue
import time
from typing import Any
import uuid

from ._models import _row_to_job_dict


class JobsStorageMixin:
    """Provides factory job records, telemetry events, and console logs persistence."""

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
            try:
                self.flush_batches()
            except Exception:
                pass

    def enqueue_event(
        self,
        job_id: str,
        seq: int,
        event_dict: dict[str, Any],
    ) -> None:
        """Enqueues a structured telemetry event to be flushed asynchronously in batches."""
        self._batch_queue.put(("event", job_id, seq, event_dict, time.time()))
        if self._batch_queue.qsize() >= 50:
            try:
                self.flush_batches()
            except Exception:
                pass

    def flush_batches(self) -> None:
        """Synchronously drains and writes all pending batch items atomically to the database."""
        items = []
        while True:
            try:
                items.append(self._batch_queue.get_nowait())
            except queue.Empty:
                break
        if not items:
            return

        log_params = []
        event_params = []
        for item in items:
            kind = item[0]
            if kind == "log":
                _, job_id, line_num, text, stream_type, ts = item
                log_id = str(uuid.uuid4())
                log_params.append((log_id, job_id, line_num, text, stream_type, ts))
            elif kind == "event":
                _, job_id, seq, event_dict, ts = item
                evt_id = str(uuid.uuid4())
                event_type = event_dict.get("type") or event_dict.get("event_type") or "unknown"
                stage = event_dict.get("stage")
                data_json = json.dumps(event_dict)
                event_params.append((evt_id, job_id, seq, event_type, stage, data_json, ts))

        try:
            with self._cursor() as cur:
                if log_params:
                    cur.executemany(
                        """
                        INSERT INTO job_console_logs (id, job_id, line_num, text, stream_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        log_params,
                    )
                if event_params:
                    cur.executemany(
                        """
                        INSERT INTO job_telemetry_events (id, job_id, seq, event_type, stage, data_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        event_params,
                    )
        except Exception:
            for item in reversed(items):
                self._batch_queue.put(item)
            raise

    def _run_batch_flusher(self) -> None:
        while not self._batch_stop_event.is_set():
            time.sleep(0.25)
            for attempt in range(3):
                try:
                    self.flush_batches()
                    break
                except Exception:
                    if attempt < 2 and not self._batch_stop_event.is_set():
                        time.sleep(0.1 * (2 ** attempt))
