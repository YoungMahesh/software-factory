"""Domain models, enums, dataclasses, and state containers for jobs and previews."""

from dataclasses import dataclass, field
from enum import Enum
import queue
import threading
import time
from typing import Any
import modal

DEFAULT_PREVIEW_URL: str = "https://3000.mahesh0.dev"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStage(str, Enum):
    IDLE = "IDLE"
    PROVISIONING = "PROVISIONING"
    PREFLIGHT = "PREFLIGHT"
    PLANNER = "PLANNER"
    CODER = "CODER"
    VERIFIER = "VERIFIER"
    REVIEWER = "REVIEWER"
    COMPLETED = "COMPLETED"
    SERVING = "SERVING"


@dataclass
class FactoryJob:
    """Represents an autonomous factory test job."""

    id: str
    repo: str
    feature: str
    issue: str | None
    model: str
    vm: bool
    dev: bool = False
    preview_url: str | None = None
    status: JobStatus = JobStatus.QUEUED
    stage: JobStage = JobStage.IDLE
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    exit_code: int | None = None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    listeners: list[queue.Queue] = field(default_factory=list)
    sandbox: modal.Sandbox | None = None
    is_in_sandbox_exec: bool = False
    _cancelled: bool = False
    _line_buffer: str = ""
    _next_log_line: int = 1
    _next_event_seq: int = 1

    def add_log(self, line: str, max_lines: int) -> None:
        """Appends a log line to the logs ring buffer."""
        if len(self.logs) >= max_lines:
            self.logs.pop(0)
        self.logs.append(line)

    def add_event(self, event: dict[str, Any], max_events: int) -> None:
        """Appends a structured event to the events ring buffer."""
        if len(self.events) >= max_events:
            self.events.pop(0)
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        duration = None
        if self.started_at is not None:
            end = self.ended_at or time.time()
            duration = round(end - self.started_at, 1)

        return {
            "id": self.id,
            "repo": self.repo,
            "feature": self.feature,
            "issue": self.issue,
            "model": self.model,
            "vm": self.vm,
            "dev": self.dev,
            "preview_url": self.preview_url,
            "status": self.status.value,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration": duration,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "log_count": len(self.logs),
            "event_count": len(self.events),
            "is_in_sandbox_exec": self.is_in_sandbox_exec,
        }


class PreviewStatus(str, Enum):
    IDLE = "IDLE"
    PROVISIONING = "PROVISIONING"
    SERVING = "SERVING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class PreviewStage(str, Enum):
    IDLE = "IDLE"
    PROVISIONING = "PROVISIONING"
    INSTALLING_DEPS = "INSTALLING_DEPS"
    STARTING_DEV = "STARTING_DEV"
    SERVING = "SERVING"


PREVIEW_STAGE_ORDER: dict[PreviewStage, int] = {
    PreviewStage.IDLE: 0,
    PreviewStage.PROVISIONING: 1,
    PreviewStage.INSTALLING_DEPS: 2,
    PreviewStage.STARTING_DEV: 3,
    PreviewStage.SERVING: 4,
}


@dataclass
class PreviewState:
    """Represents an active or stopped Dedicated Preview Sandbox."""

    repo: str
    status: PreviewStatus = PreviewStatus.IDLE
    stage: PreviewStage = PreviewStage.IDLE
    branch: str = "main"
    preview_url: str | None = None
    sandbox_id: str | None = None
    sandbox: modal.Sandbox | None = None
    snapshot_image_id: str | None = None
    snapshot_commit_sha: str | None = None
    snapshot_captured_at: float | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)
    listeners: list[queue.Queue] = field(default_factory=list)
    _stopped: bool = False
    _thread: threading.Thread | None = None
    _snapshot_thread: threading.Thread | None = None
    _snapshot_in_progress: bool = False
    _line_buffer: str = ""

    def add_log(self, line: str, max_lines: int = 5000) -> None:
        if len(self.logs) >= max_lines:
            self.logs.pop(0)
        self.logs.append(line)

    def buffer_and_extract_lines(self, incoming_chunk: str, flush: bool = False) -> list[str]:
        """Appends chunk to line buffer and returns complete lines."""
        incoming = self._line_buffer + incoming_chunk
        self._line_buffer = ""
        if not flush:
            if "\n" in incoming:
                parts = incoming.split("\n")
                self._line_buffer = parts[-1]
                return [p + "\n" for p in parts[:-1]]
            else:
                self._line_buffer = incoming
                return []
        else:
            return [incoming] if incoming else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "status": self.status.value,
            "stage": self.stage.value,
            "branch": self.branch,
            "preview_url": self.preview_url,
            "sandbox_id": self.sandbox_id,
            "snapshot_image_id": self.snapshot_image_id,
            "snapshot_commit_sha": self.snapshot_commit_sha,
            "snapshot_captured_at": self.snapshot_captured_at,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_message": self.error_message,
            "logs": list(self.logs),
            "log_count": len(self.logs),
        }
