"""4-stage Launch Request execution pipeline with checkpointed post-boot resume."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable

from sandbox.core import LaunchRequest, LaunchResponse

from ._models import (
    HANDOFF_TOKEN_TTL_SECONDS,
    FactoryAppRecord,
    LaunchRequestRecord,
    LaunchStatus,
    LaunchStatusResponse,
    build_direct_chat_url,
    utc_now_iso,
)
from ._sandbox_t3 import (
    ensure_project_and_start_thread,
    mint_pairing_token,
    prepare_app_workspace,
    provision_optional_database,
    resolve_provider_model,
    wait_for_t3_ready,
)
from ._store import FactoryStateStore

logger = logging.getLogger(__name__)

RESUMABLE_STEPS: tuple[LaunchStatus, ...] = (
    "scaffolding_workspace",
    "waiting_t3",
    "starting_thread",
)


class _BufferedLogFlusher:
    """Coalesces launcher log callbacks so volume commits happen at most every interval_secs."""

    def __init__(self, store: FactoryStateStore, request_id: str, *, interval_secs: float = 2.0) -> None:
        self._store = store
        self._request_id = request_id
        self._interval_secs = interval_secs
        self._pending: list[str] = []
        self._last_flush = time.monotonic()

    def append(self, line: str) -> None:
        self._pending.append(line)
        if time.monotonic() - self._last_flush >= self._interval_secs:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch = list(self._pending)
        self._pending.clear()
        self._last_flush = time.monotonic()
        try:
            self._store.modify_launch(self._request_id, lambda cur: cur.with_appended_logs(batch))
        except Exception as exc:
            logger.debug("Skipping buffered log commit for %s: %s", self._request_id, exc)


@dataclass(frozen=True)
class PipelineDeps:
    """Injected cloud and sandbox collaborators used by the Launch Request pipeline."""

    store: FactoryStateStore
    launch_fn: Callable[..., Any]
    create_db_fn: Callable[..., Any]
    terminate_quietly: Callable[..., None]
    get_running_sandbox: Callable[[str | None, str | None], Any | None]
    effective_env: Callable[[], dict[str, str]]
    no_t3_persist: bool = False


def _record_progress(
    store: FactoryStateStore,
    request_id: str,
    status: LaunchStatus,
    label: str,
    log_line: str | None = None,
) -> None:
    store.modify_launch(
        request_id,
        lambda cur: cur.with_stage(status, label, log_lines=[log_line] if log_line else None),
    )


def _assert_request_active(store: FactoryStateStore, app_id: str, request_id: str) -> None:
    current = store.get_app(app_id)
    if current is None or current.latest_request_id != request_id:
        raise RuntimeError(f"Launch Request '{request_id}' was superseded or deleted.")


def _acquire_sandbox(
    deps: PipelineDeps,
    app: FactoryAppRecord,
    launch: LaunchRequestRecord,
    flusher: _BufferedLogFlusher,
) -> tuple[Any, LaunchResponse, LaunchStatus | None, bool]:
    """Attaches to an existing live sandbox when resuming, else provisions a fresh one."""
    resume_step = launch.resume_from_step
    if resume_step in RESUMABLE_STEPS and app.sandbox_id and app.t3_url:
        existing_sb = deps.get_running_sandbox(app.sandbox_id, app.profile)
        if existing_sb is not None:
            resp = LaunchResponse(
                sandbox_id=app.sandbox_id,
                app_name=app.slug,
                sandbox_name=app.sandbox_name or app.slug,
                t3_url=app.t3_url,
            )
            _record_progress(
                deps.store,
                launch.request_id,
                resume_step,
                "Resuming on active sandbox",
                f"Reusing active sandbox {app.sandbox_id}; resuming from {resume_step}...",
            )
            return existing_sb, resp, resume_step, True
        _record_progress(
            deps.store,
            launch.request_id,
            "launching_sandbox",
            "Provisioning Modal sandbox",
            f"Previous sandbox {app.sandbox_id} stopped; launching fresh sandbox...",
        )
    else:
        _record_progress(
            deps.store, launch.request_id, "launching_sandbox", "Provisioning Modal sandbox", "Starting Modal sandbox..."
        )

    req = LaunchRequest(
        repo=None,
        name=app.slug,
        vm=app.vm,
        no_cloudflare=True,
        t3=True,
        no_t3_persist=deps.no_t3_persist,
        react_native=app.mobile_app,
        modal=False,
        profile=app.profile,
    )
    running = deps.launch_fn(req, log_cb=flusher.append)
    flusher.flush()
    sb, launch_resp = (running.sandbox, running.response) if hasattr(running, "response") else running
    if not launch_resp.t3_url:
        deps.terminate_quietly(launch_resp.sandbox_id, profile=app.profile, reason="missing_t3_url")
        raise RuntimeError("Modal sandbox did not expose a T3 Code Server tunnel URL.")
    return sb, launch_resp, None, False


def _handle_pipeline_failure(
    deps: PipelineDeps,
    app: FactoryAppRecord,
    launch: LaunchRequestRecord,
    *,
    current_step: LaunchStatus,
    sandbox_id: str | None,
    t3_url: str | None,
    exc: Exception,
) -> LaunchStatusResponse:
    err_msg = str(exc)
    logger.error("Launch Request %s failed at %s: %s", launch.request_id, current_step, err_msg)
    cur_app = deps.store.get_app(app.app_id, reload=False)
    active_for_app = cur_app is not None and cur_app.latest_request_id == launch.request_id
    preserve_sandbox = active_for_app and current_step in RESUMABLE_STEPS and bool(sandbox_id and t3_url)
    if not preserve_sandbox:
        deps.terminate_quietly(sandbox_id, profile=app.profile, reason="launch_failure")
    updated_app = deps.store.update_app_if_current_request(
        app.app_id,
        launch.request_id,
        status="failed",
        failed_step=current_step,
        sandbox_id=sandbox_id if preserve_sandbox else None,
        last_error=err_msg,
    )
    try:
        updated_launch = deps.store.modify_launch(
            launch.request_id,
            lambda cur: cur.with_stage(
                "failed",
                "Launch failed",
                log_lines=[f"Error ({current_step}): {err_msg}"],
                error=err_msg,
                failed_step=current_step,
            ),
        )
    except KeyError:
        updated_launch = launch.with_stage("failed", "Launch failed", error=err_msg, failed_step=current_step)
    return LaunchStatusResponse(request=updated_launch, app=updated_app or cur_app)


def run_launch_pipeline(
    deps: PipelineDeps,
    app: FactoryAppRecord,
    launch: LaunchRequestRecord,
) -> LaunchStatusResponse:
    """Executes the 4-stage Launch Request pipeline with step-level resume support."""
    request_id = launch.request_id
    app_dir = f"/root/{app.slug}"
    current_step: LaunchStatus = "launching_sandbox"
    sandbox_id: str | None = None
    t3_url: str | None = None
    flusher = _BufferedLogFlusher(deps.store, request_id)
    try:
        sb, launch_resp, effective_resume, reused = _acquire_sandbox(deps, app, launch, flusher)
        sandbox_id = launch_resp.sandbox_id
        t3_url = launch_resp.t3_url
        _assert_request_active(deps.store, app.app_id, request_id)
        deps.store.update_app_if_current_request(
            app.app_id, request_id, sandbox_id=sandbox_id, sandbox_name=launch_resp.sandbox_name, t3_url=t3_url
        )

        workspace_ready = app.workspace_ready if reused else False
        db_name = app.database_name if reused else None
        if not (reused and effective_resume in ("waiting_t3", "starting_thread") and workspace_ready):
            current_step = "scaffolding_workspace"
            _record_progress(
                deps.store,
                request_id,
                "scaffolding_workspace",
                "Preparing local Git workspace",
                f"Sandbox {sandbox_id} online; preparing {app_dir}...",
            )
            prepare_app_workspace(sb, app, app_dir, force=reused and not workspace_ready)
            db_name = db_name or provision_optional_database(
                sb, app, app_dir, env=deps.effective_env(), create_db_fn=deps.create_db_fn
            )
            workspace_ready = True
            deps.store.update_app_if_current_request(
                app.app_id, request_id, workspace_ready=True, database_name=db_name
            )

        if reused and effective_resume == "starting_thread" and app.environment_id and app.provider_instance_id:
            environment_id = app.environment_id
            instance_id = app.provider_instance_id
            chosen_model = app.model
            thought_level = app.thought_level
        else:
            current_step = "waiting_t3"
            _record_progress(
                deps.store, request_id, "waiting_t3", "Waiting for T3 Code Server", "Checking T3 server & model readiness..."
            )
            t3_meta = wait_for_t3_ready(sb)
            environment_id = t3_meta["environment_id"]
            instance_id, chosen_model, thought_level = resolve_provider_model(
                t3_meta, app.provider, app.model, app.thought_level
            )
            deps.store.update_app_if_current_request(
                app.app_id, request_id, environment_id=environment_id, provider_instance_id=instance_id, model=chosen_model
            )

        current_step = "starting_thread"
        _record_progress(
            deps.store,
            request_id,
            "starting_thread",
            "Starting agent thread & pairing",
            f"Registering workspace and starting thread ({instance_id}/{chosen_model})...",
        )
        thread_id, project_id = ensure_project_and_start_thread(
            sb, app, app_dir, instance_id=instance_id, model=chosen_model, thought_level=thought_level
        )
        token = mint_pairing_token(sb)
        chat_url = build_direct_chat_url(t3_url, environment_id, thread_id)
        handoff_url = build_direct_chat_url(t3_url, environment_id, thread_id, token=token)
        handoff_expires_at = utc_now_iso(offset_seconds=HANDOFF_TOKEN_TTL_SECONDS)

        updated_app = deps.store.update_app_if_current_request(
            app.app_id,
            request_id,
            status="ready",
            failed_step=None,
            workspace_ready=True,
            provider_instance_id=instance_id,
            model=chosen_model,
            sandbox_id=sandbox_id,
            sandbox_name=launch_resp.sandbox_name,
            environment_id=environment_id,
            project_id=project_id,
            thread_id=thread_id,
            t3_url=t3_url,
            chat_url=chat_url,
            database_name=db_name,
            last_error=None,
        )
        if updated_app is None:
            deps.terminate_quietly(sandbox_id, profile=app.profile, reason="superseded_ready")
            try:
                failed_launch = deps.store.modify_launch(
                    request_id,
                    lambda cur: cur.with_stage(
                        "failed", "Superseded or deleted", error="Launch Request was superseded or deleted."
                    ),
                )
                return LaunchStatusResponse(request=failed_launch, app=deps.store.get_app(app.app_id, reload=False))
            except KeyError:
                return LaunchStatusResponse(
                    request=launch.with_stage("failed", "Deleted", error="Factory App deleted during launch."),
                    app=None,
                )

        updated_launch = deps.store.modify_launch(
            request_id,
            lambda cur: cur.with_stage(
                "ready",
                "Ready — opening T3 Code",
                log_lines=[f"Ready: {chat_url}"],
                handoff_url=handoff_url,
                handoff_expires_at=handoff_expires_at,
                error=None,
            ),
        )
        return LaunchStatusResponse(request=updated_launch, app=updated_app)
    except Exception as exc:
        flusher.flush()
        return _handle_pipeline_failure(
            deps, app, launch, current_step=current_step, sandbox_id=sandbox_id, t3_url=t3_url, exc=exc
        )
