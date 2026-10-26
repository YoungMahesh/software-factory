"""Dedicated Preview Sandbox lifecycle manager, branch switching, and log streaming."""

import asyncio
import concurrent.futures
import inspect
import logging
import queue
import shlex
import sys
import threading
import time
from typing import Any
import modal

from factory.spawner import PreviewSpawnConfig, create_preview_sandbox
from factory.ui.github import (
    fetch_repo_issues,
    fetch_repo_milestones,
)
from factory.ui.registry._milestones import (
    PREVIEW_COMPILATION_ERROR_PATTERN,
    PREVIEW_STAGE_PATTERNS,
)
from factory.ui.registry._models import (
    PREVIEW_STAGE_ORDER,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)
from factory.ui.registry._snapshot import (
    spawn_preview_sandbox_with_fallback,
    trigger_background_snapshot,
)

logger = logging.getLogger(__name__)


def _get_pkg():
    return sys.modules.get("factory.ui.registry")


def resolve_active_preview_branch(repo_name: str) -> str:
    """Resolves active branch for preview: factory/<feature> if active milestone/issue exists, else main."""
    pkg = _get_pkg()
    fetch_ms_fn = getattr(pkg, "fetch_repo_milestones", fetch_repo_milestones) if pkg else fetch_repo_milestones
    fetch_iss_fn = getattr(pkg, "fetch_repo_issues", fetch_repo_issues) if pkg else fetch_repo_issues

    try:
        milestones = fetch_ms_fn(repo_name=repo_name, state="open")
        if milestones and (milestones[0].get("slug") or milestones[0].get("title")):
            return f"factory/{milestones[0].get('slug') or milestones[0].get('title')}"
    except Exception:
        pass

    try:
        issues = fetch_iss_fn(repo_name=repo_name, state="open")
        if issues and issues[0].get("number") is not None:
            return f"factory/issue-{issues[0]['number']}"
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
        if self.db is not None:
            try:
                self.db.save_preview(preview.to_dict())
            except Exception:
                pass

    def rehydrate(self) -> None:
        if self.db is None:
            return
        with self._lock:
            for p_dict in self.db.get_all_previews():
                repo = p_dict["repo"]
                if repo not in self._previews:
                    status = PreviewStatus.IDLE
                    stage = PreviewStage.IDLE
                    try:
                        status = PreviewStatus(p_dict.get("status", "IDLE"))
                        stage = PreviewStage(p_dict.get("stage", "IDLE"))
                    except ValueError:
                        pass
                    self._previews[repo] = PreviewState(
                        repo=repo,
                        branch=p_dict.get("branch", "main"),
                        preview_url=p_dict.get("preview_url"),
                        status=status,
                        stage=stage,
                        snapshot_image_id=p_dict.get("snapshot_image_id"),
                        snapshot_commit_sha=p_dict.get("snapshot_commit_sha"),
                        snapshot_captured_at=p_dict.get("snapshot_captured_at"),
                        created_at=p_dict.get("updated_at", time.time()),
                    )

    def get_preview(self, repo: str) -> PreviewState | None:
        with self._lock:
            return self._previews.get(repo.strip())

    def launch_preview(self, repo: str, branch: str | None = None) -> PreviewState:
        clean_repo = repo.strip()
        with self._lock:
            existing = self._previews.get(clean_repo)
            if existing and existing.status in (PreviewStatus.PROVISIONING, PreviewStatus.SERVING):
                return existing

            resolved_branch = branch.strip() if branch and branch.strip() else (
                existing.branch if existing and existing.branch else resolve_active_preview_branch(clean_repo)
            )
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
        clean_repo = repo.strip()
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
                term_fn = getattr(sandbox_to_terminate, "terminate", None)
                if term_fn is not None:
                    aio_fn = getattr(term_fn, "aio", None)
                    res = aio_fn() if callable(aio_fn) else (term_fn() if inspect.iscoroutinefunction(term_fn) else term_fn())
                    if inspect.isawaitable(res):
                        await res
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
        dead = []
        for q in preview.listeners:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in preview.listeners:
                preview.listeners.remove(d)

    def get_active_sandbox(self, repo: str) -> tuple[modal.Sandbox, str | None] | tuple[None, None]:
        clean_repo = repo.strip()
        bare_repo = clean_repo.split("/")[-1]
        with self._lock:
            for r in (clean_repo, bare_repo):
                preview = self._previews.get(r)
                if preview and preview.sandbox and preview.status == PreviewStatus.SERVING and not getattr(preview, "_stopped", False):
                    return preview.sandbox, preview.preview_url
        return None, None

    async def wait_for_serving(
        self, repo: str, timeout: float = 60.0, poll_interval: float = 0.05
    ) -> tuple[modal.Sandbox | None, str | None]:
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

    def wait_for_serving_sync(
        self, repo: str, timeout: float = 60.0, poll_interval: float = 0.05
    ) -> tuple[modal.Sandbox | None, str | None]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            sandbox, preview_url = self.get_active_sandbox(repo)
            if sandbox is not None:
                return sandbox, preview_url
            preview = self.get_preview(repo)
            if preview and preview.status in (PreviewStatus.STOPPED, PreviewStatus.FAILED):
                break
            time.sleep(poll_interval)
        return self.get_active_sandbox(repo)

    def update_branch(self, repo: str, branch: str) -> PreviewState:
        clean_repo, clean_branch = repo.strip(), branch.strip()
        with self._lock:
            preview = self._previews.get(clean_repo)
            if preview:
                preview.branch = clean_branch
            else:
                preview = PreviewState(repo=clean_repo, branch=clean_branch, status=PreviewStatus.IDLE, stage=PreviewStage.IDLE)
                self._previews[clean_repo] = preview
            self._persist_preview(preview)
            self._broadcast(preview, {"event": "branch", "branch": clean_branch, "repo": clean_repo})
            return preview

    def switch_preview_branch(self, repo: str, branch: str) -> PreviewState:
        clean_repo, clean_branch = repo.strip(), branch.strip()
        with self._lock:
            preview = self._previews.get(clean_repo)
            if not preview or preview.sandbox is None or preview.status != PreviewStatus.SERVING:
                raise RuntimeError(
                    f"No active serving preview sandbox found for repository '{clean_repo}'. "
                    "In-place branch switching requires an active Unified Studio Sandbox."
                )
            sandbox = preview.sandbox
            prev_branch = preview.branch

        q_branch = shlex.quote(clean_branch)
        q_workspace = shlex.quote(f"/root/{clean_repo.split('/')[-1]}")
        self.append_log(clean_repo, f"🌿 Switching preview branch for {clean_repo} from '{prev_branch}' to '{clean_branch}' in place...\n", flush=True)

        exec_cmd = (
            f"cd {q_workspace} && PREV_REV=$(git rev-parse HEAD 2>/dev/null || echo '') && "
            "PREV_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '') && "
            "rollback() { echo '⚠️ Rolling back container tree...' >&2; "
            "[ -n \"$PREV_BRANCH\" ] && [ \"$PREV_BRANCH\" != 'HEAD' ] && git checkout -f \"$PREV_BRANCH\" 2>/dev/null || true; "
            "[ -n \"$PREV_REV\" ] && git reset --hard \"$PREV_REV\" 2>/dev/null && git clean -fd 2>/dev/null || true; } && "
            "trap 'rollback' ERR && set -e && echo '🧹 Cleaning working tree...' && git reset --hard && git clean -fd && git fetch origin && "
            f"(git checkout {q_branch} 2>/dev/null || git checkout -b {q_branch} origin/{q_branch} 2>/dev/null || true) && "
            f"git checkout {q_branch} && git pull origin {q_branch} && TARGET_REV=$(git rev-parse HEAD 2>/dev/null || echo '') && "
            "if [ -n \"$PREV_REV\" ] && [ -n \"$TARGET_REV\" ] && [ \"$PREV_REV\" != \"$TARGET_REV\" ]; then "
            "  DIFF_FILES=$(git diff --name-only \"$PREV_REV\" \"$TARGET_REV\" -- package.json pnpm-lock.yaml 2>/dev/null || echo ''); "
            "  if [ -n \"$DIFF_FILES\" ]; then echo '📦 Running pnpm install...'; pnpm install --prefer-offline; fi; "
            "fi"
        )

        try:
            process = sandbox.exec("bash", "-c", exec_cmd)
        except Exception as e:
            err_msg = f"Failed to execute branch switch in container: {e}"
            self.append_log(clean_repo, f"❌ [ERROR] {err_msg}\n", flush=True)
            raise RuntimeError(err_msg) from e

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
        exit_code = exit_code if exit_code is not None else getattr(process, "returncode", 0)

        if exit_code != 0:
            err_msg = f"In-container branch switch to '{clean_branch}' failed (exit code {exit_code}): {''.join(captured_stderr).strip()}"
            self.append_log(clean_repo, f"\n❌ [ERROR] {err_msg}\n", flush=True)
            with self._lock:
                preview.branch = prev_branch
                self._persist_preview(preview)
            raise RuntimeError(err_msg)

        with self._lock:
            preview.branch = clean_branch
            self._persist_preview(preview)
            self._broadcast(preview, {"event": "branch", "branch": clean_branch, "repo": clean_repo})

        self.broadcast_refresh(clean_repo)
        self.append_log(clean_repo, f"✅ Switched preview branch to '{clean_branch}'.\n", flush=True)
        return preview

    def record_target_branch(self, repo: str, branch: str) -> PreviewState:
        clean_repo = repo.strip()
        with self._lock:
            preview = self._previews.get(clean_repo)
            if preview is None:
                preview = PreviewState(repo=clean_repo, branch=branch, status=PreviewStatus.IDLE, stage=PreviewStage.IDLE)
                self._previews[clean_repo] = preview
            else:
                preview.branch = branch
        self._persist_preview(preview)
        return preview

    def broadcast_branch(self, repo: str, branch: str) -> None:
        clean_repo = repo.strip()
        seen = set()
        with self._lock:
            for r in (clean_repo, clean_repo.split("/")[-1]):
                p = self._previews.get(r)
                if p and id(p) not in seen:
                    seen.add(id(p))
                    self._broadcast(p, {"event": "branch", "branch": branch})

    def broadcast_refresh(self, repo: str) -> None:
        clean_repo = repo.strip()
        seen = set()
        with self._lock:
            for r in (clean_repo, clean_repo.split("/")[-1]):
                p = self._previews.get(r)
                if p and id(p) not in seen:
                    seen.add(id(p))
                    self._broadcast(p, {"event": "preview_refresh", "repo": r})

    def sync_sandbox_to_main(self, repo: str) -> bool:
        clean_repo = repo.strip()
        sandbox, _ = self.get_active_sandbox(clean_repo)
        if sandbox is None:
            return False

        q_workspace = shlex.quote(f"/root/{clean_repo.split('/')[-1]}")
        exec_cmd = f"cd {q_workspace} && git reset --hard && git clean -fd && git checkout main && git pull origin main"
        try:
            process = sandbox.exec("bash", "-c", exec_cmd)
            exit_code = process.wait() if hasattr(process, "wait") else getattr(process, "returncode", 0)
        except Exception as e:
            logger.warning(f"Failed to sync sandbox for {repo} to main: {e}")
            return False

        if exit_code != 0:
            return False

        self.update_branch(clean_repo, "main")
        self.broadcast_refresh(clean_repo)
        return True

    def _set_stage(self, preview: PreviewState, stage: PreviewStage) -> None:
        if PREVIEW_STAGE_ORDER.get(stage, 0) > PREVIEW_STAGE_ORDER.get(preview.stage, 0):
            preview.stage = stage
            self._broadcast(preview, {"event": "stage", "stage": stage.value})
            if stage == PreviewStage.SERVING:
                preview.status = PreviewStatus.SERVING
                self._broadcast(preview, {"event": "status", "status": PreviewStatus.SERVING.value, "preview_url": preview.preview_url})
                self._trigger_background_snapshot(preview)
            self._persist_preview(preview)

    def _trigger_background_snapshot(self, preview: PreviewState) -> threading.Thread | None:
        try:
            return trigger_background_snapshot(preview, db=self.db)
        except Exception as e:
            logger.warning("Failed to trigger background snapshot for %s: %s", preview.repo, e)
            return None

    def append_log(self, repo: str, line: str, flush: bool = False) -> None:
        with self._lock:
            preview = self._previews.get(repo.strip())
            if not preview:
                return

            for raw_line in preview.buffer_and_extract_lines(line, flush=flush):
                if PREVIEW_COMPILATION_ERROR_PATTERN.search(raw_line):
                    if preview.status != PreviewStatus.FAILED:
                        preview.status = PreviewStatus.FAILED
                        preview.error_message = raw_line.strip()
                        self._broadcast(preview, {"event": "status", "status": PreviewStatus.FAILED.value, "error": preview.error_message})
                elif preview.status != PreviewStatus.FAILED:
                    for pattern, detected_stage in PREVIEW_STAGE_PATTERNS:
                        if pattern.search(raw_line):
                            self._set_stage(preview, detected_stage)
                            break

                preview.add_log(raw_line, self.max_log_lines)
                self._broadcast(preview, {"event": "log", "data": raw_line})

    def flush_buffer(self, repo: str) -> None:
        self.append_log(repo, "", flush=True)

    def _run_preview_worker(self, preview: PreviewState) -> None:
        repo = preview.repo
        pkg = _get_pkg()
        create_preview_fn = getattr(pkg, "create_preview_sandbox", create_preview_sandbox) if pkg else create_preview_sandbox

        try:
            self.append_log(repo, f"🚀 [PREVIEW] Provisioning dedicated preview sandbox for {repo} ({preview.branch})...\n", flush=True)
            self._broadcast(preview, {"event": "status", "status": PreviewStatus.PROVISIONING.value})
            self._broadcast(preview, {"event": "stage", "stage": PreviewStage.PROVISIONING.value})

            sandbox, preview_url = spawn_preview_sandbox_with_fallback(
                create_preview_fn=create_preview_fn,
                repo=repo,
                branch=preview.branch,
                db=self.db,
                preview=preview,
                on_log=lambda m: self.append_log(repo, m, flush=True),
            )

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

            self.append_log(repo, f"📡 [PREVIEW] Dedicated preview sandbox created ({preview.sandbox_id}). Live preview URL: {preview_url}\n", flush=True)

            def stream_pipe(reader):
                try:
                    for chunk in reader:
                        if preview._stopped:
                            break
                        self.append_log(repo, chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
                    self.flush_buffer(repo)
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
                    self._broadcast(preview, {"event": "status", "status": preview.status.value, "error": preview.error_message})

        except Exception as e:
            with self._lock:
                if not preview._stopped:
                    preview.status = PreviewStatus.FAILED
                    preview.error_message = str(e)
                    preview.ended_at = time.time()
                    self._broadcast(preview, {"event": "status", "status": PreviewStatus.FAILED.value, "error": str(e)})
            self.append_log(repo, f"\n❌ [ERROR] Preview failed: {e}\n", flush=True)


preview_registry = PreviewRegistry()
