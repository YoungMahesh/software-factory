"""Control-plane-backed self-deployment endpoints and async worker for the Sandbox Web Dashboard."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Any, Callable, Literal
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from sandbox._deploy_state import (
    ACTIVE_DEPLOY_STATUSES,
    STALE_DEPLOY_MINUTES,
    clone_latest_main,
    create_deploy_job,
    get_deploy_job,
    get_latest_deploy_job,
    is_stale_active_deploy,
    update_deploy_job,
)
from sandbox.apps._models import utc_now_iso
from sandbox.caddy_wildcard import is_subdomain_of, normalize_base_domain, resolve_apps_base_domain
from sandbox.dashboard_deploy import deploy_dashboard
from sandbox.env_store import fetch_vault_env_raw, resolve_gh_token
from sandbox.infra_deploy import resolve_vps_ssh_config

DashboardDeployTargetKind = Literal["apex"]
DashboardDeployStatus = Literal["queued", "cloning", "deploying", "ready", "failed"]

_DASHBOARD_DEPLOYS_SUBDIR = "dashboard-deploys"

dashboard_deploy_router = APIRouter(tags=["dashboard-deploy"])
_DASHBOARD_DEPLOY_DISPATCHER: Callable[[str], None] | None = None
_is_stale_active_deploy = is_stale_active_deploy


def set_dashboard_deploy_dispatcher(dispatcher: Callable[[str], None] | None) -> None:
    """Registers the async dispatcher invoked after recording a dashboard deploy job."""
    global _DASHBOARD_DEPLOY_DISPATCHER
    _DASHBOARD_DEPLOY_DISPATCHER = dispatcher


class DashboardDeployConflictError(RuntimeError):
    """Raised when a dashboard deployment is already queued or running."""


class DashboardDeployPayload(BaseModel):
    """HTTP payload submitted from Dashboard Deployer to deploy main to App Base Domain."""

    target: DashboardDeployTargetKind = "apex"


class DashboardDeployRecord(BaseModel):
    """Durable state record for a Control-Plane-triggered dashboard deployment."""

    deploy_id: str
    target: DashboardDeployTargetKind = "apex"
    status: DashboardDeployStatus = "queued"
    current_label: str = "Queued dashboard deployment"
    target_url: str | None = None
    commit_short: str | None = None
    control_plane_url: str | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class DashboardDeployStatusResponse(BaseModel):
    """Response returned by GET /api/dashboard/deploy."""

    deploy: DashboardDeployRecord | None = None


class DashboardDeployStateMixin:
    """FactoryStateStore mixin persisting DashboardDeployRecord JSON files."""

    def create_dashboard_deploy(
        self,
        target: DashboardDeployTargetKind = "apex",
        *,
        control_plane_url: str | None = None,
    ) -> DashboardDeployRecord:
        """Persists a new queued DashboardDeployRecord if no active deployment is running."""
        return create_deploy_job(
            self,
            subdir=_DASHBOARD_DEPLOYS_SUBDIR,
            model_cls=DashboardDeployRecord,
            conflict_exc_cls=DashboardDeployConflictError,
            conflict_noun="Dashboard deployment",
            build_record=lambda: DashboardDeployRecord(
                deploy_id=f"dash-{uuid.uuid4().hex[:12]}",
                target=target,
                current_label="Queued production deploy (App Base Domain)",
                control_plane_url=control_plane_url,
            ),
        )

    def get_dashboard_deploy(self, deploy_id: str, *, reload: bool = True) -> DashboardDeployRecord | None:
        """Loads one DashboardDeployRecord by ID."""
        return get_deploy_job(
            self,
            subdir=_DASHBOARD_DEPLOYS_SUBDIR,
            model_cls=DashboardDeployRecord,
            deploy_id=deploy_id,
            reload=reload,
        )

    def get_latest_dashboard_deploy(self, *, reload: bool = True) -> DashboardDeployRecord | None:
        """Returns the most recent DashboardDeployRecord, if any."""
        return get_latest_deploy_job(
            self,
            subdir=_DASHBOARD_DEPLOYS_SUBDIR,
            model_cls=DashboardDeployRecord,
            reload=reload,
        )

    def update_dashboard_deploy(
        self,
        deploy_id: str,
        *,
        append_logs: list[str] | None = None,
        **updates: Any,
    ) -> DashboardDeployRecord:
        """Reloads, updates fields/logs on a DashboardDeployRecord, and commits."""
        return update_deploy_job(
            self,
            subdir=_DASHBOARD_DEPLOYS_SUBDIR,
            model_cls=DashboardDeployRecord,
            deploy_id=deploy_id,
            missing_label="Dashboard deploy",
            append_logs=append_logs,
            **updates,
        )


def resolve_control_plane_ssh_private_key() -> str:
    """Resolves the VPS SSH private key from Modal secrets or Central Config Store vault."""
    inline = os.environ.get("RESOURCE_PLANE_SSH_PRIVATE_KEY", "")
    if inline.strip():
        return inline

    org_name = os.environ.get("GH_ORG_NAME", "").strip()
    gh_token = resolve_gh_token()
    age_key = os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")
    if org_name and gh_token and age_key:
        decrypted = fetch_vault_env_raw(
            "software-factory",
            org_name=org_name,
            gh_token=gh_token,
            age_key=age_key,
            target_filename="resource_plane_ssh",
        )
        if decrypted and decrypted.strip():
            return decrypted

    raise ValueError(
        "Missing VPS SSH private key. Redeploy the Modal Control Plane with RESOURCE_PLANE_SSH_KEY configured "
        "or push resource_plane_ssh to config/env/software-factory/ with AGE_PRIVATE_KEY configured."
    )


def ensure_headless_ssh_config(ssh_dir: Path | None = None) -> None:
    """Configures non-interactive SSH host key acceptance for headless Modal deploy workers."""
    target_dir = ssh_dir or (Path.home() / ".ssh")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o700)
    cfg_path = target_dir / "config"
    existing = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    if "StrictHostKeyChecking accept-new" not in existing:
        block = "Host *\n  BatchMode yes\n  StrictHostKeyChecking accept-new\n"
        content = (existing.rstrip() + "\n\n" + block) if existing.strip() else block
        cfg_path.write_text(content, encoding="utf-8")
    cfg_path.chmod(0o600)


def execute_dashboard_self_deploy(
    deploy_id: str,
    *,
    store: Any = None,
    clone_fn: Callable[..., str] | None = None,
    deploy_fn: Callable[..., int] | None = None,
    resolve_ssh_key_fn: Callable[[], str] | None = None,
) -> DashboardDeployRecord:
    """Executes one queued dashboard self-deployment job inside the Modal worker."""
    from sandbox.apps._store import get_default_store

    active_store = store or get_default_store()
    record = active_store.get_dashboard_deploy(deploy_id)
    if record is None:
        raise KeyError(f"Dashboard deploy '{deploy_id}' not found.")

    logs: list[str] = []

    def _log(msg: str) -> None:
        logs.append(msg)

    tmp_dir = Path(tempfile.mkdtemp(prefix="sf-dash-deploy-"))
    try:
        active_store.update_dashboard_deploy(
            deploy_id,
            status="cloning",
            current_label="Cloning latest main from GitHub",
        )
        org_name = os.environ.get("GH_ORG_NAME", "").strip()
        gh_token = resolve_gh_token()
        if not org_name or not gh_token:
            raise ValueError("GH_ORG_NAME and GH_TOKEN are required in Control Plane secrets.")

        private_key = (resolve_ssh_key_fn or resolve_control_plane_ssh_private_key)()
        ensure_headless_ssh_config()
        key_file = tmp_dir / "vps_ssh_key"
        normalized_key = private_key if private_key.endswith("\n") else f"{private_key}\n"
        key_file.write_text(normalized_key, encoding="utf-8")
        key_file.chmod(0o600)
        vps_cfg = resolve_vps_ssh_config(key_path=key_file, dotenv=dict(os.environ))

        repo_dir = tmp_dir / "repo"
        commit_short = (clone_fn or clone_latest_main)(repo_dir, org_name=org_name, gh_token=gh_token)
        logs.append(f"Cloned {org_name}/software-factory@main ({commit_short}).")

        active_store.update_dashboard_deploy(
            deploy_id,
            status="deploying",
            commit_short=commit_short,
            current_label=f"Deploying {commit_short} to App Base Domain",
            append_logs=logs[-1:],
        )

        clean_base = resolve_apps_base_domain(None, dotenv=dict(os.environ))
        target_url = f"https://{clean_base}"

        runner = deploy_fn or deploy_dashboard
        code = runner(
            vps_cfg,
            factory_root=repo_dir,
            dotenv=dict(os.environ),
            control_plane_url=record.control_plane_url,
            dashboard_commit=commit_short,
            stream=False,
            log_cb=_log,
        )
        if code != 0:
            raise RuntimeError(logs[-1] if logs else f"Dashboard deployment failed with exit code {code}.")

        return active_store.update_dashboard_deploy(
            deploy_id,
            status="ready",
            target_url=target_url,
            commit_short=commit_short,
            current_label=f"Live at {target_url}",
            append_logs=logs[1:],
            error=None,
        )
    except Exception as exc:
        extra_logs = [*logs[1:], f"❌ {exc}"] if logs else [f"❌ {exc}"]
        return active_store.update_dashboard_deploy(
            deploy_id,
            status="failed",
            current_label="Deployment failed",
            error=str(exc),
            append_logs=extra_logs,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _infer_control_plane_url(request: Request) -> str | None:
    explicit = os.environ.get("SANDBOX_DASHBOARD_UPSTREAM", "").strip()
    if explicit:
        return explicit
    host = (request.url.hostname or "").strip().lower()
    if not host or host in ("testserver", "localhost", "127.0.0.1"):
        return None
    base_raw = os.environ.get("APPS_BASE_DOMAIN", "").strip()
    if base_raw:
        try:
            if is_subdomain_of(host, normalize_base_domain(base_raw)):
                return None
        except ValueError:
            pass
    if host.endswith(".modal.run"):
        return f"{request.url.scheme}://{request.url.netloc}"
    return None


def _dispatch_dashboard_deploy(deploy_id: str) -> None:
    if _DASHBOARD_DEPLOY_DISPATCHER is not None:
        _DASHBOARD_DEPLOY_DISPATCHER(deploy_id)
        return
    threading.Thread(
        target=execute_dashboard_self_deploy,
        args=(deploy_id,),
        daemon=True,
    ).start()


@dashboard_deploy_router.post(
    "/api/dashboard/deploy",
    response_model=DashboardDeployRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
def api_trigger_dashboard_deploy(
    request: Request,
    payload: DashboardDeployPayload | None = None,
) -> DashboardDeployRecord:
    """Queues an async deployment of dashboard/ (main branch) to App Base Domain."""
    from sandbox.apps._store import get_default_store

    store = get_default_store()
    cp_url = _infer_control_plane_url(request)
    target = payload.target if payload is not None else "apex"
    try:
        record = store.create_dashboard_deploy(target, control_plane_url=cp_url)
    except DashboardDeployConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _dispatch_dashboard_deploy(record.deploy_id)
    return record


@dashboard_deploy_router.get(
    "/api/dashboard/deploy",
    response_model=DashboardDeployStatusResponse,
)
def api_get_latest_dashboard_deploy() -> DashboardDeployStatusResponse:
    """Returns the latest dashboard deployment record, if one exists."""
    from sandbox.apps._store import get_default_store

    return DashboardDeployStatusResponse(deploy=get_default_store().get_latest_dashboard_deploy())


@dashboard_deploy_router.get(
    "/api/dashboard/deploy/{deploy_id}",
    response_model=DashboardDeployRecord,
)
def api_get_dashboard_deploy(deploy_id: str) -> DashboardDeployRecord:
    """Returns current durable status and logs for one dashboard deployment."""
    from sandbox.apps._store import get_default_store

    record = get_default_store().get_dashboard_deploy(deploy_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard deploy '{deploy_id}' not found",
        )
    return record
