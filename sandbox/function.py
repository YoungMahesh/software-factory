"""Modal cloud control plane function hosting the FastAPI sandbox management API."""

import hmac
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
import modal

from shared.image import SHARED_SECRET_NAME
from sandbox.core import (
    LaunchRequest,
    LaunchResponse,
    SnapshotRequest,
    SnapshotResponse,
    capture_snapshot_core,
    launch_sandbox,
)

APP_NAME = "sandbox-control-plane"
app = modal.App(APP_NAME)

repo_root = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim()
    .pip_install(
        "modal>=1.6.1",
        "fastapi>=0.100.0",
        "pydantic>=2.0.0",
        "qrcode>=7.4.2",
    )
    .add_local_python_source("shared", "sandbox")
    .add_local_dir(str(repo_root / "shared"), "/root/shared")
    .add_local_dir(str(repo_root / "scripts"), "/root/scripts")
)

if (repo_root / "secrets").is_dir():
    image = image.add_local_dir(str(repo_root / "secrets"), "/root/secrets")

web_app = FastAPI(
    title="Modal Sandbox Control Plane",
    description="Synchronous HTTP API for provisioning and snapshotting Modal sandboxes.",
    version="1.0.0",
)


def verify_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Validates bearer token against MODAL_SANDBOX_AUTH_TOKEN environment variable."""
    expected_token = os.environ.get("MODAL_SANDBOX_AUTH_TOKEN")
    if not expected_token:
        # Permissive access if auth token secret is not configured
        return

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format; expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer authentication token",
        )


@web_app.get("/health")
def health() -> dict[str, str]:
    """Endpoint liveness and readiness probe."""
    return {"status": "ok", "app": APP_NAME}


@web_app.post(
    "/launch",
    response_model=LaunchResponse,
    dependencies=[Depends(verify_bearer_token)],
)
def launch(req: LaunchRequest) -> LaunchResponse:
    """Provisions a new sandbox synchronously and returns connection metadata."""
    try:
        _, response = launch_sandbox(req)
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except modal.exception.AlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox already exists: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox launch failed: {exc}",
        ) from exc


@web_app.post(
    "/snapshot",
    response_model=SnapshotResponse,
    dependencies=[Depends(verify_bearer_token)],
)
def snapshot(req: SnapshotRequest) -> SnapshotResponse:
    """Captures a filesystem snapshot of a target running sandbox."""
    try:
        return capture_snapshot_core(
            sandbox_id=req.sandbox_id,
            ttl_days=req.ttl_days,
            terminate=req.terminate,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot capture failed: {exc}",
        ) from exc


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SHARED_SECRET_NAME)],
    timeout=180,
)
@modal.asgi_app()
def fastapi_app():
    """Serves the control plane ASGI application."""
    return web_app
