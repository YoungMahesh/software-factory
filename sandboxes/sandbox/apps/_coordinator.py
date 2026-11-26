"""Durable Launch Coordinator for provisioning Factory Apps into T3 Web Chat."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable
import uuid

import modal

from sandbox.config import resolve_factory_credentials
from sandbox.core import LaunchRequest
from sandbox.db_host import create_database_connection
from sandbox.launcher import launch_sandbox
from sandbox.lifecycle import terminate_sandbox
from sandbox.profiles import get_client_for_profile
from sandbox.snapshots import list_snapshots

from ._models import (
    DEFAULT_ANTIGRAVITY_MODELS,
    DEFAULT_BUILDER_MODEL,
    DEFAULT_BUILDER_PROVIDER,
    HANDOFF_TOKEN_TTL_SECONDS,
    CreateAppPayload,
    FactoryAppRecord,
    FactoryAppView,
    LaunchRequestRecord,
    LaunchStatus,
    LaunchStatusResponse,
    ModelChoice,
    OpenAppResponse,
    build_direct_chat_url,
    derive_app_slug,
    derive_app_title,
    initial_launch_steps,
    utc_now_iso,
)
from ._sandbox_t3 import (
    ensure_blank_git_workspace,
    ensure_project_and_start_thread,
    exec_in_sandbox,
    mint_pairing_token,
    provision_optional_database,
    resolve_provider_model,
    wait_for_t3_ready,
)
from ._store import FactoryStateStore, get_default_store

logger = logging.getLogger(__name__)


class AppNotFoundError(Exception):
    """Raised when a Factory App or Launch Request does not exist."""


class AppNotReadyError(Exception):
    """Raised when a Factory App has not yet completed provisioning."""


class AppSandboxStoppedError(Exception):
    """Raised when a Factory App's ephemeral sandbox has stopped."""

    def __init__(self, app_id: str, snapshot_image_id: str | None = None, snapshot_name: str | None = None) -> None:
        super().__init__(f"Sandbox for Factory App '{app_id}' is stopped.")
        self.app_id = app_id
        self.snapshot_image_id = snapshot_image_id
        self.snapshot_name = snapshot_name


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


class LaunchCoordinator:
    """Orchestrates Factory App creation, T3 handoff, reopen, relaunch, and cleanup."""

    def __init__(
        self,
        store: FactoryStateStore | None = None,
        *,
        launch_fn: Callable[..., Any] | None = None,
        create_db_fn: Callable[..., Any] | None = None,
        terminate_fn: Callable[..., dict[str, Any]] | None = None,
        list_snapshots_fn: Callable[..., list[dict[str, Any]]] | None = None,
        client_for_profile_fn: Callable[[str], Any] | None = None,
        sandbox_from_id_fn: Callable[..., Any] | None = None,
        env: dict[str, str] | None = None,
        no_t3_persist: bool = False,
    ) -> None:
        self.store = store or get_default_store()
        self.launch_fn = launch_fn or launch_sandbox
        self.create_db_fn = create_db_fn or create_database_connection
        self.terminate_fn = terminate_fn or terminate_sandbox
        self.list_snapshots_fn = list_snapshots_fn or list_snapshots
        self.client_for_profile_fn = client_for_profile_fn or get_client_for_profile
        self.sandbox_from_id_fn = sandbox_from_id_fn or modal.Sandbox.from_id
        self.env = env
        self.no_t3_persist = no_t3_persist

    def _effective_env(self) -> dict[str, str]:
        if self.env is not None:
            return dict(self.env)
        creds = resolve_factory_credentials(mutate_environ=False)
        return {**creds.extra_env, **os.environ}

    def list_available_models(self) -> list[ModelChoice]:
        """Returns advertised builder model choices based on factory configuration."""
        models = list(DEFAULT_ANTIGRAVITY_MODELS)
        env = self._effective_env()
        if env.get("OPENCODE_GO_API_KEY"):
            models.append(ModelChoice(provider="opencode", model="default", label="OpenCode · Default"))
        if env.get("CODEX_PROFILE_VOLUME_PREFIX"):
            models.append(ModelChoice(provider="codex", model="gpt-5.4", label="Codex · Default"))
        return models

    def create_and_dispatch(
        self,
        payload: CreateAppPayload,
        dispatch_fn: Callable[[str], None] | None = None,
    ) -> tuple[FactoryAppRecord, LaunchRequestRecord]:
        """Persists a new Factory App + queued Launch Request and triggers background execution."""
        existing_slugs = {item.slug for item in self.store.list_apps()}
        slug = derive_app_slug(payload.prompt, payload.name, existing_slugs=existing_slugs)
        title = derive_app_title(payload.prompt, payload.name)
        app_id = f"app_{uuid.uuid4().hex[:12]}"
        request_id = f"req_{uuid.uuid4().hex[:12]}"

        app = FactoryAppRecord(
            app_id=app_id,
            slug=slug,
            title=title,
            prompt=payload.prompt,
            template=payload.template,
            mobile_app=payload.mobile_app,
            vm=payload.vm,
            profile=payload.profile or None,
            provider=payload.provider or DEFAULT_BUILDER_PROVIDER,
            model=payload.model or DEFAULT_BUILDER_MODEL,
            thought_level=payload.thought_level or None,
            status="provisioning",
            latest_request_id=request_id,
        )
        launch = LaunchRequestRecord(
            request_id=request_id,
            app_id=app_id,
            kind="create",
            status="queued",
            current_label="Queued launch request",
            steps=initial_launch_steps(),
        )
        saved_app, saved_launch = self.store.create_app_and_launch(app, launch)
        if dispatch_fn is not None:
            dispatch_fn(saved_launch.request_id)
        return saved_app, saved_launch

    def relaunch_factory_app(
        self,
        app_id: str,
        dispatch_fn: Callable[[str], None] | None = None,
    ) -> tuple[FactoryAppRecord, LaunchRequestRecord]:
        """Creates a new Launch Request from an existing Factory App's saved prompt."""
        app = self.store.get_app(app_id)
        if app is None:
            raise AppNotFoundError(f"Factory App '{app_id}' not found.")
        if app.sandbox_id and self._get_running_sandbox(app.sandbox_id, app.profile) is not None:
            self._terminate_quietly(app.sandbox_id, profile=app.profile, reason="relaunch")

        request_id = f"req_{uuid.uuid4().hex[:12]}"
        updated_app = app.model_copy(
            update={
                "status": "provisioning",
                "latest_request_id": request_id,
                "sandbox_id": None,
                "sandbox_name": None,
                "environment_id": None,
                "project_id": None,
                "thread_id": None,
                "t3_url": None,
                "chat_url": None,
                "last_error": None,
            }
        )
        launch = LaunchRequestRecord(
            request_id=request_id,
            app_id=app.app_id,
            kind="relaunch",
            status="queued",
            current_label="Queued relaunch request",
            steps=initial_launch_steps(),
        )
        saved_app, saved_launch = self.store.create_app_and_launch(updated_app, launch)
        if dispatch_fn is not None:
            dispatch_fn(saved_launch.request_id)
        return saved_app, saved_launch

    def _record_progress(self, request_id: str, status: LaunchStatus, label: str, log_line: str | None = None) -> None:
        self.store.modify_launch(
            request_id,
            lambda cur: cur.with_stage(status, label, log_lines=[log_line] if log_line else None),
        )

    def _terminate_quietly(self, sandbox_id: str | None, *, profile: str | None, reason: str) -> None:
        if not sandbox_id:
            return
        try:
            self.terminate_fn(sandbox_id, profile=profile)
        except Exception as exc:
            logger.warning("Failed terminating sandbox %s during %s: %s", sandbox_id, reason, exc)

    def _assert_request_active(self, app_id: str, request_id: str) -> None:
        current = self.store.get_app(app_id)
        if current is None or current.latest_request_id != request_id:
            raise RuntimeError(f"Launch Request '{request_id}' was superseded or deleted.")

    def execute_launch_request(self, request_id: str) -> LaunchStatusResponse:
        """Executes the full Launch Request provisioning pipeline synchronously."""
        launch = self.store.get_launch(request_id)
        if launch is None:
            raise AppNotFoundError(f"Launch Request '{request_id}' not found.")
        app = self.store.get_app(launch.app_id)
        if app is None:
            raise AppNotFoundError(f"Factory App '{launch.app_id}' not found.")

        app_dir = f"/root/{app.slug}"
        sandbox_id: str | None = None
        flusher = _BufferedLogFlusher(self.store, request_id)
        try:
            self._record_progress(request_id, "launching_sandbox", "Provisioning Modal sandbox", "Starting Modal sandbox...")
            req = LaunchRequest(
                repo=None,
                name=app.slug,
                vm=app.vm,
                no_cloudflare=True,
                t3=True,
                no_t3_persist=self.no_t3_persist,
                react_native=app.mobile_app,
                modal=False,
                profile=app.profile,
            )
            running = self.launch_fn(req, log_cb=flusher.append)
            flusher.flush()
            sb, launch_resp = (running.sandbox, running.response) if hasattr(running, "response") else running
            sandbox_id = launch_resp.sandbox_id
            if not launch_resp.t3_url:
                raise RuntimeError("Modal sandbox did not expose a T3 Code Server tunnel URL.")
            self._assert_request_active(app.app_id, request_id)

            self._record_progress(
                request_id,
                "scaffolding_workspace",
                "Preparing local Git workspace",
                f"Sandbox {sandbox_id} online; preparing {app_dir}...",
            )
            if app.template == "nextjs":
                cmd = ["create-app", app_dir, "-y"]
                if app.mobile_app:
                    cmd.append("--mobile-app")
                rc, out, err = exec_in_sandbox(sb, *cmd, timeout=300)
                if rc != 0:
                    raise RuntimeError(f"create-app failed in {app_dir}: {err or out}")
            else:
                ensure_blank_git_workspace(sb, app_dir)
            db_name = provision_optional_database(
                sb, app, app_dir, env=self._effective_env(), create_db_fn=self.create_db_fn
            )

            self._record_progress(
                request_id, "waiting_t3", "Waiting for T3 Code Server", "Checking T3 server & model readiness..."
            )
            t3_meta = wait_for_t3_ready(sb, timeout_secs=60)
            environment_id = t3_meta["environment_id"]
            instance_id, chosen_model, thought_level = resolve_provider_model(
                t3_meta, app.provider, app.model, app.thought_level
            )

            self._record_progress(
                request_id,
                "starting_thread",
                "Starting agent thread & pairing",
                f"Registering workspace and starting thread ({instance_id}/{chosen_model})...",
            )
            thread_id, project_id = ensure_project_and_start_thread(
                sb, app, app_dir, instance_id=instance_id, model=chosen_model, thought_level=thought_level
            )
            token = mint_pairing_token(sb)
            chat_url = build_direct_chat_url(launch_resp.t3_url, environment_id, thread_id)
            handoff_url = build_direct_chat_url(launch_resp.t3_url, environment_id, thread_id, token=token)
            handoff_expires_at = utc_now_iso(offset_seconds=HANDOFF_TOKEN_TTL_SECONDS)

            updated_app = self.store.update_app_if_current_request(
                app.app_id,
                request_id,
                status="ready",
                provider_instance_id=instance_id,
                model=chosen_model,
                sandbox_id=sandbox_id,
                sandbox_name=launch_resp.sandbox_name,
                environment_id=environment_id,
                project_id=project_id,
                thread_id=thread_id,
                t3_url=launch_resp.t3_url,
                chat_url=chat_url,
                database_name=db_name,
                last_error=None,
            )
            if updated_app is None:
                self._terminate_quietly(sandbox_id, profile=app.profile, reason="superseded_ready")
                try:
                    failed_launch = self.store.modify_launch(
                        request_id,
                        lambda cur: cur.with_stage(
                            "failed", "Superseded or deleted", error="Launch Request was superseded or deleted."
                        ),
                    )
                    return LaunchStatusResponse(request=failed_launch, app=self.store.get_app(app.app_id, reload=False))
                except KeyError:
                    return LaunchStatusResponse(
                        request=launch.with_stage("failed", "Deleted", error="Factory App deleted during launch."),
                        app=None,
                    )

            updated_launch = self.store.modify_launch(
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
            err_msg = str(exc)
            logger.error("Launch Request %s failed: %s", request_id, err_msg)
            self._terminate_quietly(sandbox_id, profile=app.profile, reason="launch_failure")
            updated_app = self.store.update_app_if_current_request(
                app.app_id,
                request_id,
                status="failed",
                sandbox_id=None,
                last_error=err_msg,
            )
            try:
                updated_launch = self.store.modify_launch(
                    request_id,
                    lambda cur: cur.with_stage(
                        "failed", "Launch failed", log_lines=[f"Error: {err_msg}"], error=err_msg
                    ),
                )
            except KeyError:
                updated_launch = launch.with_stage("failed", "Launch failed", error=err_msg)
            return LaunchStatusResponse(
                request=updated_launch,
                app=updated_app or self.store.get_app(app.app_id, reload=False),
            )

    def _attach_sandbox(self, sandbox_id: str, profile: str | None) -> Any | None:
        try:
            client = self.client_for_profile_fn(profile) if profile else None
            return self.sandbox_from_id_fn(sandbox_id, client=client) if client else self.sandbox_from_id_fn(sandbox_id)
        except Exception:
            return None

    def _get_running_sandbox(self, sandbox_id: str | None, profile: str | None) -> Any | None:
        if not sandbox_id:
            return None
        sb = self._attach_sandbox(sandbox_id, profile)
        if sb is None:
            return None
        try:
            return sb if sb.poll() is None else None
        except Exception:
            return None

    def _snapshot_index(self, profile: str | None = None) -> dict[str, dict[str, Any]]:
        try:
            snaps = self.list_snapshots_fn(profile=profile)
        except Exception:
            return {}
        by_sandbox: dict[str, dict[str, Any]] = {}
        for snap in snaps:
            sid = snap.get("sandbox_id")
            if sid and sid not in by_sandbox:
                by_sandbox[sid] = snap
        return by_sandbox

    def _to_app_view(self, app: FactoryAppRecord, snapshots: dict[str, dict[str, Any]]) -> FactoryAppView:
        snap = snapshots.get(app.sandbox_id or "") if app.sandbox_id else None
        if app.status == "provisioning":
            runtime_status = "provisioning"
        elif app.status == "failed":
            runtime_status = "failed"
        elif self._get_running_sandbox(app.sandbox_id, app.profile) is not None:
            runtime_status = "running"
        else:
            runtime_status = "stopped"
        return FactoryAppView(
            **app.model_dump(),
            runtime_status=runtime_status,
            snapshot_image_id=(snap or {}).get("image_id"),
            snapshot_name=(snap or {}).get("name"),
        )

    def get_app_with_status(self, app_id: str, *, profile: str | None = None) -> FactoryAppView | None:
        """Loads a single Factory App enriched with live sandbox running/stopped state."""
        app = self.store.get_app(app_id)
        if app is None:
            return None
        snapshots = self._snapshot_index(profile=profile or app.profile)
        return self._to_app_view(app, snapshots)

    def list_apps_with_status(self, *, profile: str | None = None) -> list[FactoryAppView]:
        """Lists Factory Apps enriched with live sandbox running/stopped state and snapshots."""
        apps = self.store.list_apps()
        snapshots = self._snapshot_index(profile=profile)
        return [self._to_app_view(app, snapshots) for app in apps]

    def open_factory_app(self, app_id: str) -> OpenAppResponse:
        """Mints a fresh short-lived pairing token for a running Factory App's T3 chat."""
        app = self.store.get_app(app_id)
        if app is None:
            raise AppNotFoundError(f"Factory App '{app_id}' not found.")
        if app.status != "ready" or not (app.sandbox_id and app.t3_url and app.environment_id and app.thread_id):
            raise AppNotReadyError(f"Factory App '{app_id}' is not ready (status: {app.status}).")

        sb = self._get_running_sandbox(app.sandbox_id, app.profile)
        if sb is None:
            snap = self._snapshot_index(profile=app.profile).get(app.sandbox_id)
            raise AppSandboxStoppedError(
                app_id,
                snapshot_image_id=(snap or {}).get("image_id"),
                snapshot_name=(snap or {}).get("name"),
            )

        token = mint_pairing_token(sb)
        chat_url = app.chat_url or build_direct_chat_url(app.t3_url, app.environment_id, app.thread_id)
        handoff_url = build_direct_chat_url(app.t3_url, app.environment_id, app.thread_id, token=token)
        return OpenAppResponse(app_id=app.app_id, handoff_url=handoff_url, chat_url=chat_url)

    def delete_factory_app(self, app_id: str, *, terminate_active_sandbox: bool = True) -> bool:
        """Deletes a Factory App record and optionally terminates its active sandbox."""
        app = self.store.get_app(app_id)
        if app is None:
            return False
        if (
            terminate_active_sandbox
            and app.sandbox_id
            and self._get_running_sandbox(app.sandbox_id, app.profile) is not None
        ):
            self._terminate_quietly(app.sandbox_id, profile=app.profile, reason=f"delete:{app_id}")
        return self.store.delete_app(app_id)
