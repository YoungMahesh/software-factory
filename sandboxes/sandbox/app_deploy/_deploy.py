"""Remote SSH deployment and teardown orchestration for Hosted Apps."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import shlex
import sys

from sandbox.caddy_deploy import ensure_docker_network
from sandbox.caddy_wildcard import (
    DEFAULT_CADDY_NETWORK,
    _read_remote,
    _ssh_run,
    _write_remote_b64,
    ensure_wildcard_caddy,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
)
from sandbox.config import parse_env_file, resolve_factory_credentials, resolve_factory_root
from sandbox.db_host_client import get_or_download_ca_cert, normalize_base_url
from sandbox.env_store import resolve_gh_token, resolve_sandbox_bundle
from sandbox.source_transfer import stream_source_archive
from sandbox.infra_deploy import (
    VpsSshConfig,
    build_ssh_cmd,
    check_remote_docker,
    check_ssh_connection,
    resolve_vps_ssh_config,
)

from ._caddy import ensure_app_caddy_route, remove_app_caddy_route
from ._ownership import claim_hosted_app
from ._config import (
    AppDeployRequest,
    AppDeployResult,
    AppTeardownResult,
    build_remote_app_env,
    resolve_app_domain,
    resolve_deploy_target,
    serialize_dotenv,
)


def sync_local_app_to_vps(
    vps_config: VpsSshConfig,
    local_dir: Path,
    remote_dir: str,
    timeout: int = 180,
) -> None:
    """Streams a local app directory to remote_dir on the VPS via tar over SSH."""
    tar_cmd = [
        "tar",
        "-czf",
        "-",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=.next",
        "--exclude=.env",
        "--exclude=.env.*",
        "--exclude=.certs",
        "--exclude=.expo",
        "--exclude=apps/mobile/android",
        "--exclude=apps/mobile/ios",
        "-C",
        str(local_dir),
        ".",
    ]
    ssh_cmd = build_ssh_cmd(vps_config, f"mkdir -p '{remote_dir}' && tar -xzf - -C '{remote_dir}'")
    try:
        stream_source_archive(tar_cmd, ssh_cmd, timeout=timeout)
    except (RuntimeError, OSError) as exc:
        raise RuntimeError(f"Failed syncing '{local_dir}' to {remote_dir}: {exc}") from exc


def sync_github_app_on_vps(
    vps_config: VpsSshConfig,
    owner: str,
    bare_repo: str,
    branch: str,
    remote_dir: str,
    gh_token: str,
    timeout: int = 180,
) -> None:
    """Clones or pulls github.com/<owner>/<bare_repo> at remote_dir using ephemeral auth."""
    basic_b64 = base64.b64encode(f"x-access-token:{gh_token}".encode("utf-8")).decode("ascii")
    clean_url = f"https://github.com/{owner}/{bare_repo}.git"
    auth_cfg = f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic_b64}"
    directory = shlex.quote(remote_dir)
    branch_arg = shlex.quote(branch)
    url_arg = shlex.quote(clean_url)
    auth_arg = shlex.quote(auth_cfg)
    script = f"""set -e
if [ -d {directory}/.git ]; then
    git -C {directory} remote set-url origin {url_arg}
    git -C {directory} -c credential.helper= -c {auth_arg} fetch origin {branch_arg} --depth 50
    git -C {directory} checkout -B {branch_arg} FETCH_HEAD
elif [ -e {directory} ] && [ -n "$(ls -A {directory} 2>/dev/null)" ]; then
    echo 'Remote directory exists and is not a git clone.' >&2
    exit 1
else
    rm -rf {directory}
    git -c credential.helper= -c {auth_arg} clone --depth 50 --branch {branch_arg} --single-branch {url_arg} {directory}
fi
"""
    res = _ssh_run(vps_config, script, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"Failed cloning/pulling {owner}/{bare_repo} on VPS: {res.stderr.strip() or res.stdout.strip()}")


def stage_remote_ca_cert(
    vps_config: VpsSshConfig,
    remote_dir: str,
    rp_domain: str | None,
    *,
    local_dir: Path | None = None,
) -> bool:
    """Writes Resource Plane root CA certificate to <remote_dir>/.certs/ca.crt when available."""
    cert_text = ""
    if local_dir and (local_dir / ".certs" / "ca.crt").is_file():
        cert_text = (local_dir / ".certs" / "ca.crt").read_text(encoding="utf-8")
    elif rp_domain and rp_domain.strip():
        try:
            ca_path = get_or_download_ca_cert(normalize_base_url(rp_domain))
            cert_text = ca_path.read_text(encoding="utf-8")
        except Exception:
            cert_text = ""

    if cert_text and "BEGIN CERTIFICATE" in cert_text:
        ok, msg = _write_remote_b64(vps_config, f"{remote_dir}/.certs/ca.crt", cert_text, mode="0644")
        if not ok:
            raise RuntimeError(msg)
        return True

    fallback_script = (
        f"if [ -s /opt/resource-plane/.data/certs/ca.crt ]; then "
        f"  mkdir -p '{remote_dir}/.certs' && cp /opt/resource-plane/.data/certs/ca.crt '{remote_dir}/.certs/ca.crt' && echo copied; "
        f"fi"
    )
    res = _ssh_run(vps_config, fallback_script, timeout=15)
    return res.returncode == 0 and "copied" in res.stdout


def _resolve_base_env(
    source_mode: str,
    local_dir: Path | None,
    bare_repo: str,
    org_name: str | None,
    gh_token: str | None,
    remote_existing_env: str,
) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if remote_existing_env:
        env_map.update(parse_env_file(remote_existing_env))

    if source_mode == "local" and local_dir is not None:
        local_env = local_dir / ".env"
        if local_env.is_file():
            env_map.update(parse_env_file(local_env))
        elif (local_dir / ".env.example").is_file() and not env_map:
            env_map.update(parse_env_file(local_dir / ".env.example"))
        return env_map

    if org_name and gh_token:
        bundle = resolve_sandbox_bundle(bare_repo, org_name=org_name, token=gh_token)
        if bundle and bundle.env_dict:
            env_map.update(bundle.env_dict)
    return env_map


def _maybe_ensure_wildcard_ready(
    vps_config: VpsSshConfig,
    base_domain: str,
    cf_token_arg: str | None,
    dotenv: dict[str, str],
) -> str | None:
    ok_wc, wc_content = _read_remote(vps_config, "/opt/caddy/conf/sites/apps-wildcard.caddy")
    if not ok_wc:
        raise RuntimeError(wc_content)
    if wc_content.strip():
        return None
    cf_token = resolve_cloudflare_dns_token(cf_token_arg, dotenv=dotenv)
    wc_ok, wc_msg = ensure_wildcard_caddy(vps_config, base_domain, cf_token, bootstrap=False)
    if not wc_ok:
        raise RuntimeError(wc_msg)
    return cf_token


def deploy_app(
    req: AppDeployRequest,
    *,
    repo_root: Path | None = None,
    cwd: Path | None = None,
) -> AppDeployResult:
    """Deploys or redeploys a Hosted App to /root/<repo-name> and exposes it on <sub.base>."""
    factory_root = repo_root or resolve_factory_root()
    dotenv = parse_env_file(factory_root / ".env") if (factory_root / ".env").is_file() else {}
    resolve_factory_credentials(repo_root=factory_root, env=dotenv, mutate_environ=True)

    vps_config = resolve_vps_ssh_config(
        host=req.host, user=req.user, port=req.port, key_path=req.key_path, dotenv=dotenv
    )
    base_domain = resolve_apps_base_domain(req.base_domain, dotenv=dotenv)
    default_org = os.environ.get("GH_ORG_NAME") or dotenv.get("GH_ORG_NAME")
    gh_token = resolve_gh_token(dotenv.get("GH_TOKEN") or dotenv.get("GITHUB_TOKEN"))

    target = resolve_deploy_target(req.target, req.repo, cwd=cwd, default_org=default_org)
    if target.source_mode == "github" and (not target.org_name or not gh_token):
        raise ValueError("Remote --repo deploy requires GH_ORG_NAME and GH_TOKEN configured.")

    _, fqdn = resolve_app_domain(target.app_slug, base_domain, req.subdomain)
    remote_dir = target.remote_directory(req.remote_base_dir)
    container_name = f"{target.app_slug}-web"

    if not check_ssh_connection(vps_config):
        raise RuntimeError(f"Cannot connect via SSH to {vps_config.user}@{vps_config.host}:{vps_config.port}.")
    docker_ok, docker_msg = check_remote_docker(vps_config)
    if not docker_ok:
        raise RuntimeError(docker_msg)

    with claim_hosted_app(vps_config, target, remote_dir, domain=fqdn) as ownership:
        remote_dir = ownership.remote_dir
        print(f"🚀 Deploying Hosted App '{target.bare_repo}' to {vps_config.user}@{vps_config.host}:{remote_dir}")
        print(f"   Public URL: https://{fqdn}")
        cf_token = _maybe_ensure_wildcard_ready(vps_config, base_domain, req.cf_dns_token, dotenv)
        env_ok, existing_remote_env = _read_remote(vps_config, f"{remote_dir}/.env")
        if not env_ok:
            raise RuntimeError(existing_remote_env)
        base_env = _resolve_base_env(
            target.source_mode, target.local_dir, target.bare_repo, target.org_name, gh_token, existing_remote_env
        )
        remote_env = build_remote_app_env(base_env, fqdn=fqdn, container_name=container_name)

        ownership.ensure_locked()
        if target.source_mode == "local":
            assert target.local_dir is not None
            print(f"==> Syncing local workspace '{target.local_dir}' -> '{remote_dir}'...")
            sync_local_app_to_vps(vps_config, target.local_dir, remote_dir)
        else:
            assert target.org_name is not None and gh_token is not None
            print(f"==> Syncing GitHub repository '{target.org_name}/{target.bare_repo}' -> '{remote_dir}'...")
            sync_github_app_on_vps(vps_config, target.org_name, target.bare_repo, req.branch, remote_dir, gh_token)

        compose_check = _ssh_run(vps_config, f"test -f '{remote_dir}/docker-compose.yml' && echo ok || echo missing", timeout=15)
        if compose_check.stdout.strip() != "ok":
            raise RuntimeError(
                f"Missing '{remote_dir}/docker-compose.yml'. Scaffold with updated app-template or add docker-compose.yml."
            )

        ownership.ensure_locked()
        ok_env, msg_env = _write_remote_b64(vps_config, f"{remote_dir}/.env", serialize_dotenv(remote_env), mode="0600")
        if not ok_env:
            raise RuntimeError(msg_env)

        rp_domain = (
            os.environ.get("RESOURCE_PLANE_DOMAIN")
            or dotenv.get("RESOURCE_PLANE_DOMAIN")
            or os.environ.get("DB_HOST_DOMAIN")
            or dotenv.get("DB_HOST_DOMAIN")
        )
        stage_remote_ca_cert(vps_config, remote_dir, rp_domain, local_dir=target.local_dir)

        net_ok, net_msg = ensure_docker_network(vps_config, DEFAULT_CADDY_NETWORK)
        if not net_ok:
            raise RuntimeError(net_msg)

        ownership.ensure_locked()
        print("==> Building Hosted App container...")
        build_res = subprocess.run(
            build_ssh_cmd(vps_config, f"cd '{remote_dir}' && docker compose -p '{target.app_slug}' build"),
            timeout=600, capture_output=False, check=False,
        )
        if build_res.returncode != 0:
            raise RuntimeError(f"Docker build failed in '{remote_dir}' (exit code {build_res.returncode}).")

        migrated = False
        if not req.skip_migrate:
            mig_probe = _ssh_run(
                vps_config,
                f"if [ -d '{remote_dir}/apps/web/drizzle' ] && ls '{remote_dir}/apps/web/drizzle'/*.sql >/dev/null 2>&1; then echo yes; else echo no; fi",
                timeout=15,
            )
            if mig_probe.stdout.strip() == "yes":
                print("==> Applying Drizzle database migrations...")
                mig_res = subprocess.run(
                    build_ssh_cmd(vps_config, f"cd '{remote_dir}' && docker compose -p '{target.app_slug}' --profile migrate run --rm migrate"),
                    timeout=300, capture_output=False, check=False,
                )
                if mig_res.returncode != 0:
                    raise RuntimeError(f"Database migration failed in '{remote_dir}' (exit code {mig_res.returncode}).")
                migrated = True

        ownership.ensure_locked()
        print("==> Starting Hosted App container...")
        up_res = subprocess.run(
            build_ssh_cmd(vps_config, f"cd '{remote_dir}' && docker compose -p '{target.app_slug}' up -d --remove-orphans"),
            timeout=180, capture_output=False, check=False,
        )
        if up_res.returncode != 0:
            raise RuntimeError(f"Failed starting containers in '{remote_dir}' (exit code {up_res.returncode}).")

        health_script = (
            f"for i in $(seq 1 30); do "
            f"  st=$(docker inspect -f '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}{{{{.State.Status}}}}{{{{end}}}}' '{container_name}' 2>/dev/null || true); "
            f"  if [ \"$st\" = 'healthy' ] || [ \"$st\" = 'running' ]; then echo ok; exit 0; fi; "
            f"  sleep 1; "
            f"done; "
            f"docker compose -f '{remote_dir}/docker-compose.yml' -p '{target.app_slug}' logs --tail=40 >&2; exit 1"
        )
        h_res = _ssh_run(vps_config, health_script, timeout=45)
        if h_res.returncode != 0 or "ok" not in h_res.stdout:
            raise RuntimeError(f"Container '{container_name}' failed readiness check:\n{h_res.stderr.strip()}")

        ownership.ensure_locked()
        print(f"==> Wiring Caddy wildcard route https://{fqdn} -> {container_name}:3000...")
        route_ok, route_msg = ensure_app_caddy_route(
            vps_config,
            target.app_slug,
            fqdn,
            f"{container_name}:3000",
            base_domain=base_domain,
            cf_dns_token=cf_token,
            ownership=ownership.metadata,
        )
        if not route_ok:
            raise RuntimeError(route_msg)
        print(f"   ✓ {route_msg}")

        if req.sync_caddy_store:
            from sandbox.caddy_store import maybe_sync_after_deploy
            if maybe_sync_after_deploy(vps_config, req.profile) != 0:
                print("⚠️  Warning: caddy-store sync failed.", file=sys.stderr)

        return AppDeployResult(
            repo_name=target.bare_repo,
            app_slug=target.app_slug,
            remote_dir=remote_dir,
            domain=fqdn,
            url=f"https://{fqdn}",
            container_name=container_name,
            source_mode=target.source_mode,
            migrated=migrated,
        )


def teardown_app(
    req: AppDeployRequest,
    *,
    purge: bool = False,
    repo_root: Path | None = None,
    cwd: Path | None = None,
) -> AppTeardownResult:
    """Stops a Hosted App stack on the VPS and removes its Caddy wildcard route."""
    factory_root = repo_root or resolve_factory_root()
    dotenv = parse_env_file(factory_root / ".env") if (factory_root / ".env").is_file() else {}
    vps_config = resolve_vps_ssh_config(
        host=req.host, user=req.user, port=req.port, key_path=req.key_path, dotenv=dotenv
    )
    default_org = os.environ.get("GH_ORG_NAME") or dotenv.get("GH_ORG_NAME")
    target = resolve_deploy_target(req.target, req.repo, cwd=cwd, default_org=default_org)
    remote_dir = target.remote_directory(req.remote_base_dir)

    if not check_ssh_connection(vps_config):
        raise RuntimeError(f"Cannot connect via SSH to {vps_config.user}@{vps_config.host}:{vps_config.port}.")

    with claim_hosted_app(vps_config, target, remote_dir, create=False) as ownership:
        remote_dir = ownership.remote_dir
        ownership.ensure_locked()
        down_script = (
            f"set -e; if [ -f '{remote_dir}/docker-compose.yml' ]; then "
            f"cd '{remote_dir}' && docker compose -p '{target.app_slug}' down; fi"
        )
        res = _ssh_run(vps_config, down_script, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(f"Failed stopping '{remote_dir}': {res.stderr.strip()}")

        ownership.ensure_locked()
        rm_ok, rm_msg = remove_app_caddy_route(vps_config, target.app_slug)
        if not rm_ok:
            raise RuntimeError(rm_msg)

        if purge:
            ownership.ensure_locked()
            res = _ssh_run(vps_config, f"rm -rf '{remote_dir}'", timeout=30)
            if res.returncode != 0:
                raise RuntimeError(f"Failed purging '{remote_dir}': {res.stderr.strip()}")
            ownership.forget()

        if req.sync_caddy_store:
            from sandbox.caddy_store import maybe_sync_after_deploy
            maybe_sync_after_deploy(vps_config, req.profile)

        return AppTeardownResult(
            repo_name=target.bare_repo,
            app_slug=target.app_slug,
            remote_dir=remote_dir,
            purged=purge,
            message=f"Stopped Hosted App '{target.bare_repo}'. {rm_msg}",
        )
