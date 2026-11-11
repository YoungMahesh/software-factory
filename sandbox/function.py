"""Modal cloud control plane function hosting the FastAPI sandbox management API."""

import hmac
import logging
import os
from pathlib import Path
import sys
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
import modal

# (shared.image secrets imports retired)
from sandbox.core import (
    LaunchRequest,
    LaunchResponse,
    SnapshotRequest,
    SnapshotResponse,
    capture_snapshot_core,
)
from sandbox.launcher import (
    RunningSandbox,
    SandboxLauncher,
    launch_sandbox,
)
from sandbox.web import router as web_router

logger = logging.getLogger(__name__)

APP_NAME = "sandbox-control-plane"
app = modal.App(APP_NAME)

repo_root = Path(__file__).resolve().parent.parent


def resolve_and_validate_web_credentials(root: Path, enforce: bool | None = None) -> dict[str, str]:
    """Resolves and validates WEB_UI_USERNAME and WEB_UI_PASSWORD.

    Checks os.environ, falling back to .env / secrets/.env. Raises a RuntimeError
    during modal deploy or modal serve if required credentials are missing.
    Bypassed during test execution when running under pytest unless enforce=True.
    """
    credentials: dict[str, str] = {}
    for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD", "MODAL_SANDBOX_AUTH_TOKEN"):
        val = os.environ.get(key)
        if val:
            credentials[key] = val

    if not credentials.get("WEB_UI_USERNAME") or not credentials.get("WEB_UI_PASSWORD"):
        candidate_files = [
            root / ".env",
            root / ".secrets" / ".env",
            root / "secrets" / ".env",
        ]
        for env_file in candidate_files:
            if env_file.is_file():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD", "MODAL_SANDBOX_AUTH_TOKEN") and k not in credentials:
                            credentials[k] = v

    if enforce is None:
        is_testing = (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or any("pytest" in str(arg) for arg in sys.argv)
        )
        should_enforce = not is_testing
    else:
        should_enforce = enforce

    if not should_enforce:
        return credentials

    missing = [key for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD") if not credentials.get(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variable(s) for Web UI deployment: {missing_str}. "
            "Please configure WEB_UI_USERNAME and WEB_UI_PASSWORD in your environment or .env file "
            "before running 'modal deploy' or 'modal serve'."
        )

    return credentials


def validate_deployment_credentials(root: Path, enforce: bool | None = None) -> bool:
    """Validates GitHub access credentials presence for repository sandbox provisioning."""
    has_creds = bool(os.environ.get("GH_TOKEN"))
    dotenv_path = root / ".env"
    if not has_creds and dotenv_path.is_file():
        try:
            for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GH_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val:
                        has_creds = True
                        break
        except Exception:
            pass

    if not has_creds:
        logger.warning(
            "GitHub access credentials (GH_TOKEN) not found in environment or .env. "
            "Launching repository sandboxes will fail until GH_TOKEN is provided."
        )
        if enforce or os.environ.get("MODAL_ENFORCE_AUTH") == "1":
            raise RuntimeError(
                "Missing required GitHub access credentials (GH_TOKEN) in environment or .env. "
                "Please configure GH_TOKEN before deploying."
            )
        return False
    return True


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
    .add_local_dir(str(repo_root / "scripts"), "/root/.scripts")
)

if (repo_root / "sandbox" / "static").is_dir():
    image = image.add_local_dir(str(repo_root / "sandbox" / "static"), "/root/sandbox/static")

# Secrets are injected via modal.Secret, not staged to filesystem

function_secrets: list[modal.Secret] = []
if (repo_root / ".env").is_file():
    function_secrets.append(modal.Secret.from_dotenv(repo_root / ".env"))

auth_env = resolve_and_validate_web_credentials(repo_root)
if auth_env:
    function_secrets.append(modal.Secret.from_dict(auth_env))
    for k, v in auth_env.items():
        if k not in os.environ:
            os.environ[k] = v

validate_deployment_credentials(repo_root)

web_app = FastAPI(
    title="Modal Sandbox Control Plane",
    description="Synchronous HTTP API and Web UI for provisioning and snapshotting Modal sandboxes.",
    version="1.0.0",
)
web_app.include_router(web_router)


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
        err_msg = str(exc)
        if "credentials" in err_msg.lower() or "github-orgs" in err_msg.lower() or "gh_token" in err_msg.lower():
            logger.error("Control plane missing credentials: %s", err_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Control plane missing credentials: {err_msg}. Ensure GH_TOKEN is present in .env and redeploy.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err_msg,
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
            name=req.name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot capture failed: {exc}",
        ) from exc


@app.function(
    image=image,
    secrets=function_secrets,
    timeout=180,
)
@modal.asgi_app()
def fastapi_app():
    """Serves the control plane ASGI application."""
    return web_app
