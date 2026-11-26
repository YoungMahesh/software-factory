"""Remote deployment and Caddy cutover orchestration for the Next.js Sandbox Dashboard."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from sandbox.app_deploy._caddy import ensure_app_caddy_route, remove_app_caddy_route
from sandbox.app_deploy._config import serialize_dotenv
from sandbox.caddy_deploy import setup_reverse_proxy
from sandbox.caddy_wildcard import (
    DEFAULT_DASHBOARD_WEB_UPSTREAM,
    _write_remote_b64,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    resolve_dashboard_upstream,
    validate_subdomain_label,
)
from sandbox.config import parse_env_file, resolve_factory_root, resolve_web_ui_credentials
from sandbox.infra_deploy import (
    VpsSshConfig,
    build_ssh_cmd,
    check_remote_docker,
    check_ssh_connection,
    resolve_vps_ssh_config,
)
from sandbox.source_transfer import stream_source_archive

DEFAULT_DASHBOARD_REMOTE_DIR = "/opt/sandbox-dashboard"
DEFAULT_DASHBOARD_APP_SLUG = "sandbox-dashboard"


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
) -> dict[str, str]:
    """Builds production environment variables written to /opt/sandbox-dashboard/.env."""
    env_vars = {
        "NODE_ENV": "production",
        "PORT": "3000",
        "SANDBOX_CONTROL_PLANE_URL": control_plane_url,
        "WEB_UI_USERNAME": username,
        "WEB_UI_PASSWORD": password,
    }
    if base_domain:
        env_vars["APPS_BASE_DOMAIN"] = base_domain
    return env_vars


def deploy_dashboard(
    vps_config: VpsSshConfig,
    *,
    factory_root: Path | None = None,
    dotenv: dict[str, str] | None = None,
    control_plane_url: str | None = None,
    base_domain: str | None = None,
    cf_dns_token: str | None = None,
    subdomain: str | None = None,
    cutover: bool = False,
    sync_caddy_store: bool = False,
    profile: str | None = None,
    stream: bool = True,
) -> int:
    """Deploys dashboard/ to VPS, builds container, and optionally wires staging or apex Caddy routes."""
    if subdomain and cutover:
        print("❌ Cannot combine --subdomain and --cutover in one step; stage first, then cut over.", file=sys.stderr)
        return 1

    root = factory_root or resolve_factory_root()
    env_map = dotenv if dotenv is not None else (parse_env_file(root / ".env") if (root / ".env").is_file() else {})

    try:
        resolved_base = resolve_apps_base_domain(base_domain, dotenv=env_map)
        upstream, lookup_err = resolve_dashboard_upstream(
            control_plane_url, base_domain=resolved_base, dotenv=env_map, repo_root=root,
        )
        if not upstream:
            raise ValueError(lookup_err or "Could not resolve Modal Control Plane URL.")
        creds = resolve_web_ui_credentials(repo_root=root, enforce=True)
        clean_sub = validate_subdomain_label(subdomain) if subdomain else None
        resolved_cf = (
            resolve_cloudflare_dns_token(cf_dns_token, dotenv=env_map)
            if (clean_sub or cutover)
            else None
        )
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(f"\n🚀 Deploying Sandbox Dashboard to {vps_config.user}@{vps_config.host}:{vps_config.remote_dir}")
    if not check_ssh_connection(vps_config):
        print(f"❌ Cannot connect via SSH to {vps_config.user}@{vps_config.host}:{vps_config.port}.", file=sys.stderr)
        return 1
    docker_ok, docker_msg = check_remote_docker(vps_config)
    if not docker_ok:
        print(f"❌ {docker_msg}", file=sys.stderr)
        return 1

    if not sync_dashboard_to_vps(vps_config):
        return 1

    remote_env = build_dashboard_remote_env(
        control_plane_url=upstream,
        username=creds["WEB_UI_USERNAME"],
        password=creds["WEB_UI_PASSWORD"],
        base_domain=resolved_base,
    )
    ok_env, msg_env = _write_remote_b64(
        vps_config, f"{vps_config.remote_dir}/.env", serialize_dotenv(remote_env), mode="0600",
    )
    if not ok_env:
        print(f"❌ {msg_env}", file=sys.stderr)
        return 1

    code, out = execute_remote_dashboard_deploy(vps_config, stream=stream)
    if code != 0:
        print(f"❌ Remote dashboard build/start failed (exit {code}).", file=sys.stderr)
        if out:
            print(out, file=sys.stderr)
        return code

    if clean_sub:
        fqdn = f"{clean_sub}.{resolved_base}"
        ok_route, route_msg = ensure_app_caddy_route(
            vps_config,
            DEFAULT_DASHBOARD_APP_SLUG,
            fqdn,
            DEFAULT_DASHBOARD_WEB_UPSTREAM,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
        )
        if not ok_route:
            print(f"❌ {route_msg}", file=sys.stderr)
            return 1
        print(f"   ✓ Staged at https://{fqdn} ({route_msg})")

    if cutover:
        ok_apex, apex_msg = setup_reverse_proxy(
            vps_config=vps_config,
            wildcard=True,
            base_domain=resolved_base,
            cf_dns_token=resolved_cf,
            dashboard=True,
            dashboard_upstream=upstream,
            dashboard_web_upstream=DEFAULT_DASHBOARD_WEB_UPSTREAM,
            dotenv=env_map,
            env_file_path=root / ".env",
        )
        if not ok_apex:
            print(f"❌ Apex cutover failed: {apex_msg}", file=sys.stderr)
            return 1
        print(f"   ✓ {apex_msg}")
        remove_app_caddy_route(vps_config, DEFAULT_DASHBOARD_APP_SLUG)

    if sync_caddy_store and (clean_sub or cutover):
        from sandbox.caddy_store import maybe_sync_after_deploy
        return maybe_sync_after_deploy(vps_config, profile)

    print("\n✅ Sandbox Dashboard deployment complete!")
    return 0


def build_dashboard_deploy_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for modal-sandbox infra dashboard."""
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra dashboard",
        description="Deploy the Next.js Sandbox Dashboard container to /opt/sandbox-dashboard on the VPS.",
    )
    parser.add_argument("--control-plane-url", default=None, help="Direct Modal Control Plane origin (*.modal.run).")
    parser.add_argument("--subdomain", default=None, help="Expose staging preview at <subdomain>.<APPS_BASE_DOMAIN>.")
    parser.add_argument("--cutover", action="store_true", help="Switch apex APPS_BASE_DOMAIN to Next.js while preserving Modal CLI paths.")
    parser.add_argument("--base-domain", default=None, help="Override APPS_BASE_DOMAIN.")
    parser.add_argument("--cf-dns-token", default=None, help="Cloudflare DNS-01 token when updating Caddy wildcard ingress.")
    parser.add_argument("--remote-dir", default=DEFAULT_DASHBOARD_REMOTE_DIR, help=f"Remote VPS directory (default: {DEFAULT_DASHBOARD_REMOTE_DIR}).")
    parser.add_argument("--sync", action="store_true", help="Back up /opt/caddy to Central Config Store after route changes.")
    parser.add_argument("--profile", default=None, help="Caddy config profile folder under caddy/ in config repo.")
    parser.add_argument("--host", default=None, help="VPS SSH host (defaults to RESOURCE_PLANE_SSH_HOST).")
    parser.add_argument("--user", default=None, help="VPS SSH user (defaults to RESOURCE_PLANE_SSH_USER or 'root').")
    parser.add_argument("--port", type=int, default=None, help="VPS SSH port (defaults to RESOURCE_PLANE_SSH_PORT or 22).")
    parser.add_argument("--key", default=None, help="Path to private SSH key (defaults to RESOURCE_PLANE_SSH_KEY).")
    parser.add_argument("--check-only", action="store_true", help="Only verify SSH and remote Docker connectivity.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deploying the Sandbox Dashboard to the VPS."""
    args = build_dashboard_deploy_parser().parse_args(argv)
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}

    try:
        vps_cfg = resolve_vps_ssh_config(
            host=args.host,
            user=args.user,
            port=args.port,
            key_path=args.key,
            remote_dir=args.remote_dir,
            dotenv=dotenv,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        if not check_ssh_connection(vps_cfg):
            print("❌ SSH connection failed.", file=sys.stderr)
            return 1
        ok, msg = check_remote_docker(vps_cfg)
        print("✓ " if ok else "❌ ", msg)
        return 0 if ok else 1

    return deploy_dashboard(
        vps_cfg,
        factory_root=root,
        dotenv=dotenv,
        control_plane_url=args.control_plane_url,
        base_domain=args.base_domain,
        cf_dns_token=args.cf_dns_token,
        subdomain=args.subdomain,
        cutover=args.cutover,
        sync_caddy_store=args.sync,
        profile=args.profile,
    )


if __name__ == "__main__":
    sys.exit(main())
