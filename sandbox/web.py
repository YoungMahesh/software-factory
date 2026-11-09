"""Web UI API routes and router for Modal Sandbox Runner.

Provides REST endpoints for inspecting and terminating sandboxes, capturing
and listing filesystem snapshots, launching from snapshots, and serving the
embedded HTML5 single-page application across multiple Modal workspace profiles.
Exclusively hosted in Modal cloud via sandbox/function.py.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
import queue
import secrets
import threading
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
import modal
from pydantic import BaseModel

from shared.image import DEFAULT_T3_USAGE_VOLUME
from sandbox.core import (
    DEFAULT_OPENCODE_PORT,
    DEFAULT_T3_PORT,
    LaunchRequest,
    LaunchResponse,
    SnapshotResponse,
    capture_snapshot_core,
    launch_sandbox,
)
from sandbox.lifecycle import get_sandboxes, terminate_sandbox
from sandbox.profiles import get_available_profiles, get_client_for_profile
from sandbox.snapshots import (
    delete_snapshot,
    get_snapshot,
    list_snapshots,
    record_snapshot,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def check_authentication(request: Request) -> None:
    """Enforces HTTP Basic authentication against WEB_UI_USERNAME and WEB_UI_PASSWORD."""
    if request.url.path in ("/favicon.ico", "/health"):
        return

    expected_user = os.environ.get("WEB_UI_USERNAME")
    expected_pass = os.environ.get("WEB_UI_PASSWORD")

    if not expected_user or not expected_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication misconfigured: WEB_UI_USERNAME and WEB_UI_PASSWORD must be set",
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )

    if not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme; expected Basic authentication",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )

    try:
        encoded = auth_header[6:].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1) if ":" in decoded else (decoded, "")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Basic authentication encoding",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )

    if not (secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_pass)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect authentication credentials",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )


router = APIRouter(dependencies=[Depends(check_authentication)])


class SnapshotCreatePayload(BaseModel):
    name: str = ""
    ttl_days: int = 30
    terminate: bool = False
    profile: str | None = None


class SnapshotLaunchPayload(BaseModel):
    name: str = "resumed-sandbox"
    vm: bool = False
    memory: int | None = None
    no_cloudflare: bool = False
    opencode: bool = False
    t3: bool = True
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    no_t3_persist: bool = False
    agy: bool = False
    herdr: bool = False
    pi: bool = False
    modal: bool = False
    sops: bool = False
    profile: str | None = None


class FreshSandboxLaunchPayload(BaseModel):
    mode: str = "repo"
    repo: str | None = None
    github_branch: str = "main"
    testing: bool = False
    full_clone: bool = False
    name: str | None = None
    profile: str | None = None
    vm: bool = False
    memory: int | None = None
    no_cloudflare: bool = False
    opencode: bool = False
    t3: bool = True
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    no_t3_persist: bool = False
    agy: bool = False
    herdr: bool = False
    pi: bool = False
    modal: bool = True
    sops: bool = True
    browser: bool = False
    react_native: bool = False


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Returns 204 No Content for favicon to prevent browser 404 logs."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/profiles", response_model=list[dict[str, Any]])
def api_list_profiles() -> list[dict[str, Any]]:
    """Returns configured Modal workspace profiles and marks active profile."""
    try:
        return get_available_profiles()
    except Exception as exc:
        logger.error("Failed to list profiles: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list profiles: {exc}") from exc


@router.get("/api/sandboxes", response_model=list[dict[str, Any]])
def api_list_sandboxes(
    app_name: str | None = Query(None, description="Filter by app name (defaults to all apps if omitted)"),
    all_apps: bool = Query(True, description="Scan environment-wide without scoping to an App"),
    profile: str | None = Query(None, description="Profile name or 'all' for aggregated across profiles"),
) -> list[dict[str, Any]]:
    """Lists existing Modal sandboxes with status, instance names, and owning profiles."""
    try:
        effective_all_apps = all_apps if app_name is None else False
        return get_sandboxes(app_name=app_name, all_apps=effective_all_apps, profile=profile)
    except Exception as exc:
        logger.error("Failed to list sandboxes: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list sandboxes: {exc}") from exc


def _build_fresh_launch_request(payload: FreshSandboxLaunchPayload) -> LaunchRequest:
    if payload.mode == "repo":
        if not payload.repo or not payload.repo.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target repository is required when launching a repository sandbox.")
    elif payload.mode == "standalone":
        if not payload.name or not payload.name.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sandbox App Name is required when launching a standalone sandbox.")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid launch mode '{payload.mode}'; expected 'repo' or 'standalone'.")

    return LaunchRequest(
        repo=payload.repo.strip() if payload.repo else None,
        testing=payload.testing,
        github_branch=payload.github_branch or "main",
        full_clone=payload.full_clone,
        name=payload.name.strip() if payload.name else None,
        vm=payload.vm,
        memory=payload.memory,
        no_cloudflare=payload.no_cloudflare,
        opencode=payload.opencode,
        t3=payload.t3,
        t3_usage_volume=payload.t3_usage_volume,
        no_t3_persist=payload.no_t3_persist,
        agy=payload.agy,
        herdr=payload.herdr,
        pi=payload.pi,
        modal=payload.modal,
        sops=payload.sops,
        browser=payload.browser,
        react_native=payload.react_native,
    )


@router.post("/api/sandboxes", response_model=LaunchResponse)
def api_launch_fresh_sandbox(payload: FreshSandboxLaunchPayload) -> LaunchResponse:
    """Launches a fresh Modal sandbox (repository-backed or standalone)."""
    req = _build_fresh_launch_request(payload)
    client = None
    if payload.profile:
        try:
            client = get_client_for_profile(payload.profile)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid profile '{payload.profile}': {exc}") from exc

    try:
        _, response = launch_sandbox(req, client=client)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        err_msg = str(exc)
        if "credentials" in err_msg.lower() or "github-orgs" in err_msg.lower():
            logger.error("Control plane missing credentials: %s", err_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Control plane missing credentials: {err_msg}. Ensure secrets/github-orgs.env is present and redeploy.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg) from exc
    except modal.exception.AlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Sandbox already exists: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to launch fresh sandbox: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to launch sandbox: {exc}") from exc


@router.post("/api/sandboxes/stream")
def api_launch_fresh_sandbox_stream(payload: FreshSandboxLaunchPayload) -> StreamingResponse:
    """Launches a fresh sandbox while streaming live provisioning progress and startup logs via SSE."""
    def event_stream():
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def log_cb(msg: str) -> None:
            q.put({"type": "log", "message": msg})

        def run_launch():
            try:
                req = _build_fresh_launch_request(payload)
                client = None
                if payload.profile:
                    try:
                        client = get_client_for_profile(payload.profile)
                    except Exception as exc:
                        q.put({"type": "error", "detail": f"Invalid profile '{payload.profile}': {exc}"})
                        return

                _, response = launch_sandbox(req, client=client, log_cb=log_cb)
                q.put({"type": "done", "response": response.model_dump()})
            except HTTPException as exc:
                q.put({"type": "error", "detail": exc.detail})
            except FileNotFoundError as exc:
                err_msg = str(exc)
                if "credentials" in err_msg.lower() or "github-orgs" in err_msg.lower():
                    q.put({"type": "error", "detail": f"Control plane missing credentials: {err_msg}. Ensure secrets/github-orgs.env is present and redeploy."})
                else:
                    q.put({"type": "error", "detail": err_msg})
            except Exception as exc:
                q.put({"type": "error", "detail": str(exc)})
            finally:
                q.put(None)

        threading.Thread(target=run_launch, daemon=True).start()

        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/sandboxes/{sandbox_id}/terminate")
def api_terminate_sandbox(sandbox_id: str, profile: str | None = Query(None, description="Owning profile name")) -> dict[str, Any]:
    """Terminates an active Modal sandbox by ID under its owning profile."""
    result = terminate_sandbox(sandbox_id, profile=profile)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Termination failed"),
        )
    return result


@router.post("/api/sandboxes/{sandbox_id}/snapshot", response_model=SnapshotResponse)
def api_create_snapshot(sandbox_id: str, payload: SnapshotCreatePayload) -> SnapshotResponse:
    """Captures a filesystem snapshot of a running sandbox."""
    try:
        return capture_snapshot_core(
            sandbox_id=sandbox_id,
            ttl_days=payload.ttl_days,
            terminate=payload.terminate,
            name=payload.name,
            profile=payload.profile,
        )
    except Exception as exc:
        logger.error("Failed to create snapshot for %s: %s", sandbox_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Snapshot capture failed: {exc}") from exc


@router.get("/api/snapshots", response_model=list[dict[str, Any]])
def api_list_snapshots(profile: str | None = Query(None, description="Filter snapshots by profile name")) -> list[dict[str, Any]]:
    """Lists all available snapshots in the registry."""
    try:
        return list_snapshots(profile=profile)
    except Exception as exc:
        logger.error("Failed to list snapshots: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list snapshots: {exc}") from exc


@router.delete("/api/snapshots/{image_id}")
def api_delete_snapshot(image_id: str) -> dict[str, Any]:
    """Removes a snapshot record from the registry."""
    if not delete_snapshot(image_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Snapshot {image_id} not found in registry")
    return {"image_id": image_id, "deleted": True}


@router.post("/api/snapshots/{image_id}/launch", response_model=LaunchResponse)
def api_launch_from_snapshot(image_id: str, payload: SnapshotLaunchPayload) -> LaunchResponse:
    """Launches a new sandbox instantiated directly from a snapshot image."""
    req = LaunchRequest(
        name=payload.name,
        from_snapshot=image_id,
        vm=payload.vm,
        memory=payload.memory,
        no_cloudflare=payload.no_cloudflare,
        opencode=payload.opencode,
        t3=payload.t3,
        t3_usage_volume=payload.t3_usage_volume,
        no_t3_persist=payload.no_t3_persist,
        agy=payload.agy,
        herdr=payload.herdr,
        pi=payload.pi,
        modal=payload.modal,
        sops=payload.sops,
    )
    client = None
    if payload.profile:
        try:
            client = get_client_for_profile(payload.profile)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid profile '{payload.profile}': {exc}") from exc

    try:
        _, response = launch_sandbox(req, client=client)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to launch from snapshot %s: %s", image_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to launch from snapshot: {exc}") from exc


@router.get("/", response_class=HTMLResponse)
def index_page() -> HTMLResponse:
    """Serves the single-page application dashboard."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        return HTMLResponse(
            "<html><body><h2>Sandbox Runner Web UI</h2><p>Static index.html not found.</p></body></html>",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


def create_app() -> FastAPI:
    """Constructs the standalone FastAPI app for testing and inspection."""
    app_instance = FastAPI(
        title="Modal Sandbox Runner Web UI",
        description="Web UI and REST API for managing Modal sandboxes and filesystem snapshots across multi-tenant profiles.",
        version="1.0.0",
    )
    app_instance.include_router(router)
    return app_instance


app = create_app()
