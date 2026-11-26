"""Optional factory cloud wiring for GitHub, Resource Plane, env-store, and Modal sandboxes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import urllib.error
import urllib.request

from sandbox.app_scaffolder._template import CloudWiringOptions
from sandbox.config import resolve_factory_credentials, resolve_factory_root
from sandbox.core import LaunchRequest, LaunchResponse
from sandbox.db_host import DatabaseConnectionInfo, create_database_connection
from sandbox.db_host_client import update_env_file
from sandbox.env_store import resolve_gh_token
from sandbox.env_store_push import push_repo_env
from sandbox.launcher import launch_sandbox
from sandbox.s3_host import S3BucketInfo, create_s3_bucket, write_s3_env_vars


@dataclass
class CloudWiringResult:
    """Summary of cloud resources created and wired for a scaffolded application."""

    github_repo: str | None = None
    database_info: DatabaseConnectionInfo | None = None
    s3_info: S3BucketInfo | None = None
    vault_pushed: bool = False
    launch_response: LaunchResponse | None = None
    deploy_result: Any = None


def sanitize_db_name(project_name: str) -> str:
    """Derives a safe PostgreSQL database identifier from project_name."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", project_name.strip().lower()).strip("_") or "app_db"
    if cleaned[0].isdigit():
        cleaned = f"app_{cleaned}"
    return cleaned[:48]


def sanitize_bucket_name(project_name: str) -> str:
    """Derives a valid S3 bucket name (3-63 lowercase chars/hyphens) from project_name."""
    cleaned = re.sub(r"[^a-z0-9-]+", "-", project_name.strip().lower()).strip("-") or "app-storage"
    if len(cleaned) < 3:
        cleaned = f"{cleaned}-app"[:63].strip("-")
    return cleaned[:63].strip("-")


def _github_api_request(
    method: str,
    api_path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Performs an authenticated GitHub REST API request returning (status_code, json_body)."""
    url = f"https://api.github.com{api_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "software-factory-create-app",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"message": raw}
        return exc.code, body


def _resolve_repo_owner_and_name(
    project_name: str,
    repo_name: str | None,
    org_name: str | None,
    default_org: str | None,
) -> tuple[str, str]:
    """Resolves (owner, bare_repo_name) for GitHub and env-store operations."""
    raw = (repo_name or project_name).strip().rstrip("/")
    if "/" in raw:
        owner, bare = raw.split("/", 1)
        return owner, bare
    owner = (org_name or default_org or "").strip()
    if not owner:
        raise ValueError(
            "GitHub organization/owner not set. Configure GH_ORG_NAME in .env or pass --repo owner/name."
        )
    return owner, raw


def _push_git_branch(project_dir: Path, remote_url: str, token: str) -> None:
    """Sets clean HTTPS origin remote and pushes current branch using ephemeral auth header."""
    existing = subprocess.run(
        ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.returncode == 0:
        subprocess.run(["git", "-C", str(project_dir), "remote", "set-url", "origin", remote_url], check=True)
    else:
        subprocess.run(["git", "-C", str(project_dir), "remote", "add", "origin", remote_url], check=True)

    head_check = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head_check.returncode != 0:
        raise RuntimeError(
            "Cannot push to GitHub because no commit exists yet. Configure Git user.name and user.email first."
        )

    basic_token = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    push_cmd = [
        "git",
        "-C",
        str(project_dir),
        "-c",
        "credential.helper=",
        "-c",
        f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic_token}",
        "push",
        "-u",
        "origin",
        "HEAD",
    ]
    res = subprocess.run(push_cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to push repository to {remote_url}: {res.stderr.strip()}")


def ensure_github_repo_and_push(
    project_dir: Path,
    owner: str,
    repo_name: str,
    *,
    public: bool = False,
    gh_token: str | None = None,
    api_fn: Any = None,
    push_fn: Any = None,
) -> str:
    """Ensures github.com/<owner>/<repo_name> exists and pushes HEAD without persisting tokens."""
    token = resolve_gh_token(gh_token)
    if not token:
        raise ValueError("GitHub token (GH_TOKEN) is required for --github.")

    call_api = api_fn or _github_api_request
    do_push = push_fn or _push_git_branch

    status_code, repo_data = call_api("GET", f"/repos/{owner}/{repo_name}", token, None)
    if status_code == 404:
        payload = {"name": repo_name, "private": not public, "auto_init": False}
        create_code, created_data = call_api("POST", f"/orgs/{owner}/repos", token, payload)
        if create_code == 404:
            # Owner may be a personal user account rather than an organization
            create_code, created_data = call_api("POST", "/user/repos", token, payload)
        if create_code not in (200, 201):
            detail = created_data.get("message", f"HTTP {create_code}")
            raise RuntimeError(f"Failed to create GitHub repository {owner}/{repo_name}: {detail}")
        repo_data = created_data
    elif status_code != 200:
        detail = repo_data.get("message", f"HTTP {status_code}")
        raise RuntimeError(f"Failed checking GitHub repository {owner}/{repo_name}: {detail}")

    full_name = repo_data.get("full_name") or f"{owner}/{repo_name}"
    remote_url = repo_data.get("clone_url") or f"https://github.com/{full_name}.git"
    do_push(project_dir, remote_url, token)
    return full_name


def wire_cloud_resources(
    project_name: str,
    project_dir: Path,
    options: CloudWiringOptions,
    *,
    repo_root: Path | None = None,
    create_db_fn: Any = None,
    create_s3_fn: Any = None,
    push_vault_fn: Any = None,
    launch_fn: Any = None,
    github_fn: Any = None,
    deploy_fn: Any = None,
) -> CloudWiringResult:
    """Executes requested cloud provisioning steps after local App Template scaffolding."""
    creds = resolve_factory_credentials(repo_root=repo_root or resolve_factory_root(), mutate_environ=True)
    extra_env = creds.extra_env
    gh_token = os.environ.get("GH_TOKEN") or creds.gh_token or resolve_gh_token()
    default_org = os.environ.get("GH_ORG_NAME") or creds.gh_org_name
    rp_domain = (
        os.environ.get("RESOURCE_PLANE_DOMAIN")
        or extra_env.get("RESOURCE_PLANE_DOMAIN")
        or os.environ.get("DB_HOST_DOMAIN")
        or extra_env.get("DB_HOST_DOMAIN")
    )
    rp_token = (
        os.environ.get("RESOURCE_PLANE_ADMIN_TOKEN")
        or extra_env.get("RESOURCE_PLANE_ADMIN_TOKEN")
        or os.environ.get("DB_HOST_ADMIN_TOKEN")
        or extra_env.get("DB_HOST_ADMIN_TOKEN")
    )

    result = CloudWiringResult()
    owner = options.org_name or default_org
    bare_repo = (options.repo_name or project_name).strip().rstrip("/").rsplit("/", 1)[-1]
    needs_github_owner = options.github or options.push_vault or options.launch
    if needs_github_owner or "/" in (options.repo_name or ""):
        owner, bare_repo = _resolve_repo_owner_and_name(
            project_name, options.repo_name, options.org_name, default_org
        )
    target_repo = f"{owner}/{bare_repo}" if owner else bare_repo
    env_file = project_dir / ".env"

    if options.github:
        gh_impl = github_fn or ensure_github_repo_and_push
        result.github_repo = gh_impl(
            project_dir,
            owner,
            bare_repo,
            public=options.public_repo,
            gh_token=gh_token,
        )

    if options.provision_db:
        db_impl = create_db_fn or create_database_connection
        db_name = options.db_name or sanitize_db_name(bare_repo)
        db_info = db_impl(
            database_name=db_name,
            project_name=bare_repo,
            domain=rp_domain,
            token=rp_token,
        )
        update_env_file(env_file, "DATABASE_URL", db_info.connection_string)
        result.database_info = db_info

    if options.provision_s3:
        s3_impl = create_s3_fn or create_s3_bucket
        bucket_name = options.bucket_name or sanitize_bucket_name(bare_repo)
        s3_info = s3_impl(
            bucket_name=bucket_name,
            project_name=bare_repo,
            domain=rp_domain,
            token=rp_token,
        )
        write_s3_env_vars(env_file, s3_info)
        result.s3_info = s3_info

    if options.push_vault:
        push_impl = push_vault_fn or push_repo_env
        push_res = push_impl(
            repo_dir=project_dir,
            env_file=env_file,
            repo_name=bare_repo,
            org_name=owner,
            gh_token=gh_token,
        )
        if not getattr(push_res, "success", False):
            raise RuntimeError(f"Failed pushing secrets to env-store: {getattr(push_res, 'message', push_res)}")
        result.vault_pushed = True

    if options.launch:
        launcher = launch_fn or launch_sandbox
        req = LaunchRequest(
            repo=target_repo,
            t3=options.t3,
            react_native=options.mobile_app,
            vm=options.vm,
            profile=options.profile,
        )
        launched = launcher(req, register_ssh_config=True)
        result.launch_response = launched.to_response() if hasattr(launched, "to_response") else launched[1]

    if options.deploy:
        from sandbox.app_deploy import AppDeployRequest, deploy_app

        deploy_impl = deploy_fn or deploy_app
        deploy_req = AppDeployRequest(
            target=str(project_dir),
            repo=target_repo if (options.repo_name or options.github or options.org_name) else None,
            subdomain=options.subdomain,
            base_domain=options.base_domain,
            skip_migrate=options.skip_migrate,
            profile=options.profile,
        )
        result.deploy_result = deploy_impl(deploy_req, repo_root=repo_root)

    return result
