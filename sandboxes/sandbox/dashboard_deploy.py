"""Remote deployment and Caddy cutover orchestration for the Next.js Sandbox Dashboard."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

from sandbox.app_deploy._caddy import ensure_app_caddy_route
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
DEFAULT_STAGING_REMOTE_DIR = "/opt/sandbox-dashboard-staging"
DEFAULT_DASHBOARD_APP_SLUG = "sandbox-dashboard"
DEFAULT_STAGING_SUBDOMAIN = "dashboard"
DEFAULT_STAGING_WEB_UPSTREAM = "sandbox-dashboard-staging-web:3000"


@dataclass(frozen=True)
class DashboardDeployTarget:
    """Isolated VPS deployment target metadata for apex vs staging dashboard."""

    kind: str
    remote_dir: str
    container_name: str
    compose_project: str
    upstream: str


DASHBOARD_TARGETS: dict[str, DashboardDeployTarget] = {
    "apex": DashboardDeployTarget(
        kind="apex",
        remote_dir=DEFAULT_DASHBOARD_REMOTE_DIR,
        container_name="sandbox-dashboard-web",
        compose_project="sandbox-dashboard",
        upstream=DEFAULT_DASHBOARD_WEB_UPSTREAM,
    ),
    "subdomain": DashboardDeployTarget(
        kind="subdomain",
        remote_dir=DEFAULT_STAGING_REMOTE_DIR,
        container_name="sandbox-dashboard-staging-web",
        compose_project="sandbox-dashboard-staging",
        upstream=DEFAULT_STAGING_WEB_UPSTREAM,
    ),
}


def resolve_dashboard_target(*, subdomain: bool = False) -> DashboardDeployTarget:
    """Returns the isolated VPS target metadata for apex or staging subdomain deployment."""
    return DASHBOARD_TARGETS["subdomain" if subdomain else "apex"]


def find_dashboard_source_dir(start_path: Path | None = None) -> Path:
    """Discovers the local dashboard directory containing deploy.sh and docker-compose.prod.yml."""
    current = (start_path or Path(__file__)).resolve()
    candidates = [
        resolve_factory_root() / "dashboard",
        current.parent.parent / "dashboard",
        current.parent.parent.parent / "dashboard",
        Path.cwd() / "dashboard",
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "deploy.sh").is_file() and (cand / "docker-compose.prod.yml").is_file():
            return cand
    raise FileNotFoundError(
        "Could not locate local 'dashboard' directory containing deploy.sh and docker-compose.prod.yml."
    )


def sync_dashboard_to_vps(
    config: VpsSshConfig,
    source_dir: Path | None = None,
    timeout: int = 180,
) -> bool:
    """Synchronizes the local dashboard workspace to the VPS via tar over SSH."""
    src = source_dir or find_dashboard_source_dir()
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
        str(src.parent),
        src.name,
    ]
    remote_extract = f"mkdir -p '{config.remote_dir}' && tar -xzf - -C '{config.remote_dir}' --strip-components=1"
    ssh_cmd = build_ssh_cmd(config, remote_extract)
    try:
        stream_source_archive(tar_cmd, ssh_cmd, timeout=timeout)
        return True
    except (RuntimeError, OSError) as exc:
        print(f"❌ Dashboard sync to VPS failed: {exc}", file=sys.stderr)
        return False


def execute_remote_dashboard_deploy(
    config: VpsSshConfig,
    *,
    stream: bool = True,
    timeout: int = 600,
) -> tuple[int, str]:
    """Executes ./deploy.sh inside the remote dashboard directory."""
    remote_script = f"cd '{config.remote_dir}' && chmod +x deploy.sh && ./deploy.sh"
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
    container_name: str = "sandbox-dashboard-web",
    compose_project: str = "sandbox-dashboard",
    dashboard_commit: str | None = None,
) -> dict[str, str]:
    """Builds production environment variables written to the VPS dashboard .env."""
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


def deploy_dashboard(
    vps_config: VpsSshConfig,
    *,
    factory_root: Path | None = None,
    dotenv: dict[str, str] | None = None,
    control_plane_url: str | None = None,
    subdomain: bool = False,
    dashboard_commit: str | None = None,
    stream: bool = True,
    log_cb=None,
) -> int:
    """Deploys dashboard/ to its isolated VPS stack and wires apex or dashboard.<base> Caddy route."""
    def _emit(msg: str, *, err: bool = False) -> None:
        if log_cb:
            log_cb(msg)
        print(msg, file=sys.stderr if err else sys.stdout)

    target = resolve_dashboard_target(subdomain=subdomain)
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

    _emit(f"🚀 Deploying Sandbox Web Dashboard ({target.kind}) to {target_cfg.user}@{target_cfg.host}:{target_cfg.remote_dir}")
    if not check_ssh_connection(target_cfg):
        _emit(f"❌ Cannot connect via SSH to {target_cfg.user}@{target_cfg.host}:{target_cfg.port}.", err=True)
        return 1
    docker_ok, docker_msg = check_remote_docker(target_cfg)
    if not docker_ok:
        _emit(f"❌ {docker_msg}", err=True)
        return 1

    source_dir = find_dashboard_source_dir(root)
    if not sync_dashboard_to_vps(target_cfg, source_dir=source_dir):
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
        _emit(f"❌ Remote dashboard build/start failed (exit {code}).", err=True)
        if out:
            _emit(out, err=True)
        return code

    if subdomain:
        fqdn = f"{DEFAULT_STAGING_SUBDOMAIN}.{resolved_base}"
        ok_route, route_msg = ensure_app_caddy_route(
            target_cfg,
            DEFAULT_DASHBOARD_APP_SLUG,
            fqdn,
            target.upstream,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
            dashboard_upstream=upstream,
            apex_cli_only=True,
        )
        if not ok_route:
            _emit(f"❌ {route_msg}", err=True)
            return 1
        _emit(f"   ✓ Staged at https://{fqdn} ({route_msg})")
    else:
        ok_apex, apex_msg = setup_reverse_proxy(
            vps_config=target_cfg,
            wildcard=True,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
            dashboard=True,
            dashboard_upstream=upstream,
            dashboard_web_upstream=target.upstream,
            dotenv=env_map,
            env_file_path=root / ".env",
        )
        if not ok_apex:
            _emit(f"❌ Apex routing failed: {apex_msg}", err=True)
            return 1
        _emit(f"   ✓ {apex_msg}")

    _emit("✅ Sandbox Web Dashboard deployment complete!")
    return 0


def build_dashboard_deploy_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for modal-sandbox infra dashboard."""
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra dashboard",
        description="Build and deploy the Sandbox Web Dashboard to the App Base Domain or staging subdomain.",
    )
    parser.add_argument(
        "--subdomain",
        action="store_true",
        help="Deploy isolated staging stack to dashboard.<APPS_BASE_DOMAIN> without affecting the apex.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deploying the Sandbox Web Dashboard to the VPS."""
    args = build_dashboard_deploy_parser().parse_args(argv)
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    target = resolve_dashboard_target(subdomain=args.subdomain)

    try:
        vps_cfg = resolve_vps_ssh_config(remote_dir=target.remote_dir, dotenv=dotenv)
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    return deploy_dashboard(
        vps_cfg,
        factory_root=root,
        dotenv=dotenv,
        subdomain=args.subdomain,
    )


if __name__ == "__main__":
    sys.exit(main())
