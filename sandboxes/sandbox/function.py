"""Modal cloud control plane function hosting the FastAPI sandbox management API."""

import logging
import os
from pathlib import Path
import sys

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
import modal

from sandbox.apps import (
    FACTORY_STATE_MOUNT_PATH,
    FactoryStateStore,
    LaunchCoordinator,
    get_factory_state_volume,
    set_default_store,
    set_launch_dispatcher,
)
from shared.image import SOPS_INSTALL_COMMANDS, stage_app_template_into_image
from sandbox.config import (
    collect_control_plane_secrets_dict,
    compile_control_plane_secrets,
    parse_env_file,
    resolve_factory_root,
    resolve_web_ui_credentials,
)
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
from sandbox.provenance import resolve_host_software_factory_provenance
from sandbox.web import check_authentication, codex_router, router as web_router

logger = logging.getLogger(__name__)

APP_NAME = "sandbox-control-plane"
app = modal.App(APP_NAME)

sandbox_dir = Path(__file__).resolve().parent
execution_root = sandbox_dir.parent
repo_root = resolve_factory_root()


def resolve_and_validate_web_credentials(root: Path, enforce: bool | None = None) -> dict[str, str]:
    """Resolves and validates WEB_UI_USERNAME and WEB_UI_PASSWORD via FactoryConfiguration."""
    return resolve_web_ui_credentials(repo_root=root, enforce=enforce)


def collect_control_plane_secrets(root: Path) -> dict[str, str]:
    """Collects control plane secrets from .env and environment for Modal secret injection."""
    prov_fn = getattr(sys.modules.get("sandbox.function"), "resolve_host_software_factory_provenance", None)
    prov = prov_fn(root) if prov_fn else None
    return collect_control_plane_secrets_dict(repo_root=root, provenance=prov)


def validate_deployment_credentials(root: Path, enforce: bool | None = None) -> bool:
    """Validates GitHub access credentials and Age decryption keys for repository sandbox provisioning."""
    parsed: dict[str, str] = {}
    dotenv_path = root / ".env"
    if dotenv_path.is_file():
        parsed = parse_env_file(dotenv_path)

    has_creds = bool(os.environ.get("GH_TOKEN") or parsed.get("GH_TOKEN"))
    has_age_key = bool(
        os.environ.get("AGE_PRIVATE_KEY")
        or os.environ.get("SOPS_AGE_KEY")
        or parsed.get("AGE_PRIVATE_KEY")
        or parsed.get("SOPS_AGE_KEY")
    )

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

    if not has_age_key:
        logger.warning(
            "Age decryption key (AGE_PRIVATE_KEY / SOPS_AGE_KEY) not found in environment or .env. "
            "Decrypting secrets from Central Environment Store (env-store) will be skipped."
        )

    return True


def validate_clean_working_tree(root: Path, enforce: bool | None = None) -> bool:
    """Validates that the host working tree has no uncommitted changes before deployment.

    Raises RuntimeError if dirty working tree is detected during modal deploy or modal serve.
    Can be bypassed via ALLOW_DIRTY_DEPLOY=1 environment variable or during pytest execution
    unless enforce=True.
    """
    if os.environ.get("ALLOW_DIRTY_DEPLOY") == "1":
        return True

    if enforce is None:
        is_testing = (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or any("pytest" in str(arg) for arg in sys.argv)
        )
        should_enforce = modal.is_local() and not is_testing
    else:
        should_enforce = enforce

    if not should_enforce:
        return True

    prov = resolve_host_software_factory_provenance(root)
    if prov.get("SOFTWARE_FACTORY_DIRTY") == "1":
        raise RuntimeError(
            "Cannot deploy sandbox control plane with uncommitted changes. "
            "Please commit or stash your changes before running 'modal deploy' or 'modal serve', "
            "or set ALLOW_DIRTY_DEPLOY=1 to bypass."
        )

    return True


CONTROL_PLANE_PIP_PACKAGES: tuple[str, ...] = (
    "modal>=1.6.1",
    "fastapi>=0.100.0",
    "pydantic>=2.0.0",
    "qrcode>=7.4.2",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
)

image = (
    modal.Image.debian_slim()
    .apt_install("curl")
    .run_commands(*SOPS_INSTALL_COMMANDS)
    .pip_install(*CONTROL_PLANE_PIP_PACKAGES)
    .add_local_python_source("sandbox")
    .add_local_dir(execution_root / "shared", "/root/shared", ignore=["**/__pycache__"])
    .add_local_dir(execution_root / "scripts", "/root/.scripts", ignore=["**/__pycache__"])
    .add_local_dir(sandbox_dir / "static", "/root/sandbox/static")
)
image = stage_app_template_into_image(
    image,
    template_dir=repo_root / "app-template",
    factory_root=repo_root,
    copy=False,
)

# Secrets are injected via modal.Secret, not staged to filesystem
auth_env = resolve_and_validate_web_credentials(repo_root)
for k, v in auth_env.items():
    if k not in os.environ:
        os.environ[k] = v

validate_deployment_credentials(repo_root)
validate_clean_working_tree(repo_root)

if modal.is_local():
    function_secrets = compile_control_plane_secrets(repo_root)
else:
    function_secrets = [modal.Secret.from_dict({})]

web_app = FastAPI(
    title="Modal Sandbox Control Plane",
    description="Synchronous HTTP API and Web UI for provisioning and snapshotting Modal sandboxes.",
    version="1.0.0",
)
web_app.include_router(web_router)
web_app.include_router(codex_router)


@web_app.get("/health")
def health() -> dict[str, str]:
    """Endpoint liveness and readiness probe."""
    return {"status": "ok", "app": APP_NAME}


@web_app.post(
    "/launch",
    response_model=LaunchResponse,
    dependencies=[Depends(check_authentication)],
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
    dependencies=[Depends(check_authentication)],
)
def snapshot(req: SnapshotRequest) -> SnapshotResponse:
    """Captures a filesystem snapshot of a target running sandbox."""
    try:
        return capture_snapshot_core(
            sandbox_id=req.sandbox_id,
            ttl_days=req.ttl_days,
            terminate=req.terminate,
            name=req.name,
            timeout=req.timeout,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot capture failed: {exc}",
        ) from exc


factory_state_volume = get_factory_state_volume()


@app.function(
    image=image,
    secrets=function_secrets,
    volumes={FACTORY_STATE_MOUNT_PATH: factory_state_volume},
    timeout=600,
)
def run_launch_request(request_id: str) -> dict[str, Any]:
    """Modal background worker executing a Factory App Launch Request."""
    store = FactoryStateStore(root_dir=FACTORY_STATE_MOUNT_PATH, volume=factory_state_volume)
    set_default_store(store)
    result = LaunchCoordinator(store=store).execute_launch_request(request_id)
    return result.model_dump()


@app.function(
    image=image,
    secrets=function_secrets,
    volumes={FACTORY_STATE_MOUNT_PATH: factory_state_volume},
    timeout=180,
)
@modal.asgi_app()
def fastapi_app():
    """Serves the control plane ASGI application."""
    set_default_store(FactoryStateStore(root_dir=FACTORY_STATE_MOUNT_PATH, volume=factory_state_volume))
    set_launch_dispatcher(lambda request_id: run_launch_request.spawn(request_id))
    return web_app
