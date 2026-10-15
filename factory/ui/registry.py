"""In-Memory Job Registry and Assembly Line Stage Detector.

Manages background worker execution of factory sandbox jobs, captures
streaming stdout/stderr logs into a ring buffer, detects pipeline milestones
via regular expressions, and provides sandbox termination control.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import inspect
import json
import logging
import queue
import re
import shlex

logger = logging.getLogger(__name__)
import threading
import time
from typing import Any
import uuid

import modal
from factory.orchestrator import FACTORY_TIMEOUT_SECS
from factory.spawner import (
    FactorySpawnConfig,
    PreviewSpawnConfig,
    create_factory_sandbox,
    create_preview_sandbox,
)
from factory.ui.github import (
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_scratch_metadata,
)

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


STAGE_PATTERNS = [
    (re.compile(r"Pre-flight Guard Check|assertPreflight|Stage 0", re.IGNORECASE), JobStage.PREFLIGHT),
    (re.compile(r"Stage 1: Planner Agent|runPlannerAgent|Planning implementation", re.IGNORECASE), JobStage.PLANNER),
    (re.compile(r"Stage 2: Coder Agent|runCoderAgent|Coding implementation", re.IGNORECASE), JobStage.CODER),
    (re.compile(r"Stage 3: Deterministic Verifier|verifyWorkspace|Deterministic Verification", re.IGNORECASE), JobStage.VERIFIER),
    (re.compile(r"Stage 4: Reviewer Agent|runReviewerAgent|Reviewing diff", re.IGNORECASE), JobStage.REVIEWER),
    (re.compile(r"Assembly line pipeline completed successfully|IN-CONTAINER ASSEMBLY LINE PIPELINE PASSED", re.IGNORECASE), JobStage.COMPLETED),
    (re.compile(r"active serving keep-alive state|Dev server running with PID|Launching Dev Preview Keep-Alive Daemon", re.IGNORECASE), JobStage.SERVING),
]


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


class JobRegistry:
    """Thread-safe manager for software factory test jobs."""

    def __init__(
        self,
        max_log_lines: int = 10000,
        max_events: int = 10000,
        preview_registry: Any = None,
        db: Any = None,
    ):
        self._jobs: dict[str, FactoryJob] = {}
        self._lock = threading.RLock()
        self.max_log_lines = max_log_lines
        self.max_events = max_events
        self.preview_registry = preview_registry
        self.db = db

    def _persist_job(self, job: FactoryJob) -> None:
        """Persists the job record through to the database if available."""
        if self.db is not None:
            try:
                self.db.save_job(job.to_dict())
            except Exception:
                pass

    def rehydrate(self) -> None:
        """Rehydrates recent jobs from the database on startup."""
        if self.db is None:
            return
        recent_jobs = self.db.get_recent_jobs(limit=50)
        with self._lock:
            for j_dict in recent_jobs:
                j_id = j_dict["id"]
                if j_id not in self._jobs:
                    status_val = j_dict.get("status", "QUEUED")
                    try:
                        status = JobStatus(status_val)
                    except ValueError:
                        status = JobStatus.QUEUED

                    stage_val = j_dict.get("stage", "IDLE")
                    try:
                        stage = JobStage(stage_val)
                    except ValueError:
                        stage = JobStage.IDLE

                    job = FactoryJob(
                        id=j_dict["id"],
                        repo=j_dict["repo"],
                        feature=j_dict["feature"],
                        issue=j_dict["issue"],
                        model=j_dict["model"],
                        vm=j_dict["vm"],
                        dev=j_dict["dev"],
                        preview_url=j_dict.get("preview_url"),
                        status=status,
                        stage=stage,
                        created_at=j_dict.get("created_at", time.time()),
                        started_at=j_dict.get("started_at"),
                        ended_at=j_dict.get("ended_at"),
                        exit_code=j_dict.get("exit_code"),
                        error_message=j_dict.get("error_message"),
                    )

                    # Rehydrate logs
                    logs = self.db.get_console_logs(job.id)
                    job.logs = [l["text"] for l in logs]
                    job._next_log_line = len(job.logs) + 1

                    # Rehydrate telemetry events
                    events = self.db.get_telemetry_events(job.id)
                    job.events = events
                    job._next_event_seq = len(job.events) + 1

                    self._jobs[job.id] = job

    def _get_effective_preview_registry(self) -> Any:
        if self.preview_registry is not None:
            return self.preview_registry
        return globals().get("preview_registry")

    def get_active_sandbox(self, repo: str) -> tuple[modal.Sandbox, str | None] | tuple[None, None]:
        """Detects if an active Unified Studio Sandbox is serving for the target repository."""
        p_reg = self._get_effective_preview_registry()
        if p_reg is not None and hasattr(p_reg, "get_active_sandbox"):
            return p_reg.get_active_sandbox(repo)
        return None, None

    def is_job_active(self, repo: str) -> bool:
        """Returns True if there is a running or queued Assembly Line job for the given repository."""
        clean_repo = repo.strip()
        with self._lock:
            return any(
                j.repo == clean_repo and j.status in (JobStatus.QUEUED, JobStatus.RUNNING)
                for j in self._jobs.values()
            )

    def create_job(
        self,
        repo: str,
        feature: str,
        issue: str | None = None,
        model: str = "deepseek-v4.1-flash",
        vm: bool = False,
        dev: bool = False,
    ) -> FactoryJob:
        """Creates and registers a new test job."""
        job_id = uuid.uuid4().hex[:10]
        preview_url = DEFAULT_PREVIEW_URL if dev else None
        job = FactoryJob(
            id=job_id,
            repo=repo.strip(),
            feature=feature.strip(),
            issue=issue.strip() if issue else None,
            model=model.strip(),
            vm=vm,
            dev=dev,
            preview_url=preview_url,
        )
        with self._lock:
            self._jobs[job_id] = job
        self._persist_job(job)
        return job

    def get_job(self, job_id: str) -> FactoryJob | None:
        """Retrieves a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """Returns metadata for all registered jobs ordered by creation time descending."""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [j.to_dict() for j in jobs]

    def add_listener(self, job_id: str) -> queue.Queue | None:
        """Registers a queue listener to receive live log and stage events."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            q: queue.Queue = queue.Queue()
            job.listeners.append(q)
            return q

    def remove_listener(self, job_id: str, q: queue.Queue) -> None:
        """Unregisters a queue listener."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and q in job.listeners:
                job.listeners.remove(q)

    def _set_stage(self, job: FactoryJob, stage: JobStage) -> None:
        """Updates job stage if changed and broadcasts stage transition event."""
        if job.stage != stage:
            job.stage = stage
            self._broadcast(job, {"event": "stage", "stage": stage.value})
            self._persist_job(job)

    def append_log(
        self,
        job_id: str,
        line: str,
        flush: bool = False,
        stream_type: str = "stdout",
    ) -> None:
        """Appends log text or structured telemetry, detects stages, and notifies listeners.

        Reassembles fragmented chunks, detects single-line JSON telemetry envelopes prefixed
        with '__SF_EVENT__:', records them in job.events, and broadcasts typed 'agent_event' payloads.
        Raw __SF_EVENT__: lines are stripped from job.logs. Plain-text lines are preserved
        in job.logs, checked for stage transitions, and broadcast as 'log' payloads.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            incoming = job._line_buffer + line
            job._line_buffer = ""

            if not flush:
                if "\n" in incoming:
                    parts = incoming.split("\n")
                    complete_lines = [p + "\n" for p in parts[:-1]]
                    job._line_buffer = parts[-1]
                else:
                    stripped = incoming.strip()
                    if stripped.startswith("__SF_EVENT__:"):
                        try:
                            json.loads(stripped[len("__SF_EVENT__:"):].strip())
                            complete_lines = [incoming]
                        except Exception:
                            job._line_buffer = incoming
                            complete_lines = []
                    else:
                        job._line_buffer = incoming
                        complete_lines = []
            else:
                complete_lines = [incoming] if incoming else []

            for raw_line in complete_lines:
                stripped = raw_line.strip()
                if stripped.startswith("__SF_EVENT__:"):
                    payload_str = stripped[len("__SF_EVENT__:"):].strip()
                    try:
                        event_obj = json.loads(payload_str)
                    except Exception:
                        continue

                    if not isinstance(event_obj, dict):
                        continue

                    job.add_event(event_obj, self.max_events)
                    seq = getattr(job, "_next_event_seq", len(job.events))
                    job._next_event_seq = seq + 1
                    if self.db is not None:
                        try:
                            self.db.enqueue_event(job.id, seq, event_obj)
                        except Exception:
                            pass

                    # Stage transition detection from structured telemetry
                    if event_obj.get("type") == "stage":
                        stage_name = event_obj.get("stage") or event_obj.get("data", {}).get("stage")
                        if stage_name:
                            try:
                                detected_stage = JobStage(stage_name)
                                self._set_stage(job, detected_stage)
                            except ValueError:
                                pass

                    event_type = event_obj.get("type")
                    if event_type in ("attempt", "attempt_start"):
                        self._broadcast(job, {"event": "attempt", "data": event_obj})

                    self._broadcast(job, {"event": "agent_event", "data": event_obj})
                else:
                    # Detect stage transitions from log line
                    for pattern, detected_stage in STAGE_PATTERNS:
                        if pattern.search(raw_line):
                            self._set_stage(job, detected_stage)
                            break

                    job.add_log(raw_line, self.max_log_lines)
                    line_num = getattr(job, "_next_log_line", len(job.logs))
                    job._next_log_line = line_num + 1
                    if self.db is not None:
                        try:
                            self.db.enqueue_log(job.id, line_num, raw_line, stream_type=stream_type)
                        except Exception:
                            pass

                    payload = {"event": "log", "data": raw_line}
                    self._broadcast(job, payload)

    def flush_buffer(self, job_id: str) -> None:
        """Flushes any buffered incomplete log or telemetry chunk for the job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not job._line_buffer:
                return
            remaining = job._line_buffer
            job._line_buffer = ""
        self.append_log(job_id, remaining, flush=True)

    def _broadcast(self, job: FactoryJob, payload: dict[str, Any]) -> None:
        dead_listeners = []
        for q in job.listeners:
            try:
                q.put_nowait(payload)
            except Exception:
                dead_listeners.append(q)
        for dead in dead_listeners:
            if dead in job.listeners:
                job.listeners.remove(dead)

    def cancel_job(self, job_id: str) -> bool:
        """Terminates an active or queued job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
                return False

            job._cancelled = True
            job.status = JobStatus.CANCELLED
            job.ended_at = time.time()
            sandbox_to_terminate = job.sandbox if not job.is_in_sandbox_exec else None
            self._persist_job(job)

        if sandbox_to_terminate is not None:
            try:
                sandbox_to_terminate.terminate()
            except Exception:
                pass

        self.append_log(job_id, "\n[ABORTED] Job cancelled by user.\n")
        with self._lock:
            self._broadcast(job, {"event": "status", "status": JobStatus.CANCELLED.value})
        return True

    def start_job(self, job_id: str) -> None:
        """Launches the job in a background execution thread."""
        thread = threading.Thread(
            target=self._run_job_worker,
            args=(job_id,),
            daemon=True,
            name=f"factory-job-{job_id}",
        )
        thread.start()

    def _stream_and_wait(self, job: FactoryJob, stream_src: Any) -> int:
        import concurrent.futures

        def stream_pipe(reader, stream_type="stdout"):
            try:
                for chunk in reader:
                    if job._cancelled:
                        break
                    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                    self.append_log(job.id, text, stream_type=stream_type)
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_out = executor.submit(stream_pipe, stream_src.stdout, "stdout")
            f_err = executor.submit(stream_pipe, stream_src.stderr, "stderr")
            concurrent.futures.wait([f_out, f_err])

        if hasattr(stream_src, "wait"):
            try:
                exit_code = stream_src.wait()
            except TypeError:
                stream_src.wait(raise_on_termination=False)
                exit_code = getattr(stream_src, "returncode", None)
        else:
            exit_code = getattr(stream_src, "returncode", 0)

        self.flush_buffer(job.id)
        return exit_code if exit_code is not None else getattr(stream_src, "returncode", 0)

    def _finalize_job(self, job: FactoryJob, exit_code: int, is_in_sandbox: bool = False) -> None:
        with self._lock:
            if not job._cancelled:
                job.exit_code = exit_code
                job.ended_at = time.time()
                if exit_code == 0:
                    job.status = JobStatus.SUCCESS
                    job.stage = JobStage.COMPLETED
                else:
                    job.status = JobStatus.FAILED
                self._broadcast(job, {"event": "status", "status": job.status.value})
                self._broadcast(job, {"event": "stage", "stage": job.stage.value})
                self._persist_job(job)

                if exit_code == 0 and is_in_sandbox:
                    refresh_payload = {
                        "event": "preview_refresh",
                        "repo": job.repo,
                        "job_id": job.id,
                    }
                    self._broadcast(job, refresh_payload)

                    p_reg = self._get_effective_preview_registry()
                    if p_reg is not None and hasattr(p_reg, "broadcast_refresh"):
                        p_reg.broadcast_refresh(job.repo)

    def _run_job_worker(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return

        with self._lock:
            if job._cancelled:
                return
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            self._persist_job(job)

        active_sandbox, preview_url = self.get_active_sandbox(job.repo)

        if active_sandbox is not None:
            with self._lock:
                if job._cancelled:
                    return
                job.sandbox = active_sandbox
                job.is_in_sandbox_exec = True
                job.stage = JobStage.PREFLIGHT
                if preview_url and not job.preview_url:
                    job.preview_url = preview_url
                self._broadcast(job, {"event": "status", "status": JobStatus.RUNNING.value})
                self._broadcast(job, {"event": "stage", "stage": JobStage.PREFLIGHT.value})

            self.append_log(
                job_id,
                f"🚀 [DELEGATE] Active Unified Studio Sandbox detected for {job.repo}. Delegating in-sandbox execution via sandbox.exec()...\n",
            )

            try:
                import shlex
                bare_repo = job.repo.strip().split("/")[-1]
                workspace_dir = f"/root/{bare_repo}"

                cmd_args = [
                    "node",
                    "--experimental-strip-types",
                    "/root/factory/pipeline.ts",
                    "--workspace",
                    workspace_dir,
                    "--feature",
                    job.feature,
                    "--studio",
                ]
                if job.issue:
                    cmd_args.extend(["--issue", str(job.issue)])
                if job.model:
                    cmd_args.extend(["--model", job.model])

                # Update preview branch tracking in-place
                p_reg = self._get_effective_preview_registry()
                if p_reg is not None and hasattr(p_reg, "update_branch"):
                    target_branch = f"factory/{job.feature}" if not job.feature.startswith("factory/") else job.feature
                    p_reg.update_branch(job.repo, target_branch)

                pipeline_cmd = " ".join(shlex.quote(a) for a in cmd_args)
                exec_cmd = (
                    "if [ ! -f /root/.factory.env ]; then "
                    "echo 'ERROR: /root/.factory.env not found in sandbox' >&2; exit 1; "
                    "fi; "
                    "set -a; source /root/.factory.env; set +a; "
                    f"export PYTHONUNBUFFERED=1; "
                    f"export STUDIO_MODE=1; "
                    f"exec {pipeline_cmd}"
                )

                process = active_sandbox.exec("bash", "-c", exec_cmd)
                exit_code = self._stream_and_wait(job, process)
                self._finalize_job(job, exit_code, is_in_sandbox=True)

            except Exception as e:
                with self._lock:
                    if not job._cancelled:
                        job.status = JobStatus.FAILED
                        job.error_message = str(e)
                        job.ended_at = time.time()
                        self._broadcast(job, {"event": "status", "status": JobStatus.FAILED.value})
                        self._persist_job(job)
                        self.append_log(job_id, f"\n❌ [ERROR] In-sandbox execution failed: {e}\n")
            return

        with self._lock:
            if job._cancelled:
                return
            job.stage = JobStage.PROVISIONING
            self._broadcast(job, {"event": "status", "status": JobStatus.RUNNING.value})
            self._broadcast(job, {"event": "stage", "stage": JobStage.PROVISIONING.value})

        self.append_log(
            job_id,
            f"🚀 [INIT] Spawning Software Factory Sandbox for {job.repo} ({job.feature})...\n",
        )

        try:
            config = FactorySpawnConfig(
                project=f"software-factory-09-test/{job.repo}",
                feature=job.feature,
                issue=job.issue,
                vm=job.vm,
                testing=True,
                model=job.model,
                dev=job.dev,
                timeout_secs=FACTORY_TIMEOUT_SECS,
            )

            sandbox = create_factory_sandbox(config)
            with self._lock:
                if job._cancelled:
                    try:
                        sandbox.terminate()
                    except Exception:
                        pass
                    return
                job.sandbox = sandbox

            self.append_log(job_id, f"📦 [MODAL] Sandbox created: {sandbox.object_id}\n")

            exit_code = self._stream_and_wait(job, sandbox)
            self._finalize_job(job, exit_code, is_in_sandbox=False)

        except Exception as e:
            with self._lock:
                if not job._cancelled:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.ended_at = time.time()
                    self._broadcast(job, {"event": "status", "status": JobStatus.FAILED.value})
                    self._persist_job(job)
                    self.append_log(job_id, f"\n❌ [ERROR] Execution failed: {e}\n")


# Global singleton instance
job_registry = JobRegistry()


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


PREVIEW_COMPILATION_ERROR_PATTERN = re.compile(
    r"\[vite:esbuild\]|\[vite\] Internal server error|Failed to compile|SyntaxError:|Compilation failed|error when starting dev server",
    re.IGNORECASE,
)


PREVIEW_STAGE_PATTERNS = [
    (
        re.compile(
            r"PREVIEW_STAGE:SERVING|ready in \d+|Local:\s+http|Network:\s+http|Dev server (?:running|started) on port|started on port",
            re.IGNORECASE,
        ),
        PreviewStage.SERVING,
    ),
    (
        re.compile(
            r"PREVIEW_STAGE:STARTING_DEV|Launching Dev Preview Keep-Alive Daemon|Container entering active serving keep-alive state|pnpm dev|VITE v|vite v|Dev server running with PID",
            re.IGNORECASE,
        ),
        PreviewStage.STARTING_DEV,
    ),
    (
        re.compile(
            r"PREVIEW_STAGE:INSTALLING_DEPS|Installing target repository dependencies|Installing dependencies|pnpm install|npm install|Packages: \+|Progress: resolved",
            re.IGNORECASE,
        ),
        PreviewStage.INSTALLING_DEPS,
    ),
]


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
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)
    listeners: list[queue.Queue] = field(default_factory=list)
    _stopped: bool = False
    _thread: threading.Thread | None = None
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
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_message": self.error_message,
            "logs": list(self.logs),
            "log_count": len(self.logs),
        }


def resolve_active_preview_branch(repo_name: str) -> str:
    """Resolves active branch for preview: factory/<feature> if active milestone/issue exists, else main."""
    try:
        milestones = fetch_repo_milestones(repo_name=repo_name, state="open")
        if milestones:
            first_ms = milestones[0]
            slug = first_ms.get("slug") or first_ms.get("title")
            if slug:
                return f"factory/{slug}"
    except Exception:
        pass

    try:
        issues = fetch_repo_issues(repo_name=repo_name, state="open")
        if issues:
            first_issue = issues[0]
            issue_num = first_issue.get("number")
            if issue_num is not None:
                return f"factory/issue-{issue_num}"
    except Exception:
        pass

    try:
        scratch = fetch_repo_scratch_metadata(repo_name=repo_name)
        features = scratch.get("features") or []
        if features:
            slug = features[0].get("slug")
            if slug:
                return f"factory/{slug}"
    except Exception:
        pass

    return "main"


class PreviewRegistry:
    """Thread-safe manager for Dedicated Preview Sandboxes keyed by repository."""

    def __init__(self, max_log_lines: int = 5000, db: Any = None):
        self._previews: dict[str, PreviewState] = {}
        self._lock = threading.RLock()
        self.max_log_lines = max_log_lines
        self.db = db

    def _persist_preview(self, preview: PreviewState) -> None:
        """Persists the preview state through to the database if available."""
        if self.db is not None:
            try:
                self.db.save_preview(preview.to_dict())
            except Exception:
                pass

    def rehydrate(self) -> None:
        """Rehydrates active and previous preview states from the database."""
        if self.db is None:
            return
        all_previews = self.db.get_all_previews()
        with self._lock:
            for p_dict in all_previews:
                repo = p_dict["repo"]
                if repo not in self._previews:
                    status_val = p_dict.get("status", "IDLE")
                    try:
                        status = PreviewStatus(status_val)
                    except ValueError:
                        status = PreviewStatus.IDLE

                    stage_val = p_dict.get("stage", "IDLE")
                    try:
                        stage = PreviewStage(stage_val)
                    except ValueError:
                        stage = PreviewStage.IDLE

                    state = PreviewState(
                        repo=repo,
                        branch=p_dict.get("branch", "main"),
                        preview_url=p_dict.get("preview_url"),
                        status=status,
                        stage=stage,
                        created_at=p_dict.get("updated_at", time.time()),
                    )
                    self._previews[repo] = state

    def get_preview(self, repo: str) -> PreviewState | None:
        """Retrieves current preview state for a repository."""
        with self._lock:
            return self._previews.get(repo.strip())

    def launch_preview(self, repo: str, branch: str | None = None) -> PreviewState:
        """Launches a Dedicated Preview Sandbox for the specified repository."""
        clean_repo = repo.strip()
        with self._lock:
            existing = self._previews.get(clean_repo)
            if existing and existing.status in (PreviewStatus.PROVISIONING, PreviewStatus.SERVING):
                return existing

            if branch and branch.strip():
                resolved_branch = branch.strip()
            elif existing and existing.branch:
                resolved_branch = existing.branch
            else:
                resolved_branch = resolve_active_preview_branch(clean_repo)

            preview = PreviewState(
                repo=clean_repo,
                branch=resolved_branch,
                status=PreviewStatus.PROVISIONING,
                stage=PreviewStage.PROVISIONING,
                started_at=time.time(),
            )
            self._previews[clean_repo] = preview
        self._persist_preview(preview)

        thread = threading.Thread(
            target=self._run_preview_worker,
            args=(preview,),
            daemon=True,
            name=f"preview-{clean_repo}",
        )
        preview._thread = thread
        thread.start()
        return preview

    async def stop_preview(self, repo: str) -> bool:
        """Terminates active Dedicated Preview Sandbox for a repository asynchronously."""
        clean_repo = repo.strip()
        sandbox_to_terminate = None
        with self._lock:
            preview = self._previews.get(clean_repo)
            if not preview or preview.status in (PreviewStatus.STOPPED, PreviewStatus.IDLE):
                return False

            preview._stopped = True
            preview.status = PreviewStatus.STOPPED
            preview.ended_at = time.time()
            sandbox_to_terminate = preview.sandbox
            self._persist_preview(preview)
            self._broadcast(preview, {"event": "status", "status": PreviewStatus.STOPPED.value})

        if sandbox_to_terminate is not None:
            try:
                terminate_fn = getattr(sandbox_to_terminate, "terminate", None)
                if terminate_fn is not None:
                    terminate_aio = getattr(terminate_fn, "aio", None)
                    if callable(terminate_aio):
                        result = terminate_aio()
                        if inspect.isawaitable(result):
                            await result
                    elif inspect.iscoroutinefunction(terminate_fn):
                        await terminate_fn()
                    else:
                        result = terminate_fn()
                        if inspect.isawaitable(result):
                            await result
            except Exception:
                pass

        return True

    def add_listener(self, repo: str) -> queue.Queue | None:
        with self._lock:
            preview = self._previews.get(repo.strip())
            if not preview:
                return None
            q: queue.Queue = queue.Queue()
            preview.listeners.append(q)
            return q

    def remove_listener(self, repo: str, q: queue.Queue) -> None:
        with self._lock:
            preview = self._previews.get(repo.strip())
            if preview and q in preview.listeners:
                preview.listeners.remove(q)

    def _broadcast(self, preview: PreviewState, payload: dict[str, Any]) -> None:
        dead_listeners = []
        for q in preview.listeners:
            try:
                q.put_nowait(payload)
            except Exception:
                dead_listeners.append(q)
        for dead in dead_listeners:
            if dead in preview.listeners:
                preview.listeners.remove(dead)

    def get_active_sandbox(self, repo: str) -> tuple[modal.Sandbox, str | None] | tuple[None, None]:
        """Returns (sandbox, preview_url) if an active Unified Studio Sandbox is serving for the repository."""
        clean_repo = repo.strip()
        bare_repo = clean_repo.split("/")[-1]
        with self._lock:
            for r in (clean_repo, bare_repo):
                preview = self._previews.get(r)
                if (
                    preview is not None
                    and preview.sandbox is not None
                    and preview.status == PreviewStatus.SERVING
                    and not getattr(preview, "_stopped", False)
                ):
                    return preview.sandbox, preview.preview_url
        return None, None

    async def wait_for_serving(
        self,
        repo: str,
        timeout: float = 60.0,
        poll_interval: float = 0.05,
    ) -> tuple[modal.Sandbox | None, str | None]:
        """Waits asynchronously for the repository's preview sandbox to reach SERVING status."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            sandbox, preview_url = self.get_active_sandbox(repo)
            if sandbox is not None:
                return sandbox, preview_url
            preview = self.get_preview(repo)
            if preview and preview.status in (PreviewStatus.STOPPED, PreviewStatus.FAILED):
                break
            await asyncio.sleep(poll_interval)
        return self.get_active_sandbox(repo)

    def update_branch(self, repo: str, branch: str) -> PreviewState:
        """Updates the active branch tracking for a repository preview."""
        clean_repo = repo.strip()
        clean_branch = branch.strip()
        with self._lock:
            preview = self._previews.get(clean_repo)
            if preview:
                preview.branch = clean_branch
            else:
                preview = PreviewState(
                    repo=clean_repo,
                    branch=clean_branch,
                    status=PreviewStatus.IDLE,
                    stage=PreviewStage.IDLE,
                )
                self._previews[clean_repo] = preview
            self._persist_preview(preview)
            self._broadcast(preview, {"event": "branch", "branch": clean_branch, "repo": clean_repo})
            return preview

    def switch_preview_branch(self, repo: str, branch: str) -> PreviewState:
        """Switches the active branch in an actively serving Unified Studio Sandbox in place via sandbox.exec.

        Performs a clean working tree reset (`git reset --hard && git clean -fd`), fetches remote changes,
        and checks out the target branch. Diffs in package.json or pnpm-lock.yaml trigger
        in-container `pnpm install --prefer-offline`. Broadcasts SSE branch and preview_refresh events.
        If in-container checkout or installation fails, non-destructive recovery preserves the container
        on its current branch and logs diagnostic details.
        """
        clean_repo = repo.strip()
        clean_branch = branch.strip()

        with self._lock:
            preview = self._previews.get(clean_repo)
            if not preview or preview.sandbox is None or preview.status != PreviewStatus.SERVING:
                raise RuntimeError(
                    f"No active serving preview sandbox found for repository '{clean_repo}'. "
                    "In-place branch switching requires an active Unified Studio Sandbox."
                )
            sandbox = preview.sandbox
            prev_branch = preview.branch

        bare_repo = clean_repo.split("/")[-1]
        workspace_dir = f"/root/{bare_repo}"
        q_branch = shlex.quote(clean_branch)
        q_workspace = shlex.quote(workspace_dir)

        self.append_log(
            clean_repo,
            f"🌿 Switching preview branch for {clean_repo} from '{prev_branch}' to '{clean_branch}' in place...\n",
            flush=True,
        )

        exec_cmd = (
            f"cd {q_workspace} && "
            "PREV_REV=$(git rev-parse HEAD 2>/dev/null || echo '') && "
            "PREV_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '') && "
            "rollback() { "
            "  echo '⚠️ Rolling back container working tree to previous branch state...' >&2; "
            "  if [ -n \"$PREV_BRANCH\" ] && [ \"$PREV_BRANCH\" != 'HEAD' ]; then "
            "    git checkout -f \"$PREV_BRANCH\" 2>/dev/null || true; "
            "  fi; "
            "  if [ -n \"$PREV_REV\" ]; then "
            "    git reset --hard \"$PREV_REV\" 2>/dev/null || true; "
            "    git clean -fd 2>/dev/null || true; "
            "  fi; "
            "} && "
            "trap 'rollback' ERR && "
            "set -e && "
            "echo '🧹 Cleaning working tree (git reset --hard && git clean -fd)...' && "
            "git reset --hard && git clean -fd && "
            "git fetch origin && "
            f"(git checkout {q_branch} 2>/dev/null || git checkout -b {q_branch} origin/{q_branch} 2>/dev/null || true) && "
            f"git checkout {q_branch} && git pull origin {q_branch} && "
            "TARGET_REV=$(git rev-parse HEAD 2>/dev/null || echo '') && "
            "if [ -n \"$PREV_REV\" ] && [ -n \"$TARGET_REV\" ] && [ \"$PREV_REV\" != \"$TARGET_REV\" ]; then "
            "  DIFF_FILES=$(git diff --name-only \"$PREV_REV\" \"$TARGET_REV\" -- package.json pnpm-lock.yaml 2>/dev/null || echo ''); "
            "  if [ -n \"$DIFF_FILES\" ]; then "
            "    echo '📦 Dependency changes detected in package.json/pnpm-lock.yaml. Running pnpm install --prefer-offline...'; "
            "    pnpm install --prefer-offline; "
            "  fi; "
            "fi"
        )

        try:
            process = sandbox.exec("bash", "-c", exec_cmd)
        except Exception as e:
            err_msg = f"Failed to execute branch switch in container: {e}"
            self.append_log(clean_repo, f"❌ [ERROR] {err_msg}\n", flush=True)
            raise RuntimeError(err_msg) from e

        # Stream stdout and stderr to preview logs
        import concurrent.futures
        captured_stderr: list[str] = []

        def stream_pipe(reader, is_stderr: bool = False):
            try:
                for chunk in reader:
                    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                    if is_stderr:
                        captured_stderr.append(text)
                    self.append_log(clean_repo, text)
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_out = executor.submit(stream_pipe, getattr(process, "stdout", iter([])), False)
            f_err = executor.submit(stream_pipe, getattr(process, "stderr", iter([])), True)
            concurrent.futures.wait([f_out, f_err])

        if hasattr(process, "wait"):
            try:
                exit_code = process.wait()
            except TypeError:
                process.wait(raise_on_termination=False)
                exit_code = getattr(process, "returncode", None)
        else:
            exit_code = getattr(process, "returncode", 0)

        self.flush_buffer(clean_repo)

        if exit_code is None:
            exit_code = getattr(process, "returncode", 0)

        if exit_code != 0:
            error_details = "".join(captured_stderr).strip() or f"Process exited with code {exit_code}"
            err_msg = (
                f"In-container branch switch to '{clean_branch}' failed (exit code {exit_code}): {error_details}"
            )
            self.append_log(clean_repo, f"\n❌ [ERROR] {err_msg}\n", flush=True)
            # Safe recovery: ensure preview container remains SERVING on its original branch
            with self._lock:
                preview.branch = prev_branch
                self._persist_preview(preview)
            raise RuntimeError(err_msg)

        # Success: update branch, persist, broadcast events
        with self._lock:
            preview.branch = clean_branch
            self._persist_preview(preview)
            self._broadcast(preview, {"event": "branch", "branch": clean_branch, "repo": clean_repo})

        self.broadcast_refresh(clean_repo)
        self.append_log(clean_repo, f"✅ Switched preview branch to '{clean_branch}'.\n", flush=True)
        return preview

    def broadcast_refresh(self, repo: str) -> None:
        """Broadcasts a preview_refresh event to all preview listeners for the repository."""
        clean_repo = repo.strip()
        bare_repo = clean_repo.split("/")[-1]
        seen_previews = set()
        with self._lock:
            for r in (clean_repo, bare_repo):
                preview = self._previews.get(r)
                if preview is not None and id(preview) not in seen_previews:
                    seen_previews.add(id(preview))
                    self._broadcast(preview, {"event": "preview_refresh", "repo": r})

    def sync_sandbox_to_main(self, repo: str) -> bool:
        """Synchronizes active Unified Studio Sandbox to main post-merge.

        Executes git reset --hard && git clean -fd && git checkout main && git pull origin main
        inside the running sandbox via sandbox.exec, updating preview registry branch state to main.
        """
        clean_repo = repo.strip()
        sandbox, _ = self.get_active_sandbox(clean_repo)
        if sandbox is None:
            return False

        bare_repo = clean_repo.split("/")[-1]
        workspace_dir = f"/root/{bare_repo}"
        exec_cmd = (
            f"cd {workspace_dir} && "
            "git reset --hard && "
            "git clean -fd && "
            "git checkout main && "
            "git pull origin main"
        )

        exit_code = 0
        try:
            process = sandbox.exec("bash", "-c", exec_cmd)
            if hasattr(process, "wait"):
                try:
                    exit_code = process.wait()
                except TypeError:
                    process.wait(raise_on_termination=False)
                    exit_code = getattr(process, "returncode", 0)
            else:
                exit_code = getattr(process, "returncode", 0)
        except Exception as e:
            logger.warning(f"Failed to sync sandbox for {repo} to main: {e}")
            return False

        if exit_code != 0:
            logger.warning(f"Failed to sync sandbox for {clean_repo} to main: command exited with code {exit_code}")
            return False

        self.update_branch(clean_repo, "main")
        self.broadcast_refresh(clean_repo)
        return True

    def _set_stage(self, preview: PreviewState, stage: PreviewStage) -> None:
        """Updates preview stage if changed and broadcasts stage transition event."""
        current_rank = PREVIEW_STAGE_ORDER.get(preview.stage, 0)
        target_rank = PREVIEW_STAGE_ORDER.get(stage, 0)
        if target_rank > current_rank:
            preview.stage = stage
            self._broadcast(preview, {"event": "stage", "stage": stage.value})
            if stage == PreviewStage.SERVING:
                preview.status = PreviewStatus.SERVING
                self._broadcast(preview, {
                    "event": "status",
                    "status": PreviewStatus.SERVING.value,
                    "preview_url": preview.preview_url,
                })
            self._persist_preview(preview)

    def append_log(self, repo: str, line: str, flush: bool = False) -> None:
        """Appends log line to preview ring buffer, checks stage transitions, and broadcasts."""
        with self._lock:
            preview = self._previews.get(repo.strip())
            if not preview:
                return

            complete_lines = preview.buffer_and_extract_lines(line, flush=flush)

            for raw_line in complete_lines:
                if PREVIEW_COMPILATION_ERROR_PATTERN.search(raw_line):
                    if preview.status != PreviewStatus.FAILED:
                        preview.status = PreviewStatus.FAILED
                        preview.error_message = raw_line.strip()
                        self._broadcast(preview, {
                            "event": "status",
                            "status": PreviewStatus.FAILED.value,
                            "error": preview.error_message,
                        })
                elif preview.status != PreviewStatus.FAILED:
                    for pattern, detected_stage in PREVIEW_STAGE_PATTERNS:
                        if pattern.search(raw_line):
                            self._set_stage(preview, detected_stage)
                            break

                preview.add_log(raw_line, self.max_log_lines)
                self._broadcast(preview, {"event": "log", "data": raw_line})

    def flush_buffer(self, repo: str) -> None:
        """Flushes any buffered incomplete log line for the preview."""
        self.append_log(repo, "", flush=True)

    def _run_preview_worker(self, preview: PreviewState) -> None:
        repo = preview.repo
        try:
            self.append_log(
                repo,
                f"🚀 [PREVIEW] Provisioning dedicated preview sandbox for {repo} ({preview.branch})...\n",
                flush=True,
            )
            self._broadcast(preview, {"event": "status", "status": PreviewStatus.PROVISIONING.value})
            self._broadcast(preview, {"event": "stage", "stage": PreviewStage.PROVISIONING.value})

            config = PreviewSpawnConfig(
                repo=repo,
                branch=preview.branch,
                testing=True,
            )
            sandbox, preview_url = create_preview_sandbox(config)

            with self._lock:
                if preview._stopped:
                    try:
                        sandbox.terminate()
                    except Exception:
                        pass
                    return
                preview.sandbox = sandbox
                preview.sandbox_id = getattr(sandbox, "object_id", None)
                preview.preview_url = preview_url

            self.append_log(
                repo,
                f"📡 [PREVIEW] Dedicated preview sandbox created ({preview.sandbox_id}). Live preview URL: {preview_url}\n",
                flush=True,
            )

            # Stream logs from sandbox
            import concurrent.futures

            def stream_pipe(reader):
                try:
                    for chunk in reader:
                        if preview._stopped:
                            break
                        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                        self.append_log(repo, text)
                except Exception:
                    pass

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f_out = executor.submit(stream_pipe, sandbox.stdout)
                f_err = executor.submit(stream_pipe, sandbox.stderr)
                concurrent.futures.wait([f_out, f_err])

            sandbox.wait(raise_on_termination=False)
            self.flush_buffer(repo)

            with self._lock:
                if not preview._stopped:
                    preview.ended_at = time.time()
                    if preview.status != PreviewStatus.FAILED:
                        if sandbox.returncode == 0:
                            preview.status = PreviewStatus.STOPPED
                        else:
                            preview.status = PreviewStatus.FAILED
                            preview.error_message = f"Process exited with code {sandbox.returncode}"
                    self._broadcast(preview, {
                        "event": "status",
                        "status": preview.status.value,
                        "error": preview.error_message,
                    })

        except Exception as e:
            with self._lock:
                if not preview._stopped:
                    preview.status = PreviewStatus.FAILED
                    preview.error_message = str(e)
                    preview.ended_at = time.time()
                    self._broadcast(preview, {"event": "status", "status": PreviewStatus.FAILED.value, "error": str(e)})
            self.append_log(repo, f"\n❌ [ERROR] Preview failed: {e}\n", flush=True)


# Global singleton instance
preview_registry = PreviewRegistry()

