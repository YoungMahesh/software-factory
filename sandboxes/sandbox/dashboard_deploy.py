"""Remote deployment and Caddy ingress orchestration for Sandbox Web Dashboard and Dashboard Deployer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Callable

from sandbox.app_deploy._caddy import ensure_app_caddy_route, remove_app_caddy_route
from sandbox.app_deploy._config import serialize_dotenv
from sandbox.caddy_deploy import setup_reverse_proxy
from sandbox.caddy_wildcard import (
    DEFAULT_DASHBOARD_WEB_UPSTREAM,
    _write_remote_b64,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    resolve_dashboard_upstream,
)
from sandbox.config import parse_env_file, resolve_factory_root, resolve_web_ui_credentials
from sandbox.infra_deploy import (
    VpsSshConfig,
    build_ssh_cmd,
    check_remote_docker,
    check_ssh_connection,
    resolve_vps_ssh_config,
)
from sandbox.provenance import resolve_host_software_factory_provenance
from sandbox.source_transfer import stream_source_archive

DEFAULT_DASHBOARD_REMOTE_DIR = "/opt/sandbox-dashboard"
DEFAULT_DASHBOARD_CONTAINER = "sandbox-dashboard-web"
DEFAULT_DASHBOARD_COMPOSE_PROJECT = "sandbox-dashboard"

DEFAULT_LEGACY_STAGING_REMOTE_DIR = "/opt/sandbox-dashboard-staging"
DEFAULT_LEGACY_STAGING_CONTAINER = "sandbox-dashboard-staging-web"
DEFAULT_LEGACY_STAGING_COMPOSE_PROJECT = "sandbox-dashboard-staging"
DEFAULT_LEGACY_STAGING_APP_SLUG = "sandbox-dashboard"

DEFAULT_DEPLOYER_REMOTE_DIR = "/opt/dashboard-deployer"
DEFAULT_DEPLOYER_APP_SLUG = "dashboard-deployer"
DEFAULT_DEPLOYER_SUBDOMAIN = "deploy"
DEFAULT_DEPLOYER_CONTAINER = "dashboard-deployer-web"
DEFAULT_DEPLOYER_COMPOSE_PROJECT = "dashboard-deployer"
DEFAULT_DEPLOYER_UPSTREAM = "dashboard-deployer-web:3000"


@dataclass(frozen=True)
class VpsWebStackTarget:
    """VPS deployment target metadata for a Next.js factory stack."""

    label: str
    folder_name: str
    remote_dir: str
    container_name: str
    compose_project: str
    upstream: str


DASHBOARD_TARGET = VpsWebStackTarget(
    label="Sandbox Web Dashboard",
    folder_name="dashboard",
    remote_dir=DEFAULT_DASHBOARD_REMOTE_DIR,
    container_name=DEFAULT_DASHBOARD_CONTAINER,
    compose_project=DEFAULT_DASHBOARD_COMPOSE_PROJECT,
    upstream=DEFAULT_DASHBOARD_WEB_UPSTREAM,
)

DEPLOYER_TARGET = VpsWebStackTarget(
    label="Dashboard Deployer",
    folder_name="dashboard-deployer",
    remote_dir=DEFAULT_DEPLOYER_REMOTE_DIR,
    container_name=DEFAULT_DEPLOYER_CONTAINER,
    compose_project=DEFAULT_DEPLOYER_COMPOSE_PROJECT,
    upstream=DEFAULT_DEPLOYER_UPSTREAM,
)


def _find_compose_source_dir(folder_name: str, start_path: Path | None = None) -> Path:
    """Discovers a local Next.js stack directory containing deploy.sh and docker-compose.prod.yml."""
    current = (start_path or Path(__file__)).resolve()
    candidates = [
        resolve_factory_root() / folder_name,
        current.parent.parent / folder_name,
        current.parent.parent.parent / folder_name,
        Path.cwd() / folder_name,
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "deploy.sh").is_file() and (cand / "docker-compose.prod.yml").is_file():
            return cand
    raise FileNotFoundError(
        f"Could not locate local '{folder_name}' directory containing deploy.sh and docker-compose.prod.yml."
    )


def find_dashboard_source_dir(start_path: Path | None = None) -> Path:
    """Discovers the local dashboard directory containing deploy.sh and docker-compose.prod.yml."""
    return _find_compose_source_dir("dashboard", start_path)


def find_deployer_source_dir(start_path: Path | None = None) -> Path:
    """Discovers the local dashboard-deployer directory containing deploy.sh and docker-compose.prod.yml."""
    return _find_compose_source_dir("dashboard-deployer", start_path)


def _sync_dir_to_vps(
    config: VpsSshConfig,
    source_dir: Path,
    *,
    label: str,
    timeout: int = 180,
) -> bool:
    """Synchronizes a local Next.js workspace directory to the VPS via tar over SSH."""
    tar_cmd = [
        "tar",
        "-czf",
        "-",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=**/node_modules",
        "--exclude=.next",
        "--exclude=**/.next",
        "--exclude=.env",
        "--exclude=.env.*",
        "-C",
        str(source_dir.parent),
        source_dir.name,
    ]
    remote_extract = f"mkdir -p {shlex.quote(config.remote_dir)} && tar -xzf - -C {shlex.quote(config.remote_dir)} --strip-components=1"
    ssh_cmd = build_ssh_cmd(config, remote_extract)
    try:
        stream_source_archive(tar_cmd, ssh_cmd, timeout=timeout)
        return True
    except (RuntimeError, OSError) as exc:
        print(f"❌ {label} sync to VPS failed: {exc}", file=sys.stderr)
        return False


def sync_dashboard_to_vps(
    config: VpsSshConfig,
    source_dir: Path | None = None,
    timeout: int = 180,
) -> bool:
    """Synchronizes the local dashboard workspace to the VPS via tar over SSH."""
    return _sync_dir_to_vps(
        config,
        source_dir or find_dashboard_source_dir(),
        label="Dashboard",
        timeout=timeout,
    )


def sync_deployer_to_vps(
    config: VpsSshConfig,
    source_dir: Path | None = None,
    timeout: int = 180,
) -> bool:
    """Synchronizes the local dashboard-deployer workspace to the VPS via tar over SSH."""
    return _sync_dir_to_vps(
        config,
        source_dir or find_deployer_source_dir(),
        label="Dashboard Deployer",
        timeout=timeout,
    )


def execute_remote_dashboard_deploy(
    config: VpsSshConfig,
    *,
    stream: bool = True,
    timeout: int = 600,
) -> tuple[int, str]:
    """Executes ./deploy.sh inside the remote VPS stack directory."""
    remote_script = f"cd {shlex.quote(config.remote_dir)} && chmod +x deploy.sh && ./deploy.sh"
    cmd = build_ssh_cmd(config, remote_script)
    if stream:
        res = subprocess.run(cmd, check=False)
        return res.returncode, ""
    res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
    return res.returncode, res.stdout + ("\n" + res.stderr if res.stderr else "")


def build_dashboard_remote_env(
    *,
    control_plane_url: str,
    username: str,
    password: str,
    base_domain: str | None = None,
    container_name: str = DEFAULT_DASHBOARD_CONTAINER,
    compose_project: str = DEFAULT_DASHBOARD_COMPOSE_PROJECT,
    dashboard_commit: str | None = None,
) -> dict[str, str]:
    """Builds production environment variables written to a VPS Next.js stack .env."""
    env_vars = {
        "NODE_ENV": "production",
        "PORT": "3000",
        "SANDBOX_CONTROL_PLANE_URL": control_plane_url,
        "WEB_UI_USERNAME": username,
        "WEB_UI_PASSWORD": password,
        "DASHBOARD_CONTAINER_NAME": container_name,
        "DASHBOARD_COMPOSE_PROJECT": compose_project,
    }
    if base_domain:
        env_vars["APPS_BASE_DOMAIN"] = base_domain
    if dashboard_commit and dashboard_commit != "unknown":
        env_vars["NEXT_PUBLIC_DASHBOARD_COMMIT"] = dashboard_commit
    return env_vars


def _resolve_dashboard_commit(root: Path, explicit_commit: str | None) -> str | None:
    if explicit_commit and explicit_commit.strip():
        return explicit_commit.strip()
    prov = resolve_host_software_factory_provenance(root)
    short = prov.get("SOFTWARE_FACTORY_COMMIT_SHORT", "").strip()
    if not short or short == "unknown":
        return None
    return f"{short}*" if prov.get("SOFTWARE_FACTORY_DIRTY") == "1" else short


def cleanup_legacy_staging_dashboard(
    vps_config: VpsSshConfig,
    *,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    """Removes any retired sandbox-dashboard-staging container, directory, and Caddy route."""
    ok_route, route_msg = remove_app_caddy_route(vps_config, DEFAULT_LEGACY_STAGING_APP_SLUG)
    if ok_route and "already up to date" not in route_msg.lower() and log_cb:
        log_cb(f"   ✓ Removed legacy staging Caddy route ({DEFAULT_LEGACY_STAGING_APP_SLUG}.caddy)")

    cleanup_script = (
        f"if [ -d {shlex.quote(DEFAULT_LEGACY_STAGING_REMOTE_DIR)} ] || "
        f"docker inspect {shlex.quote(DEFAULT_LEGACY_STAGING_CONTAINER)} >/dev/null 2>&1; then "
        f"if [ -f {shlex.quote(DEFAULT_LEGACY_STAGING_REMOTE_DIR + '/docker-compose.prod.yml')} ]; then "
        f"docker compose -p {shlex.quote(DEFAULT_LEGACY_STAGING_COMPOSE_PROJECT)} "
        f"-f {shlex.quote(DEFAULT_LEGACY_STAGING_REMOTE_DIR + '/docker-compose.prod.yml')} down --remove-orphans >/dev/null 2>&1 || true; "
        "fi; "
        f"docker rm -f {shlex.quote(DEFAULT_LEGACY_STAGING_CONTAINER)} >/dev/null 2>&1 || true; "
        f"rm -rf {shlex.quote(DEFAULT_LEGACY_STAGING_REMOTE_DIR)}; "
        "echo REMOVED_STAGING; "
        "fi"
    )
    res = subprocess.run(
        build_ssh_cmd(vps_config, cleanup_script),
        timeout=60,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and "REMOVED_STAGING" in res.stdout and log_cb:
        log_cb(f"   ✓ Removed legacy staging stack ({DEFAULT_LEGACY_STAGING_REMOTE_DIR})")


def _deploy_vps_nextjs_stack(
    vps_config: VpsSshConfig,
    target: VpsWebStackTarget,
    *,
    sync_fn: Callable[[VpsSshConfig, Path], bool],
    find_source_fn: Callable[[Path | None], Path],
    wire_caddy_fn: Callable[[VpsSshConfig, str, str, str, dict[str, str], Path], tuple[bool, str]],
    factory_root: Path | None = None,
    dotenv: dict[str, str] | None = None,
    control_plane_url: str | None = None,
    dashboard_commit: str | None = None,
    stream: bool = True,
    log_cb: Callable[[str], None] | None = None,
) -> int:
    """Shared orchestration for syncing, building, wiring Caddy, and cleaning up legacy staging."""
    def _emit(msg: str, *, err: bool = False) -> None:
        if log_cb:
            log_cb(msg)
        print(msg, file=sys.stderr if err else sys.stdout)

    target_cfg = VpsSshConfig(
        host=vps_config.host,
        user=vps_config.user,
        port=vps_config.port,
        key_path=vps_config.key_path,
        remote_dir=target.remote_dir,
    )
    root = factory_root or resolve_factory_root()
    env_map = dotenv if dotenv is not None else (parse_env_file(root / ".env") if (root / ".env").is_file() else {})

    try:
        resolved_base = resolve_apps_base_domain(None, dotenv=env_map)
        upstream, lookup_err = resolve_dashboard_upstream(
            control_plane_url, base_domain=resolved_base, dotenv=env_map, repo_root=root,
        )
        if not upstream:
            raise ValueError(lookup_err or "Could not resolve Modal Control Plane URL.")
        creds = resolve_web_ui_credentials(repo_root=root, env=env_map or None, enforce=True)
        resolved_cf = resolve_cloudflare_dns_token(None, dotenv=env_map)
    except (ValueError, RuntimeError) as exc:
        _emit(f"❌ {exc}", err=True)
        return 1

    _emit(f"🚀 Deploying {target.label} to {target_cfg.user}@{target_cfg.host}:{target_cfg.remote_dir}")
    if not check_ssh_connection(target_cfg):
        _emit(f"❌ Cannot connect via SSH to {target_cfg.user}@{target_cfg.host}:{target_cfg.port}.", err=True)
        return 1
    docker_ok, docker_msg = check_remote_docker(target_cfg)
    if not docker_ok:
        _emit(f"❌ {docker_msg}", err=True)
        return 1

    source_dir = find_source_fn(root)
    if not sync_fn(target_cfg, source_dir):
        return 1

    commit_label = _resolve_dashboard_commit(root, dashboard_commit)
    remote_env = build_dashboard_remote_env(
        control_plane_url=upstream,
        username=creds["WEB_UI_USERNAME"],
        password=creds["WEB_UI_PASSWORD"],
        base_domain=resolved_base,
        container_name=target.container_name,
        compose_project=target.compose_project,
        dashboard_commit=commit_label,
    )
    ok_env, msg_env = _write_remote_b64(
        target_cfg, f"{target_cfg.remote_dir}/.env", serialize_dotenv(remote_env), mode="0600",
    )
    if not ok_env:
        _emit(f"❌ {msg_env}", err=True)
        return 1

    code, out = execute_remote_dashboard_deploy(target_cfg, stream=stream)
    if code != 0:
        _emit(f"❌ Remote {target.label} build/start failed (exit {code}).", err=True)
        if out:
            _emit(out, err=True)
        return code

    ok_route, route_msg = wire_caddy_fn(
        target_cfg, resolved_base, upstream, resolved_cf, env_map, root,
    )
    if not ok_route:
        _emit(f"❌ {route_msg}", err=True)
        return 1
    _emit(f"   ✓ {route_msg}")

    cleanup_legacy_staging_dashboard(target_cfg, log_cb=lambda msg: _emit(msg))
    _emit(f"✅ {target.label} deployment complete!")
    return 0


def deploy_dashboard(
    vps_config: VpsSshConfig,
    *,
    factory_root: Path | None = None,
    dotenv: dict[str, str] | None = None,
    control_plane_url: str | None = None,
    dashboard_commit: str | None = None,
    stream: bool = True,
    log_cb: Callable[[str], None] | None = None,
) -> int:
    """Deploys dashboard/ to /opt/sandbox-dashboard and wires apex App Base Domain Caddy routing."""
    def _wire_apex(
        target_cfg: VpsSshConfig,
        resolved_base: str,
        upstream: str,
        resolved_cf: str,
        env_map: dict[str, str],
        root: Path,
    ) -> tuple[bool, str]:
        ok, msg = setup_reverse_proxy(
            vps_config=target_cfg,
            wildcard=True,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
            dashboard=True,
            dashboard_upstream=upstream,
            dashboard_web_upstream=DASHBOARD_TARGET.upstream,
            dotenv=env_map,
            env_file_path=root / ".env",
        )
        return (ok, msg if ok else f"Apex routing failed: {msg}")

    return _deploy_vps_nextjs_stack(
        vps_config,
        DASHBOARD_TARGET,
        sync_fn=sync_dashboard_to_vps,
        find_source_fn=find_dashboard_source_dir,
        wire_caddy_fn=_wire_apex,
        factory_root=factory_root,
        dotenv=dotenv,
        control_plane_url=control_plane_url,
        dashboard_commit=dashboard_commit,
        stream=stream,
        log_cb=log_cb,
    )


def deploy_deployer(
    vps_config: VpsSshConfig,
    *,
    factory_root: Path | None = None,
    dotenv: dict[str, str] | None = None,
    control_plane_url: str | None = None,
    dashboard_commit: str | None = None,
    stream: bool = True,
    log_cb: Callable[[str], None] | None = None,
) -> int:
    """Deploys dashboard-deployer/ to /opt/dashboard-deployer and wires deploy.<APPS_BASE_DOMAIN>."""
    def _wire_deployer(
        target_cfg: VpsSshConfig,
        resolved_base: str,
        upstream: str,
        resolved_cf: str,
        _env_map: dict[str, str],
        _root: Path,
    ) -> tuple[bool, str]:
        fqdn = f"{DEFAULT_DEPLOYER_SUBDOMAIN}.{resolved_base}"
        ok, msg = ensure_app_caddy_route(
            target_cfg,
            DEFAULT_DEPLOYER_APP_SLUG,
            fqdn,
            DEPLOYER_TARGET.upstream,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
            dashboard_upstream=upstream,
            apex_cli_only=True,
        )
        return (ok, f"Dashboard Deployer live at https://{fqdn} ({msg})" if ok else msg)

    return _deploy_vps_nextjs_stack(
        vps_config,
        DEPLOYER_TARGET,
        sync_fn=sync_deployer_to_vps,
        find_source_fn=find_deployer_source_dir,
        wire_caddy_fn=_wire_deployer,
        factory_root=factory_root,
        dotenv=dotenv,
        control_plane_url=control_plane_url,
        dashboard_commit=dashboard_commit,
        stream=stream,
        log_cb=log_cb,
    )


def build_dashboard_deploy_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for modal-sandbox infra dashboard."""
    return argparse.ArgumentParser(
        prog="modal-sandbox infra dashboard",
        description="Build and deploy the Sandbox Web Dashboard to the App Base Domain.",
    )


def build_deployer_deploy_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for modal-sandbox infra deployer."""
    return argparse.ArgumentParser(
        prog="modal-sandbox infra deployer",
        description="Build and deploy the standalone Dashboard Deployer to deploy.<APPS_BASE_DOMAIN>.",
    )


def _run_stack_cli(
    parser: argparse.ArgumentParser,
    target: VpsWebStackTarget,
    runner: Callable[..., int],
    argv: list[str] | None = None,
) -> int:
    parser.parse_args(argv)
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    try:
        vps_cfg = resolve_vps_ssh_config(remote_dir=target.remote_dir, dotenv=dotenv)
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    return runner(vps_cfg, factory_root=root, dotenv=dotenv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deploying the Sandbox Web Dashboard to the VPS."""
    return _run_stack_cli(build_dashboard_deploy_parser(), DASHBOARD_TARGET, deploy_dashboard, argv)


def deployer_main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deploying the Dashboard Deployer to the VPS."""
    return _run_stack_cli(build_deployer_deploy_parser(), DEPLOYER_TARGET, deploy_deployer, argv)


if __name__ == "__main__":
    sys.exit(main())
