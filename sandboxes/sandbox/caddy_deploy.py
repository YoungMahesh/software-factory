"""Reverse-proxy automation module for Host Ingress Proxy (/opt/caddy) on Linux VPS.

Automates fresh-host /opt/caddy bootstrapping, wildcard DNS-01 TLS setup,
Caddy status probing, Docker network attachment, idempotent modular site routing,
config validation, and zero-downtime Caddy reloads.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from sandbox.caddy_wildcard import (
    DEFAULT_CADDY_CONTAINER,
    DEFAULT_CADDY_DIR,
    DEFAULT_CADDY_NETWORK,
    DEFAULT_S3_UPSTREAM,
    DEFAULT_WEB_UPSTREAM,
    SITES_IMPORT_PATTERN,
    caddyfile_imports_sites,
    ensure_wildcard_caddy,
    format_caddy_route,
    is_subdomain_of,
    normalize_base_domain,
    parse_caddyfile_domains,
    render_base_caddyfile,
    render_resource_plane_site,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    resolve_wildcard_dashboard_upstream,
)
from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.host_ingress import apply_configuration, prepare_runtime
from sandbox.infra_deploy import (
    VpsSshConfig,
    build_ssh_cmd,
    find_resource_plane_source_dir,
    resolve_vps_ssh_config,
    sync_env_keys,
)

DEFAULT_CADDYFILE_PATH = "/opt/caddy/conf/Caddyfile"
DEFAULT_CADDY_SITES_DIR = "/opt/caddy/conf/sites"
DEFAULT_RESOURCE_PLANE_SITE_PATH = "/opt/caddy/conf/sites/resource-plane.caddy"


@dataclass
class CaddyConfig:
    """Configuration for the canonical Host Ingress Proxy (/opt/caddy)."""

    caddy_dir: str = DEFAULT_CADDY_DIR
    caddyfile_path: str = DEFAULT_CADDYFILE_PATH
    sites_dir: str = DEFAULT_CADDY_SITES_DIR
    site_path: str = DEFAULT_RESOURCE_PLANE_SITE_PATH
    container_name: str = DEFAULT_CADDY_CONTAINER
    network: str = DEFAULT_CADDY_NETWORK


def find_caddy_source_dir(start_path: Path | None = None) -> Path:
    """Locates local resource-plane/caddy stack definition directory."""
    caddy_dir = find_resource_plane_source_dir(start_path) / "caddy"
    if (
        caddy_dir.is_dir()
        and (caddy_dir / "docker-compose.yml").is_file()
        and (caddy_dir / "conf" / "Caddyfile").is_file()
    ):
        return caddy_dir
    raise FileNotFoundError(
        "Could not locate local 'resource-plane/caddy' directory containing "
        "docker-compose.yml and conf/Caddyfile."
    )


def _run_ssh(vps_config: VpsSshConfig, remote_cmd: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Executes a remote command over SSH and captures text output."""
    return subprocess.run(build_ssh_cmd(vps_config, remote_cmd), timeout=timeout, capture_output=True, text=True, check=False)


def _ssh_exec(vps_config: VpsSshConfig, remote_cmd: str, timeout: int, error_prefix: str) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    """Runs SSH command and converts timeout/OS errors into status tuples."""
    try:
        return _run_ssh(vps_config, remote_cmd, timeout=timeout), ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"{error_prefix}: {exc}"


def check_caddy_running(vps_config: VpsSshConfig, caddy_config: CaddyConfig | None = None, timeout: int = 15) -> tuple[bool, str]:
    """Verifies that the Caddy reverse-proxy container is active on remote VPS."""
    cfg = caddy_config or CaddyConfig()
    script = f"if docker inspect -f '{{{{.State.Running}}}}' {cfg.container_name} 2>/dev/null | grep -q 'true'; then echo running; else echo not_running; fi"
    res, err = _ssh_exec(vps_config, script, timeout, "Failed to probe Caddy status on VPS")
    if res is None:
        return False, err
    if res.returncode == 0 and res.stdout.strip() == "running":
        return True, f"Caddy container '{cfg.container_name}' is running."
    return False, f"Caddy container '{cfg.container_name}' is not running or missing."


def check_ports_available(vps_config: VpsSshConfig, timeout: int = 15) -> tuple[bool, str]:
    """Verifies that host ports 80 and 443 are free before bootstrapping Caddy."""
    probe_script = (
        "busy=\"\"; "
        "if command -v ss >/dev/null 2>&1; then busy=$(ss -H -lnt '( sport = :80 or sport = :443 )' 2>/dev/null || true); "
        "elif command -v lsof >/dev/null 2>&1; then busy=$(lsof -iTCP:80 -iTCP:443 -sTCP:LISTEN -Pn 2>/dev/null || true); fi; "
        "if [ -z \"$busy\" ]; then busy=$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E ':(80|443)->' || true); fi; "
        "if [ -n \"$busy\" ]; then echo \"BUSY:$busy\"; else echo FREE; fi"
    )
    res, err = _ssh_exec(vps_config, probe_script, timeout, "Port availability check failed")
    if res is None:
        return False, err
    out = res.stdout.strip()
    if res.returncode == 0 and out == "FREE":
        return True, "Ports 80 and 443 are available."
    if out.startswith("BUSY:"):
        return False, f"Ports 80/443 are already in use on remote VPS: {out.removeprefix('BUSY:').strip()}"
    return False, f"Failed to verify ports 80/443 availability: {res.stderr.strip() or out}"


def ensure_docker_network(vps_config: VpsSshConfig, network: str = DEFAULT_CADDY_NETWORK, timeout: int = 20) -> tuple[bool, str]:
    """Ensures the shared Docker bridge network exists on the remote VPS."""
    net_script = (
        f"if ! docker network inspect '{network}' >/dev/null 2>&1; then docker network create '{network}' >/dev/null; fi && "
        f"docker network inspect '{network}' >/dev/null 2>&1 && echo ok"
    )
    res, err = _ssh_exec(vps_config, net_script, timeout, "Docker network setup failed")
    if res is None:
        return False, err
    if res.returncode == 0 and "ok" in res.stdout:
        return True, f"Docker network '{network}' is ready."
    return False, f"Failed to create/verify Docker network '{network}': {res.stderr.strip()}"


def ensure_caddy_network(vps_config: VpsSshConfig, caddy_config: CaddyConfig | None = None, timeout: int = 20) -> tuple[bool, str]:
    """Ensures the Caddy container is connected to the target Docker network."""
    cfg = caddy_config or CaddyConfig()
    net_ok, net_msg = ensure_docker_network(vps_config, cfg.network, timeout=timeout)
    if not net_ok:
        return False, net_msg

    network_script = (
        f"if ! docker inspect {cfg.container_name} --format '{{{{json .NetworkSettings.Networks}}}}' 2>/dev/null "
        f"| grep -q '\"{cfg.network}\"'; then docker network connect {cfg.network} {cfg.container_name} >/dev/null 2>&1 || true; fi; "
        f"if docker inspect {cfg.container_name} --format '{{{{json .NetworkSettings.Networks}}}}' 2>/dev/null "
        f"| grep -q '\"{cfg.network}\"'; then echo connected; else echo disconnected; fi"
    )
    res, err = _ssh_exec(vps_config, network_script, timeout, "Network attachment probe failed")
    if res is None:
        return False, err
    if res.returncode == 0 and "connected" in res.stdout:
        return True, f"Caddy is connected to network '{cfg.network}'."
    return False, f"Failed to attach Caddy to network '{cfg.network}'."


def bootstrap_caddy(
    vps_config: VpsSshConfig,
    email: str | None = None,
    caddy_config: CaddyConfig | None = None,
    source_dir: Path | None = None,
    timeout: int = 360,
) -> tuple[bool, str]:
    """Prepares the complete canonical build context and starts or upgrades Caddy."""
    cfg = caddy_config or CaddyConfig()
    result = prepare_runtime(
        vps_config, source_dir=source_dir, bootstrap=True, email=email,
        caddy_dir=cfg.caddy_dir, container_name=cfg.container_name,
        network=cfg.network, timeout=timeout,
    )
    return result.success, result.message


def validate_caddy(vps_config: VpsSshConfig, caddy_config: CaddyConfig | None = None, timeout: int = 30) -> tuple[bool, str]:
    """Validates remote Caddy configuration before reload."""
    cfg = caddy_config or CaddyConfig()
    res, err = _ssh_exec(vps_config, f"docker exec {cfg.container_name} caddy validate --config /etc/caddy/Caddyfile", timeout, "Caddy validation timed out or failed")
    if res is None:
        return False, err
    if res.returncode == 0:
        return True, "Caddy configuration validated."
    return False, f"Caddy validation failed: {res.stderr.strip() or res.stdout.strip()}"


def ensure_caddy_site_config(
    vps_config: VpsSshConfig,
    domain: str,
    upstream: str = DEFAULT_WEB_UPSTREAM,
    s3_domain: str | None = None,
    s3_upstream: str = DEFAULT_S3_UPSTREAM,
    caddy_config: CaddyConfig | None = None,
    timeout: int = 90,
) -> tuple[bool, bool, str]:
    """Applies and activates the Resource Plane route, recovering on failure."""
    cfg = caddy_config or CaddyConfig()
    relative_path = Path(cfg.site_path).relative_to(cfg.caddy_dir).as_posix()
    result = apply_configuration(
        vps_config,
        {relative_path: render_resource_plane_site(domain, upstream, s3_domain, s3_upstream)},
        require_sites_import=True, caddy_dir=cfg.caddy_dir,
        container_name=cfg.container_name, network=cfg.network, timeout=timeout,
    )
    return result.success, result.changed, result.message


def reload_caddy(vps_config: VpsSshConfig, caddy_config: CaddyConfig | None = None, timeout: int = 30) -> tuple[bool, str]:
    """Validates and reloads remote Caddy configuration with zero downtime."""
    cfg = caddy_config or CaddyConfig()
    val_ok, val_msg = validate_caddy(vps_config, cfg, timeout=timeout)
    if not val_ok:
        return False, val_msg
    res, err = _ssh_exec(vps_config, f"docker exec -w /etc/caddy {cfg.container_name} caddy reload >/dev/null 2>&1", timeout, "Caddy reload command timed out or failed")
    if res is None:
        return False, err
    if res.returncode == 0:
        return True, f"Successfully reloaded Caddy configuration on container '{cfg.container_name}'."
    return False, f"Caddy reload failed (code {res.returncode}): {res.stderr.strip()}"


def setup_reverse_proxy(
    vps_config: VpsSshConfig, domain: str | None = None, upstream: str = DEFAULT_WEB_UPSTREAM,
    s3_domain: str | None = None, s3_upstream: str = DEFAULT_S3_UPSTREAM,
    bootstrap: bool = False, email: str | None = None, caddy_config: CaddyConfig | None = None,
    *, base_domain: str | None = None, cf_dns_token: str | None = None, wildcard: bool = False,
    dashboard: bool = False, dashboard_upstream: str | None = None, dashboard_web_upstream: str | None = None,
    no_dashboard: bool = False, apex_cli_only: bool = False,
    dotenv: dict[str, str] | None = None, env_file_path: Path | None = None,
) -> tuple[bool, str]:
    """High-level orchestration: optionally bootstraps /opt/caddy, sets up wildcard TLS, writes site config, and reloads."""
    cfg = caddy_config or CaddyConfig()
    wc_msg, active_base = "", None
    wants_wc = bool(
        wildcard or dashboard or no_dashboard
        or (dashboard_upstream and dashboard_upstream.strip())
        or (dashboard_web_upstream and dashboard_web_upstream.strip())
        or (base_domain and base_domain.strip())
    )
    if wants_wc:
        if no_dashboard and (dashboard or (dashboard_upstream and dashboard_upstream.strip()) or (dashboard_web_upstream and dashboard_web_upstream.strip())):
            return False, "Cannot combine --no-dashboard with --dashboard, --dashboard-upstream, or --dashboard-web-upstream."
        active_base = resolve_apps_base_domain(base_domain, dotenv=dotenv)
        resolved_cf = resolve_cloudflare_dns_token(cf_dns_token, dotenv=dotenv)
        dash_ok, effective_dash, dash_note = resolve_wildcard_dashboard_upstream(
            active_base, explicit_upstream=dashboard_upstream,
            require_dashboard=dashboard, no_dashboard=no_dashboard,
            dotenv=dotenv,
        )
        if not dash_ok:
            return False, f"Sandbox Web Dashboard setup failed: {dash_note}"
        wc_ok, wc_msg = ensure_wildcard_caddy(
            vps_config, active_base, resolved_cf, bootstrap=bootstrap, email=email,
            dashboard_upstream=effective_dash, dashboard_web_upstream=dashboard_web_upstream,
            preserve_dashboard=not no_dashboard,
            apex_cli_only=apex_cli_only,
            caddy_dir=cfg.caddy_dir, container_name=cfg.container_name, network=cfg.network,
        )
        if not wc_ok:
            return False, f"Wildcard Caddy setup failed: {wc_msg}"
        if dash_note:
            wc_msg = f"{wc_msg} {dash_note}".strip()
        if effective_dash and env_file_path is not None:
            endpoint_url = f"https://{active_base}"
            synced, _ = sync_env_keys(env_file_path, {"MODAL_SANDBOX_ENDPOINT_URL": endpoint_url})
            if synced:
                wc_msg = f"{wc_msg} Synchronized MODAL_SANDBOX_ENDPOINT_URL={endpoint_url} to {env_file_path.name}.".strip()
            else:
                wc_msg = f"{wc_msg} Preserved existing MODAL_SANDBOX_ENDPOINT_URL in {env_file_path.name}.".strip()
        bootstrap = False
    elif bootstrap:
        boot_ok, boot_msg = bootstrap_caddy(vps_config, email=email, caddy_config=cfg)
        if not boot_ok:
            return False, f"Caddy bootstrap failed: {boot_msg}"
    else:
        ok, msg = check_caddy_running(vps_config, cfg)
        if not ok:
            return False, f"{msg} Re-run with --bootstrap to provision {cfg.caddy_dir}."

    net_ok, net_msg = ensure_caddy_network(vps_config, cfg)
    if not net_ok:
        return False, f"Caddy network attachment failed: {net_msg}"
    if not domain or not domain.strip():
        return True, wc_msg or f"Host Ingress Proxy at {cfg.caddy_dir} is running and attached to '{cfg.network}'."

    clean_domain = domain.strip()
    if active_base and is_subdomain_of(clean_domain, active_base) and not s3_domain:
        from sandbox.app_deploy._caddy import ensure_app_caddy_route
        rp_ok, rp_msg = ensure_app_caddy_route(
            vps_config, "resource-plane", clean_domain, upstream,
            caddy_dir=cfg.caddy_dir, container_name=cfg.container_name, network=cfg.network,
        )
        return (rp_ok, f"{wc_msg} {rp_msg}".strip() if wc_msg else rp_msg)

    site_ok, changed, site_msg = ensure_caddy_site_config(
        vps_config, domain=clean_domain, upstream=upstream,
        s3_domain=s3_domain.strip() if s3_domain else None, s3_upstream=s3_upstream, caddy_config=cfg,
    )
    if not site_ok:
        return False, f"Site configuration failed: {site_msg}"

    s3_msg = f" and S3 route '{s3_domain}'" if s3_domain else ""
    if not changed:
        base_msg = f"Reverse-proxy for '{clean_domain}'{s3_msg} is already up to date (reload skipped)."
        return True, f"{wc_msg} {base_msg}".strip() if wc_msg else base_msg

    done_msg = f"Reverse-proxy successfully configured for '{clean_domain}'{s3_msg}. {site_msg}"
    return True, f"{wc_msg} {done_msg}".strip() if wc_msg else done_msg


def _normalize_site_domain(raw_domain: str) -> str:
    """Normalizes a Caddy site domain, stripping any scheme, port, or path."""
    return normalize_base_domain(raw_domain)


def build_caddy_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for Host Ingress Proxy setup CLI."""
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra caddy",
        description="Configure Host Ingress Proxy (/opt/caddy) for Resource Plane and wildcard ingress.",
    )
    parser.add_argument("--domain", help="Public domain for Resource Plane web console & MCP endpoint.")
    parser.add_argument("--s3-domain", default=None, help="Optional public domain for SeaweedFS S3 API endpoint.")
    parser.add_argument("--bootstrap", action="store_true", help=f"Provision {DEFAULT_CADDY_DIR} via Docker Compose on a fresh VPS.")
    parser.add_argument("--email", default=None, help="Optional ACME email written during --bootstrap.")
    parser.add_argument("--wildcard", action="store_true", help="Provision or upgrade /opt/caddy with Cloudflare DNS-01 wildcard cert for APPS_BASE_DOMAIN.")
    parser.add_argument("--check-only", action="store_true", help="Only verify Caddy status and connectivity without altering configuration.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for Host Ingress Proxy setup and Central Config Store (caddy/) sync."""
    arg_list = list(sys.argv[1:] if argv is None else argv)
    if arg_list and arg_list[0] in ("backup", "restore"):
        from sandbox.caddy_store import run_caddy_store_subcommand
        return run_caddy_store_subcommand(arg_list[0], arg_list[1:])

    args = build_caddy_parser().parse_args(arg_list)
    if args.email and not args.bootstrap:
        print("❌ --email can only be used together with --bootstrap.", file=sys.stderr)
        return 1

    root = resolve_factory_root()
    file_env = parse_env_file(root / ".env") if (root / ".env").exists() else {}
    try:
        vps_config = resolve_vps_ssh_config(dotenv=file_env)
        domain = _normalize_site_domain(args.domain) if args.domain and args.domain.strip() else None
        s3_domain = _normalize_site_domain(args.s3_domain) if args.s3_domain and args.s3_domain.strip() else None
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        return 1

    caddy_cfg = CaddyConfig()
    if args.check_only:
        print(f"🔍 Probing Caddy on VPS {vps_config.user}@{vps_config.host}:{vps_config.port}...")
        ok, msg = check_caddy_running(vps_config, caddy_cfg)
        if not ok:
            print(f"❌ {msg}", file=sys.stderr)
            return 1
        print(f"✓ {msg}")
        net_ok, net_msg = ensure_caddy_network(vps_config, caddy_cfg)
        print(f"✓ {net_msg}" if net_ok else f"⚠ {net_msg}")
        val_ok, val_msg = validate_caddy(vps_config, caddy_cfg)
        print(f"✓ {val_msg}" if val_ok else f"❌ {val_msg}")
        return 0 if (net_ok and val_ok) else 1

    env_base = os.environ.get("APPS_BASE_DOMAIN") or file_env.get("APPS_BASE_DOMAIN")
    env_cf = (
        os.environ.get("CLOUDFLARE_DNS_API_TOKEN") or file_env.get("CLOUDFLARE_DNS_API_TOKEN")
        or os.environ.get("CLOUDFLARE_API_TOKEN") or file_env.get("CLOUDFLARE_API_TOKEN")
    )
    auto_wildcard = bool(args.bootstrap and env_base and env_base.strip() and env_cf and env_cf.strip())
    if not domain and not args.bootstrap and not args.wildcard:
        print("❌ Missing target. Provide --domain, --bootstrap, or --wildcard.", file=sys.stderr)
        return 1

    setup_kwargs: dict[str, object] = {}
    if args.wildcard or auto_wildcard:
        try:
            setup_kwargs = {
                "wildcard": True,
                "base_domain": resolve_apps_base_domain(dotenv=file_env),
                "cf_dns_token": resolve_cloudflare_dns_token(dotenv=file_env),
                "apex_cli_only": True,
                "dotenv": file_env,
                "env_file_path": root / ".env",
            }
        except ValueError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1

    target_desc = f"domain '{domain}'" if domain else ("wildcard" if setup_kwargs else "bootstrap only")
    print(f"🔒 Configuring Host Ingress Proxy (/opt/caddy) on {vps_config.user}@{vps_config.host} ({target_desc})...")
    success, message = setup_reverse_proxy(
        vps_config=vps_config,
        domain=domain,
        s3_domain=s3_domain,
        bootstrap=args.bootstrap,
        email=args.email,
        caddy_config=caddy_cfg,
        **setup_kwargs,
    )
    if not success:
        print(f"❌ {message}", file=sys.stderr)
        return 1
    print(f"✓ {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
