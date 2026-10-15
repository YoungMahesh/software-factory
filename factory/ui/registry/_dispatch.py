"""In-memory job registry state, thread-safe job tracking, background worker execution, and process cancellation."""

import concurrent.futures
import json
import logging
import queue
import shlex
import sys
import threading
import time
from typing import Any
import uuid
import modal

from factory.orchestrator import FACTORY_TIMEOUT_SECS
from factory.spawner import FactorySpawnConfig, create_factory_sandbox
from factory.ui.registry._milestones import STAGE_PATTERNS
from factory.ui.registry._models import (
    DEFAULT_PREVIEW_URL,
    FactoryJob,
    JobStage,
    JobStatus,
)

logger = logging.getLogger(__name__)


def _get_pkg():
    return sys.modules.get("factory.ui.registry")


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
                    try:
                        status = JobStatus(j_dict.get("status", "QUEUED"))
                    except ValueError:
                        status = JobStatus.QUEUED
                    try:
                        stage = JobStage(j_dict.get("stage", "IDLE"))
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

                    logs = self.db.get_console_logs(job.id)
                    job.logs = [l["text"] for l in logs]
                    job._next_log_line = len(job.logs) + 1

                    events = self.db.get_telemetry_events(job.id)
                    job.events = events
                    job._next_event_seq = len(job.events) + 1

                    self._jobs[job.id] = job

    def _get_effective_preview_registry(self) -> Any:
        if self.preview_registry is not None:
            return self.preview_registry
        pkg = _get_pkg()
        if pkg is not None and hasattr(pkg, "preview_registry"):
            return getattr(pkg, "preview_registry")
        from factory.ui.registry._preview import preview_registry
        return preview_registry

    def get_active_sandbox(self, repo: str) -> tuple[modal.Sandbox, str | None] | tuple[None, None]:
        """Detects if an active Unified Studio Sandbox is serving for the target repository."""
        p_reg = self._get_effective_preview_registry()
        if p_reg is not None and hasattr(p_reg, "get_active_sandbox"):
            return p_reg.get_active_sandbox(repo)
        return None, None

    def is_job_active(self, repo: str) -> bool:
        """Checks if an Assembly Line Pipeline job is currently RUNNING or QUEUED for a repository."""
        clean_repo = repo.strip()
        bare_repo = clean_repo.split("/")[-1]
        with self._lock:
            for job in self._jobs.values():
                job_bare = job.repo.strip().split("/")[-1]
                if (job.repo == clean_repo or job_bare == bare_repo) and job.status in (JobStatus.RUNNING, JobStatus.QUEUED):
                    return True
        return False

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
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [j.to_dict() for j in jobs]

    def add_listener(self, job_id: str) -> queue.Queue | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            q: queue.Queue = queue.Queue()
            job.listeners.append(q)
            return q

    def remove_listener(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and q in job.listeners:
                job.listeners.remove(q)

    def _set_stage(self, job: FactoryJob, stage: JobStage) -> None:
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

                    if event_obj.get("type") == "stage":
                        stage_name = event_obj.get("stage") or event_obj.get("data", {}).get("stage")
                        if stage_name:
                            try:
                                self._set_stage(job, JobStage(stage_name))
                            except ValueError:
                                pass

                    event_type = event_obj.get("type")
                    if event_type in ("attempt", "attempt_start"):
                        self._broadcast(job, {"event": "attempt", "data": event_obj})

                    self._broadcast(job, {"event": "agent_event", "data": event_obj})
                else:
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

                    self._broadcast(job, {"event": "log", "data": raw_line})

    def flush_buffer(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not job._line_buffer:
                return
            remaining = job._line_buffer
            job._line_buffer = ""
        self.append_log(job_id, remaining, flush=True)

    def _broadcast(self, job: FactoryJob, payload: dict[str, Any]) -> None:
        dead = []
        for q in job.listeners:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in job.listeners:
                job.listeners.remove(d)

    def cancel_job(self, job_id: str) -> bool:
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
        thread = threading.Thread(
            target=self._run_job_worker,
            args=(job_id,),
            daemon=True,
            name=f"factory-job-{job_id}",
        )
        thread.start()

    def _stream_and_wait(self, job: FactoryJob, stream_src: Any) -> int:
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
                job.status = JobStatus.SUCCESS if exit_code == 0 else JobStatus.FAILED
                if exit_code == 0:
                    job.stage = JobStage.COMPLETED
                self._broadcast(job, {"event": "status", "status": job.status.value})
                self._broadcast(job, {"event": "stage", "stage": job.stage.value})
                self._persist_job(job)

                if exit_code == 0 and is_in_sandbox:
                    self._broadcast(job, {"event": "preview_refresh", "repo": job.repo, "job_id": job.id})
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

            self.append_log(job_id, f"🚀 [DELEGATE] Active Unified Studio Sandbox detected for {job.repo}. Delegating via sandbox.exec()...\n")

            try:
                bare_repo = job.repo.strip().split("/")[-1]
                workspace_dir = f"/root/{bare_repo}"
                cmd_args = [
                    "node", "--experimental-strip-types", "/root/factory/pipeline.ts",
                    "--workspace", workspace_dir, "--feature", job.feature, "--studio",
                ]
                if job.issue:
                    cmd_args.extend(["--issue", str(job.issue)])
                if job.model:
                    cmd_args.extend(["--model", job.model])

                p_reg = self._get_effective_preview_registry()
                if p_reg is not None and hasattr(p_reg, "update_branch"):
                    target_branch = f"factory/{job.feature}" if not job.feature.startswith("factory/") else job.feature
                    p_reg.update_branch(job.repo, target_branch)

                pipeline_cmd = " ".join(shlex.quote(a) for a in cmd_args)
                exec_cmd = (
                    "if [ ! -f /root/.factory.env ]; then "
                    "echo 'ERROR: /root/.factory.env not found in sandbox' >&2; exit 1; fi; "
                    "set -a; source /root/.factory.env; set +a; "
                    f"export PYTHONUNBUFFERED=1; export STUDIO_MODE=1; exec {pipeline_cmd}"
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

        self.append_log(job_id, f"🚀 [INIT] Spawning Software Factory Sandbox for {job.repo} ({job.feature})...\n")

        pkg = _get_pkg()
        create_factory_fn = getattr(pkg, "create_factory_sandbox", create_factory_sandbox) if pkg else create_factory_sandbox

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
            sandbox = create_factory_fn(config)
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


job_registry = JobRegistry()
