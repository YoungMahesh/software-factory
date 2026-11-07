"""Web UI API routes and server for Modal Sandbox Runner.

Provides REST endpoints for inspecting and terminating sandboxes, capturing
and listing filesystem snapshots, launching from snapshots, and serving the
embedded HTML5 single-page application across multiple Modal workspace profiles.
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
from pathlib import Path
import secrets
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
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
    """Enforces HTTP Basic and Bearer authentication when credentials are configured."""
    # Allow favicon and health checks to proceed unauthenticated
    if request.url.path in ("/favicon.ico", "/health"):
        return

    expected_user = os.environ.get("WEB_UI_USERNAME")
    expected_pass = os.environ.get("WEB_UI_PASSWORD")
    token_auth = os.environ.get("MODAL_SANDBOX_AUTH_TOKEN")

    # If neither password nor token auth is configured, allow permissive access
    if not expected_pass and not token_auth:
        return

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )

    # Support Bearer token authentication
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        expected = token_auth or expected_pass
        if expected and secrets.compare_digest(token, expected):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
            headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
        )

    # Support HTTP Basic authentication
    if auth_header.startswith("Basic "):
        try:
            encoded = auth_header[6:].strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            if ":" in decoded:
                username, password = decoded.split(":", 1)
            else:
                username, password = decoded, ""
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Basic authentication encoding",
                headers={"WWW-Authenticate": 'Basic realm="Modal Sandbox Runner"'},
            )

        if expected_pass:
            valid_user = True
            if expected_user:
                valid_user = secrets.compare_digest(username, expected_user)
            valid_pass = secrets.compare_digest(password, expected_pass)
            if valid_user and valid_pass:
                return

        if token_auth:
            if secrets.compare_digest(password, token_auth) or secrets.compare_digest(username, token_auth):
                return

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
    t3: bool = False
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    no_t3_persist: bool = False
    agy: bool = False
    herdr: bool = False
    pi: bool = False
    modal: bool = False
    profile: str | None = None


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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list profiles: {exc}",
        ) from exc


@router.get("/api/sandboxes", response_model=list[dict[str, Any]])
def api_list_sandboxes(
    app_name: str | None = Query(None, description="Filter by app name (defaults to software-factory if not all_apps)"),
    all_apps: bool = Query(False, description="Scan environment-wide without scoping to an App"),
    profile: str | None = Query(None, description="Profile name or 'all' for aggregated across profiles"),
) -> list[dict[str, Any]]:
    """Lists existing Modal sandboxes with status, instance names, and owning profiles."""
    try:
        return get_sandboxes(app_name=app_name, all_apps=all_apps, profile=profile)
    except Exception as exc:
        logger.error("Failed to list sandboxes: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sandboxes: {exc}",
        ) from exc


@router.post("/api/sandboxes/{sandbox_id}/terminate")
def api_terminate_sandbox(
    sandbox_id: str,
    profile: str | None = Query(None, description="Owning profile name"),
) -> dict[str, Any]:
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
    """Flushes buffers and creates a filesystem snapshot of a running sandbox."""
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot capture failed: {exc}",
        ) from exc


@router.get("/api/snapshots", response_model=list[dict[str, Any]])
def api_list_snapshots(
    profile: str | None = Query(None, description="Filter snapshots by profile name"),
) -> list[dict[str, Any]]:
    """Lists all available snapshots in the registry."""
    try:
        return list_snapshots(profile=profile)
    except Exception as exc:
        logger.error("Failed to list snapshots: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list snapshots: {exc}",
        ) from exc


@router.delete("/api/snapshots/{image_id}")
def api_delete_snapshot(image_id: str) -> dict[str, Any]:
    """Removes a snapshot record from the registry."""
    found = delete_snapshot(image_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {image_id} not found in registry",
        )
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
    )
    client = None
    if payload.profile:
        try:
            client = get_client_for_profile(payload.profile)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid profile '{payload.profile}': {exc}",
            ) from exc

    try:
        _, response = launch_sandbox(req, client=client)
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to launch sandbox from snapshot %s: %s", image_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox launch failed: {exc}",
        ) from exc


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
    """Constructs the standalone FastAPI app."""
    app = FastAPI(
        title="Modal Sandbox Runner Web UI",
        description="Web UI and REST API for managing Modal sandboxes and filesystem snapshots across multi-tenant profiles.",
        version="1.0.0",
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="Start the Modal Sandbox Runner Web UI server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()
    print(f"🚀 Starting Sandbox Runner Web UI on http://{args.host}:{args.port}")
    uvicorn.run("sandbox.web:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
