"""FastAPI REST endpoints for Factory Apps, Launch Requests, and model choices."""

from __future__ import annotations

import threading
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, status

from ._coordinator import (
    AppNotFoundError,
    AppNotReadyError,
    AppSandboxStoppedError,
    LaunchCoordinator,
)
from ._models import (
    CreateAppPayload,
    FactoryAppRecord,
    FactoryAppView,
    LaunchRequestRecord,
    LaunchStatusResponse,
    ModelChoice,
    OpenAppResponse,
)

apps_router = APIRouter(tags=["apps"])

_COORDINATOR_FACTORY: Callable[[], LaunchCoordinator] | None = None
_LAUNCH_DISPATCHER: Callable[[str], None] | None = None


def set_coordinator_factory(factory: Callable[[], LaunchCoordinator] | None) -> None:
    """Overrides the LaunchCoordinator factory (primarily for tests)."""
    global _COORDINATOR_FACTORY
    _COORDINATOR_FACTORY = factory


def set_launch_dispatcher(dispatcher: Callable[[str], None] | None) -> None:
    """Registers the asynchronous dispatcher invoked after saving a Launch Request."""
    global _LAUNCH_DISPATCHER
    _LAUNCH_DISPATCHER = dispatcher


def get_coordinator() -> LaunchCoordinator:
    """Returns a LaunchCoordinator bound to the current store configuration."""
    if _COORDINATOR_FACTORY is not None:
        return _COORDINATOR_FACTORY()
    return LaunchCoordinator()


def _dispatch_launch(request_id: str, coordinator: LaunchCoordinator) -> None:
    if _LAUNCH_DISPATCHER is not None:
        _LAUNCH_DISPATCHER(request_id)
        return
    threading.Thread(
        target=coordinator.execute_launch_request,
        args=(request_id,),
        daemon=True,
    ).start()


def _launch_accepted_payload(app: FactoryAppRecord, launch: LaunchRequestRecord) -> dict[str, Any]:
    return {
        "app_id": app.app_id,
        "request_id": launch.request_id,
        "status_url": f"/api/launches/{launch.request_id}",
        "app": app.model_dump(),
        "request": launch.model_dump(),
    }


@apps_router.get("/api/models", response_model=list[ModelChoice])
def api_list_models() -> list[ModelChoice]:
    """Lists available builder provider/model selections."""
    return get_coordinator().list_available_models()


@apps_router.get("/api/apps", response_model=list[FactoryAppView])
def api_list_apps(
    profile: str | None = Query(None, description="Optional Modal profile filter for snapshot lookup"),
) -> list[FactoryAppView]:
    """Lists Factory Apps enriched with live sandbox runtime status and snapshots."""
    effective_profile = None if (not profile or profile == "all") else profile
    return get_coordinator().list_apps_with_status(profile=effective_profile)


@apps_router.post("/api/apps", status_code=status.HTTP_202_ACCEPTED)
def api_create_app(payload: CreateAppPayload) -> dict[str, Any]:
    """Creates a Factory App and spawns a durable Launch Request."""
    coordinator = get_coordinator()
    app, launch = coordinator.create_and_dispatch(
        payload,
        dispatch_fn=lambda req_id: _dispatch_launch(req_id, coordinator),
    )
    return _launch_accepted_payload(app, launch)


@apps_router.get("/api/apps/{app_id}", response_model=FactoryAppView)
def api_get_app(app_id: str) -> FactoryAppView:
    """Returns a single Factory App enriched with live runtime status."""
    match = get_coordinator().get_app_with_status(app_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Factory App '{app_id}' not found")
    return match


@apps_router.get("/api/launches/{request_id}", response_model=LaunchStatusResponse)
def api_get_launch(request_id: str) -> LaunchStatusResponse:
    """Returns current durable progress and handoff URL for a Launch Request."""
    coordinator = get_coordinator()
    launch = coordinator.store.get_launch(request_id)
    if launch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Launch Request '{request_id}' not found")
    app = coordinator.store.get_app(launch.app_id, reload=False)
    return LaunchStatusResponse(request=launch, app=app)


@apps_router.post("/api/apps/{app_id}/open", response_model=OpenAppResponse)
def api_open_app(app_id: str) -> OpenAppResponse:
    """Mints a fresh short-lived pairing token and returns the direct T3 chat handoff URL."""
    coordinator = get_coordinator()
    try:
        return coordinator.open_factory_app(app_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AppNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "app_not_ready", "message": str(exc)},
        ) from exc
    except AppSandboxStoppedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "sandbox_stopped",
                "message": str(exc),
                "snapshot_image_id": exc.snapshot_image_id,
                "snapshot_name": exc.snapshot_name,
            },
        ) from exc


@apps_router.post("/api/apps/{app_id}/relaunch", status_code=status.HTTP_202_ACCEPTED)
def api_relaunch_app(
    app_id: str,
    resume: bool = Query(False, description="Resume from failed step on preserved sandbox when still active"),
) -> dict[str, Any]:
    """Starts a fresh Launch Request or resumes from the failed step when resume=true."""
    coordinator = get_coordinator()
    try:
        app, launch = coordinator.relaunch_factory_app(
            app_id,
            resume=resume,
            dispatch_fn=lambda req_id: _dispatch_launch(req_id, coordinator),
        )
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _launch_accepted_payload(app, launch)


@apps_router.delete("/api/apps/{app_id}")
def api_delete_app(
    app_id: str,
    terminate_sandbox: bool = Query(True, description="Terminate running sandbox if still active"),
) -> dict[str, Any]:
    """Removes a Factory App record and optionally terminates its active sandbox."""
    deleted = get_coordinator().delete_factory_app(app_id, terminate_active_sandbox=terminate_sandbox)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Factory App '{app_id}' not found")
    return {"app_id": app_id, "deleted": True}
