"""Control-plane-backed Cloudflare Pages build and deploy endpoints for the Documentation Web App."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Literal
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sandbox._deploy_state import (
    clone_latest_main,
    create_deploy_job,
    get_deploy_job,
    get_latest_deploy_job,
    read_full_head_commit,
    update_deploy_job,
)
from sandbox.apps._models import utc_now_iso
from sandbox.caddy_wildcard import resolve_apps_base_domain
from sandbox.env_store import resolve_gh_token

DocsDeployStatus = Literal["queued", "cloning", "building", "deploying", "ready", "failed"]

DEFAULT_CLOUDFLARE_PAGES_PROJECT = "modal-sandboxes-docs"
DEFAULT_CLOUDFLARE_PAGES_BRANCH = "main"
_DOCS_DEPLOYS_SUBDIR = "docs-deploys"

docs_deploy_router = APIRouter(tags=["docs-deploy"])
_DOCS_DEPLOY_DISPATCHER: Callable[[str], None] | None = None


def set_docs_deploy_dispatcher(dispatcher: Callable[[str], None] | None) -> None:
    """Registers the async dispatcher invoked after recording a documentation deploy job."""
    global _DOCS_DEPLOY_DISPATCHER
    _DOCS_DEPLOY_DISPATCHER = dispatcher


class DocsDeployConflictError(RuntimeError):
    """Raised when a documentation deployment is already queued or running."""


class DocsDeployRecord(BaseModel):
    """Durable state record for a Control-Plane-triggered documentation deployment."""

    deploy_id: str
    status: DocsDeployStatus = "queued"
    current_label: str = "Queued documentation deploy (Cloudflare Pages)"
    target_url: str | None = None
    project_name: str | None = None
    branch: str | None = None
    commit: str | None = None
    commit_short: str | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class DocsDeployStatusResponse(BaseModel):
    """Response returned by GET /api/docs/deploy."""

    deploy: DocsDeployRecord | None = None


class DocsDeployStateMixin:
    """FactoryStateStore mixin persisting DocsDeployRecord JSON files."""

    def create_docs_deploy(self) -> DocsDeployRecord:
        """Persists a new queued DocsDeployRecord if no active docs deployment is running."""
        return create_deploy_job(
            self,
            subdir=_DOCS_DEPLOYS_SUBDIR,
            model_cls=DocsDeployRecord,
            conflict_exc_cls=DocsDeployConflictError,
            conflict_noun="Documentation deployment",
            build_record=lambda: DocsDeployRecord(
                deploy_id=f"docs-{uuid.uuid4().hex[:12]}",
                current_label="Queued documentation deploy (Cloudflare Pages)",
            ),
        )

    def get_docs_deploy(self, deploy_id: str, *, reload: bool = True) -> DocsDeployRecord | None:
        """Loads one DocsDeployRecord by ID."""
        return get_deploy_job(
            self,
            subdir=_DOCS_DEPLOYS_SUBDIR,
            model_cls=DocsDeployRecord,
            deploy_id=deploy_id,
            reload=reload,
        )

    def get_latest_docs_deploy(self, *, reload: bool = True) -> DocsDeployRecord | None:
        """Returns the most recent DocsDeployRecord, if any."""
        return get_latest_deploy_job(
            self,
            subdir=_DOCS_DEPLOYS_SUBDIR,
            model_cls=DocsDeployRecord,
            reload=reload,
        )

    def update_docs_deploy(
        self,
        deploy_id: str,
        *,
        append_logs: list[str] | None = None,
        **updates: Any,
    ) -> DocsDeployRecord:
        """Reloads, updates fields/logs on a DocsDeployRecord, and commits."""
        return update_deploy_job(
            self,
            subdir=_DOCS_DEPLOYS_SUBDIR,
            model_cls=DocsDeployRecord,
            deploy_id=deploy_id,
            missing_label="Documentation deploy",
            append_logs=append_logs,
            **updates,
        )


def resolve_docs_builder() -> str:
    """Locates Zensical (or MkDocs fallback) executable for strict documentation compilation."""
    python_bin_dir = Path(sys.executable).resolve().parent
    candidates = [
        python_bin_dir / "zensical",
        Path("/usr/local/bin/zensical"),
        python_bin_dir / "mkdocs",
        Path("/usr/local/bin/mkdocs"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    for name in ("zensical", "mkdocs"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Neither zensical nor mkdocs executable was found in Control Plane worker image.")


def resolve_wrangler_command() -> list[str]:
    """Locates the Wrangler CLI command for Cloudflare Pages upload."""
    if shutil.which("wrangler"):
        return ["wrangler"]
    if shutil.which("npx"):
        return ["npx", "wrangler"]
    raise RuntimeError("Neither wrangler nor npx was found in Control Plane worker image.")


def write_deploy_info_json(
    site_dir: Path,
    *,
    commit: str,
    commit_short: str,
    deployed_at: str | None = None,
) -> Path:
    """Writes static deploy-info.json metadata into the compiled documentation site/ output."""
    info_path = site_dir / "deploy-info.json"
    payload = {
        "commit": commit,
        "commit_short": commit_short,
        "deployed_at": deployed_at or utc_now_iso(),
    }
    info_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return info_path


def _append_process_output(output: str, log_cb: Callable[[str], None] | None) -> None:
    if not log_cb or not output:
        return
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if line:
            log_cb(line)


def build_docs_site(
    repo_dir: Path,
    *,
    commit: str,
    commit_short: str,
    log_cb: Callable[[str], None] | None = None,
) -> Path:
    """Compiles mkdocs.yml + docs/ in strict mode and writes /deploy-info.json into site/."""
    builder = resolve_docs_builder()
    if log_cb:
        log_cb(f"Building documentation with {Path(builder).name} (strict mode)...")
    res = subprocess.run(
        [builder, "build", "--strict", "-f", str(repo_dir / "mkdocs.yml")],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    _append_process_output(res.stdout, log_cb)
    _append_process_output(res.stderr, log_cb)
    if res.returncode != 0:
        raise RuntimeError(f"Documentation build failed with exit code {res.returncode}.")

    site_dir = repo_dir / "site"
    if not site_dir.is_dir():
        raise RuntimeError("Documentation build completed without generating site/ output directory.")

    write_deploy_info_json(site_dir, commit=commit, commit_short=commit_short)
    if log_cb:
        log_cb(f"Built site/ and wrote deploy-info.json ({commit_short}).")
    return site_dir


def publish_docs_to_cloudflare(
    site_dir: Path,
    *,
    project_name: str,
    branch: str,
    account_id: str,
    api_token: str,
    repo_dir: Path | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    """Uploads compiled static site/ to Cloudflare Pages using Wrangler."""
    wrangler_cmd = resolve_wrangler_command()
    if log_cb:
        log_cb(f"Publishing site/ to Cloudflare Pages project '{project_name}' (branch '{branch}')...")
    env = dict(os.environ)
    env["CI"] = "1"
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token
    cmd = [
        *wrangler_cmd,
        "pages",
        "deploy",
        str(site_dir),
        f"--project-name={project_name}",
        f"--branch={branch}",
        "--commit-dirty=true",
    ]
    res = subprocess.run(
        cmd,
        cwd=str(repo_dir or site_dir.parent),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    _append_process_output(res.stdout, log_cb)
    _append_process_output(res.stderr, log_cb)
    if res.returncode != 0:
        raise RuntimeError(f"Wrangler Cloudflare Pages publish failed with exit code {res.returncode}.")


def execute_docs_deploy(
    deploy_id: str,
    *,
    store: Any = None,
    clone_fn: Callable[..., str] | None = None,
    build_fn: Callable[..., Path] | None = None,
    publish_fn: Callable[..., None] | None = None,
) -> DocsDeployRecord:
    """Executes one queued documentation build and Cloudflare Pages deployment job."""
    from sandbox.apps._store import get_default_store

    active_store = store or get_default_store()
    record = active_store.get_docs_deploy(deploy_id)
    if record is None:
        raise KeyError(f"Documentation deploy '{deploy_id}' not found.")

    logs: list[str] = []
    flushed_count = 0

    def _log(msg: str) -> None:
        logs.append(msg)

    def _take_new_logs() -> list[str]:
        nonlocal flushed_count
        new_items = logs[flushed_count:]
        flushed_count = len(logs)
        return new_items

    tmp_dir = Path(tempfile.mkdtemp(prefix="sf-docs-deploy-"))
    try:
        org_name = os.environ.get("GH_ORG_NAME", "").strip()
        gh_token = resolve_gh_token()
        if not org_name or not gh_token:
            raise ValueError("GH_ORG_NAME and GH_TOKEN are required in Hosted Sandbox Control Plane secrets.")

        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        if not account_id or not api_token:
            raise ValueError(
                "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required in Hosted Sandbox Control Plane secrets."
            )

        clean_base = resolve_apps_base_domain(None, dotenv=dict(os.environ))
        target_url = f"https://docs.{clean_base}"
        project_name = (os.environ.get("CLOUDFLARE_PAGES_PROJECT") or "").strip() or DEFAULT_CLOUDFLARE_PAGES_PROJECT
        branch = (os.environ.get("CLOUDFLARE_PAGES_BRANCH") or "").strip() or DEFAULT_CLOUDFLARE_PAGES_BRANCH

        active_store.update_docs_deploy(
            deploy_id,
            status="cloning",
            target_url=target_url,
            project_name=project_name,
            branch=branch,
            current_label="Cloning latest main from GitHub",
        )

        repo_dir = tmp_dir / "repo"
        commit_short = (clone_fn or clone_latest_main)(repo_dir, org_name=org_name, gh_token=gh_token)
        commit_full = read_full_head_commit(repo_dir, commit_short)
        _log(f"Cloned {org_name}/software-factory@main ({commit_short}).")

        active_store.update_docs_deploy(
            deploy_id,
            status="building",
            commit=commit_full,
            commit_short=commit_short,
            current_label=f"Building documentation ({commit_short})",
            append_logs=_take_new_logs(),
        )

        site_dir = (build_fn or build_docs_site)(
            repo_dir,
            commit=commit_full,
            commit_short=commit_short,
            log_cb=_log,
        )

        active_store.update_docs_deploy(
            deploy_id,
            status="deploying",
            current_label=f"Publishing {commit_short} to docs.{clean_base}",
            append_logs=_take_new_logs() or None,
        )

        (publish_fn or publish_docs_to_cloudflare)(
            site_dir,
            project_name=project_name,
            branch=branch,
            account_id=account_id,
            api_token=api_token,
            repo_dir=repo_dir,
            log_cb=_log,
        )
        _log(f"✅ Documentation Web App deployed to {target_url} (project: {project_name}, branch: {branch}).")

        return active_store.update_docs_deploy(
            deploy_id,
            status="ready",
            target_url=target_url,
            project_name=project_name,
            branch=branch,
            commit=commit_full,
            commit_short=commit_short,
            current_label=f"Live at {target_url}",
            append_logs=_take_new_logs(),
            error=None,
        )
    except Exception as exc:
        err_msg = f"❌ {exc}"
        return active_store.update_docs_deploy(
            deploy_id,
            status="failed",
            current_label="Deployment failed",
            error=str(exc),
            append_logs=[*_take_new_logs(), err_msg],
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _dispatch_docs_deploy(deploy_id: str) -> None:
    if _DOCS_DEPLOY_DISPATCHER is not None:
        _DOCS_DEPLOY_DISPATCHER(deploy_id)
        return
    threading.Thread(
        target=execute_docs_deploy,
        args=(deploy_id,),
        daemon=True,
    ).start()


@docs_deploy_router.post(
    "/api/docs/deploy",
    response_model=DocsDeployRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
def api_trigger_docs_deploy() -> DocsDeployRecord:
    """Queues an async Zensical build and Cloudflare Pages deployment from GitHub main."""
    from sandbox.apps._store import get_default_store

    store = get_default_store()
    try:
        record = store.create_docs_deploy()
    except DocsDeployConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _dispatch_docs_deploy(record.deploy_id)
    return record


@docs_deploy_router.get(
    "/api/docs/deploy",
    response_model=DocsDeployStatusResponse,
)
def api_get_latest_docs_deploy() -> DocsDeployStatusResponse:
    """Returns the latest documentation deployment record, if one exists."""
    from sandbox.apps._store import get_default_store

    return DocsDeployStatusResponse(deploy=get_default_store().get_latest_docs_deploy())


@docs_deploy_router.get(
    "/api/docs/deploy/{deploy_id}",
    response_model=DocsDeployRecord,
)
def api_get_docs_deploy(deploy_id: str) -> DocsDeployRecord:
    """Returns current durable status and logs for one documentation deployment."""
    from sandbox.apps._store import get_default_store

    record = get_default_store().get_docs_deploy(deploy_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documentation deploy '{deploy_id}' not found",
        )
    return record
