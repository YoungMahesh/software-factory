"""Durable Launch Coordinator for provisioning Factory Apps into T3 Web Chat."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable
import uuid

import modal

from sandbox.config import resolve_factory_credentials
from sandbox.db_host import create_database_connection
from sandbox.launcher import launch_sandbox
from sandbox.lifecycle import terminate_sandbox
from sandbox.profiles import get_client_for_profile
from sandbox.snapshots import list_snapshots

from ._models import (
    DEFAULT_ANTIGRAVITY_MODELS,
    DEFAULT_BUILDER_MODEL,
    DEFAULT_BUILDER_PROVIDER,
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
)
from ._pipeline import RESUMABLE_STEPS, PipelineDeps, run_launch_pipeline
from ._sandbox_t3 import mint_pairing_token
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


class LaunchCoordinator:
    """Orchestrates Factory App creation, T3 handoff, step resume, relaunch, and cleanup."""

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
        *,
        resume: bool = False,
        dispatch_fn: Callable[[str], None] | None = None,
    ) -> tuple[FactoryAppRecord, LaunchRequestRecord]:
        """Starts a fresh Launch Request or resumes from the last failed step when alive."""
        app = self.store.get_app(app_id)
        if app is None:
            raise AppNotFoundError(f"Factory App '{app_id}' not found.")

        resume_step: LaunchStatus | None = None
        if (
            resume
            and app.failed_step in RESUMABLE_STEPS
            and app.sandbox_id
            and app.t3_url
            and self._get_running_sandbox(app.sandbox_id, app.profile) is not None
        ):
            resume_step = app.failed_step
        elif app.sandbox_id and self._get_running_sandbox(app.sandbox_id, app.profile) is not None:
            self._terminate_quietly(app.sandbox_id, profile=app.profile, reason="relaunch")

        request_id = f"req_{uuid.uuid4().hex[:12]}"
        if resume_step is not None:
            updated_app = app.model_copy(
                update={
                    "status": "provisioning",
                    "latest_request_id": request_id,
                    "failed_step": None,
                    "last_error": None,
                }
            )
            label = f"Resuming from {resume_step}"
        else:
            updated_app = app.model_copy(
                update={
                    "status": "provisioning",
                    "latest_request_id": request_id,
                    "failed_step": None,
                    "workspace_ready": False,
                    "sandbox_id": None,
                    "sandbox_name": None,
                    "environment_id": None,
                    "project_id": None,
                    "thread_id": None,
                    "t3_url": None,
                    "chat_url": None,
                    "database_name": None,
                    "last_error": None,
                }
            )
            label = "Queued relaunch request"

        launch = LaunchRequestRecord(
            request_id=request_id,
            app_id=app.app_id,
            kind="relaunch",
            resume_from_step=resume_step,
            status="queued",
            current_label=label,
            steps=initial_launch_steps(resume_from=resume_step),
        )
        saved_app, saved_launch = self.store.create_app_and_launch(updated_app, launch)
        if dispatch_fn is not None:
            dispatch_fn(saved_launch.request_id)
        return saved_app, saved_launch

    def _terminate_quietly(self, sandbox_id: str | None, *, profile: str | None, reason: str) -> None:
        if not sandbox_id:
            return
        try:
            self.terminate_fn(sandbox_id, profile=profile)
        except Exception as exc:
            logger.warning("Failed terminating sandbox %s during %s: %s", sandbox_id, reason, exc)

    def execute_launch_request(self, request_id: str) -> LaunchStatusResponse:
        """Executes a Launch Request, resuming from failed_step on an active sandbox when requested."""
        launch = self.store.get_launch(request_id)
        if launch is None:
            raise AppNotFoundError(f"Launch Request '{request_id}' not found.")
        app = self.store.get_app(launch.app_id)
        if app is None:
            raise AppNotFoundError(f"Factory App '{launch.app_id}' not found.")

        deps = PipelineDeps(
            store=self.store,
            launch_fn=self.launch_fn,
            create_db_fn=self.create_db_fn,
            terminate_quietly=self._terminate_quietly,
            get_running_sandbox=self._get_running_sandbox,
            effective_env=self._effective_env,
            no_t3_persist=self.no_t3_persist,
        )
        return run_launch_pipeline(deps, app, launch)

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
