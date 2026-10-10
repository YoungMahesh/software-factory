"""In-Memory Job Registry and Assembly Line Stage Detector.

Manages background worker execution of factory sandbox jobs, captures
streaming stdout/stderr logs into a ring buffer, detects pipeline milestones
via regular expressions, and provides sandbox termination control.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import queue
import re
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
    _cancelled: bool = False
    _line_buffer: str = ""

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
        }


class JobRegistry:
    """Thread-safe manager for software factory test jobs."""

    def __init__(self, max_log_lines: int = 10000, max_events: int = 10000):
        self._jobs: dict[str, FactoryJob] = {}
        self._lock = threading.RLock()
        self.max_log_lines = max_log_lines
        self.max_events = max_events

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

    def append_log(self, job_id: str, line: str, flush: bool = False) -> None:
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
            sandbox_to_terminate = job.sandbox

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

    def _run_job_worker(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return

        with self._lock:
            if job._cancelled:
                return
            job.status = JobStatus.RUNNING
            job.stage = JobStage.PROVISIONING
            job.started_at = time.time()
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

            # Stream logs line by line
            import concurrent.futures

            def stream_pipe(reader, is_err=False):
                try:
                    for chunk in reader:
                        if job._cancelled:
                            break
                        if isinstance(chunk, bytes):
                            text = chunk.decode("utf-8", errors="replace")
                        else:
                            text = str(chunk)
                        self.append_log(job_id, text)
                except Exception:
                    pass

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f_out = executor.submit(stream_pipe, sandbox.stdout, False)
                f_err = executor.submit(stream_pipe, sandbox.stderr, True)
                concurrent.futures.wait([f_out, f_err])

            sandbox.wait(raise_on_termination=False)
            exit_code = sandbox.returncode
            self.flush_buffer(job_id)

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

        except Exception as e:
            with self._lock:
                if not job._cancelled:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.ended_at = time.time()
                    self._broadcast(job, {"event": "status", "status": JobStatus.FAILED.value})
                    self.append_log(job_id, f"\n❌ [ERROR] Execution failed: {e}\n")


# Global singleton instance
job_registry = JobRegistry()


class PreviewStatus(str, Enum):
    IDLE = "IDLE"
    PROVISIONING = "PROVISIONING"
    SERVING = "SERVING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass
class PreviewState:
    """Represents an active or stopped Dedicated Preview Sandbox."""

    repo: str
    status: PreviewStatus = PreviewStatus.IDLE
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

    def add_log(self, line: str, max_lines: int = 5000) -> None:
        if len(self.logs) >= max_lines:
            self.logs.pop(0)
        self.logs.append(line)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "status": self.status.value,
            "branch": self.branch,
            "preview_url": self.preview_url,
            "sandbox_id": self.sandbox_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_message": self.error_message,
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

    def __init__(self, max_log_lines: int = 5000):
        self._previews: dict[str, PreviewState] = {}
        self._lock = threading.RLock()
        self.max_log_lines = max_log_lines

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

            resolved_branch = branch.strip() if branch else resolve_active_preview_branch(clean_repo)
            preview = PreviewState(
                repo=clean_repo,
                branch=resolved_branch,
                status=PreviewStatus.PROVISIONING,
                started_at=time.time(),
            )
            self._previews[clean_repo] = preview

        thread = threading.Thread(
            target=self._run_preview_worker,
            args=(preview,),
            daemon=True,
            name=f"preview-{clean_repo}",
        )
        preview._thread = thread
        thread.start()
        return preview

    def stop_preview(self, repo: str) -> bool:
        """Terminates active preview sandbox for a repository."""
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
            self._broadcast(preview, {"event": "status", "status": PreviewStatus.STOPPED.value})

        if sandbox_to_terminate is not None:
            try:
                sandbox_to_terminate.terminate()
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

    def _run_preview_worker(self, preview: PreviewState) -> None:
        repo = preview.repo
        try:
            preview.add_log(f"🚀 [PREVIEW] Provisioning dedicated preview sandbox for {repo} ({preview.branch})...\n", self.max_log_lines)
            self._broadcast(preview, {"event": "status", "status": PreviewStatus.PROVISIONING.value})

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
                preview.status = PreviewStatus.SERVING
                self._broadcast(preview, {
                    "event": "status",
                    "status": PreviewStatus.SERVING.value,
                    "preview_url": preview_url,
                })

            preview.add_log(f"📡 [PREVIEW] Live preview server serving at {preview_url}\n", self.max_log_lines)

            # Stream logs from sandbox
            import concurrent.futures

            def stream_pipe(reader):
                try:
                    for chunk in reader:
                        if preview._stopped:
                            break
                        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                        preview.add_log(text, self.max_log_lines)
                        self._broadcast(preview, {"event": "log", "data": text})
                except Exception:
                    pass

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f_out = executor.submit(stream_pipe, sandbox.stdout)
                f_err = executor.submit(stream_pipe, sandbox.stderr)
                concurrent.futures.wait([f_out, f_err])

            sandbox.wait(raise_on_termination=False)

            with self._lock:
                if not preview._stopped:
                    preview.ended_at = time.time()
                    if sandbox.returncode == 0:
                        preview.status = PreviewStatus.STOPPED
                    else:
                        preview.status = PreviewStatus.FAILED
                    self._broadcast(preview, {"event": "status", "status": preview.status.value})

        except Exception as e:
            with self._lock:
                if not preview._stopped:
                    preview.status = PreviewStatus.FAILED
                    preview.error_message = str(e)
                    preview.ended_at = time.time()
                    self._broadcast(preview, {"event": "status", "status": PreviewStatus.FAILED.value, "error": str(e)})
                    preview.add_log(f"\n❌ [ERROR] Preview failed: {e}\n", self.max_log_lines)


# Global singleton instance
preview_registry = PreviewRegistry()

