"""Reverse-proxy automation module for Resource Plane using Caddy on Linux VPS.

Automates Caddy status probing, external Docker network attachment,
idempotent Caddyfile routing updates, and zero-downtime Caddy reloads.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd, resolve_vps_ssh_config


DEFAULT_CADDY_DIR = "/root/infra-stack/v1/caddy"
DEFAULT_CADDYFILE_PATH = "/root/infra-stack/v1/caddy/conf/Caddyfile"
DEFAULT_CADDY_CONTAINER = "cCaddy"
DEFAULT_CADDY_NETWORK = "dbhost-network"
DEFAULT_WEB_UPSTREAM = "db-host-web:3000"
DEFAULT_S3_UPSTREAM = "neon-seaweedfs:8333"


@dataclass
class CaddyConfig:
    """Configuration for remote Caddy reverse-proxy service."""
    caddy_dir: str = DEFAULT_CADDY_DIR
    caddyfile_path: str = DEFAULT_CADDYFILE_PATH
    container_name: str = DEFAULT_CADDY_CONTAINER
    network: str = DEFAULT_CADDY_NETWORK


def check_caddy_running(
    vps_config: VpsSshConfig,
    caddy_config: CaddyConfig | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    """Verifies that the Caddy reverse-proxy container is active on remote VPS."""
    cfg = caddy_config or CaddyConfig()
    check_script = (
        f"if docker inspect -f '{{{{.State.Running}}}}' {cfg.container_name} 2>/dev/null | grep -q 'true'; "
        "then echo running; else echo not_running; fi"
    )
    cmd = build_ssh_cmd(vps_config, check_script)
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip() == "running":
            return True, f"Caddy container '{cfg.container_name}' is running."
        return False, f"Caddy container '{cfg.container_name}' is not running or missing."
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed to probe Caddy status on VPS: {exc}"


def ensure_caddy_network(
    vps_config: VpsSshConfig,
    caddy_config: CaddyConfig | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    """Ensures the Caddy container is connected to the target Docker network."""
    cfg = caddy_config or CaddyConfig()
    network_script = f"""
if ! docker inspect {cfg.container_name} --format '{{{{json .NetworkSettings.Networks}}}}' 2>/dev/null | grep -q '"{cfg.network}"'; then
  docker network connect {cfg.network} {cfg.container_name} >/dev/null 2>&1 || true
fi
if docker inspect {cfg.container_name} --format '{{{{json .NetworkSettings.Networks}}}}' 2>/dev/null | grep -q '"{cfg.network}"'; then
  echo connected
else
  echo disconnected
fi
"""
    cmd = build_ssh_cmd(vps_config, network_script.strip())
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode == 0 and "connected" in res.stdout:
            return True, f"Caddy is connected to network '{cfg.network}'."
        return False, f"Failed to attach Caddy to network '{cfg.network}'."
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Network attachment probe failed: {exc}"


def parse_caddyfile_domains(caddyfile_content: str) -> list[str]:
    """Parses existing site blocks / domain names from Caddyfile text."""
    domains: list[str] = []
    lines = caddyfile_content.splitlines()
    for line in lines:
        cleaned = line.split("#")[0].strip()
        if not cleaned:
            continue
        if cleaned.startswith("{") or cleaned.startswith("}"):
            continue
        # Pattern matching site block header: 'domain.com {' or 'sub.domain.com {' or bare domain
        match = re.match(r"^([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}(?::\d+)?)\s*\{?", cleaned)
        if match:
            domains.append(match.group(1))
    return domains


def format_caddy_route(domain: str, upstream: str) -> str:
    """Formats a standard Caddy reverse_proxy site block."""
    return f"\n{domain} {{\n\treverse_proxy {upstream}\n}}\n"


def ensure_caddy_route(
    vps_config: VpsSshConfig,
    domain: str,
    upstream: str = DEFAULT_WEB_UPSTREAM,
    caddy_config: CaddyConfig | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    """Idempotently adds a reverse_proxy block for domain to remote Caddyfile."""
    cfg = caddy_config or CaddyConfig()
    clean_domain = domain.strip().lower()

    read_cmd = build_ssh_cmd(vps_config, f"cat '{cfg.caddyfile_path}' 2>/dev/null || true")
    try:
        res = subprocess.run(read_cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return False, f"Could not read remote Caddyfile at {cfg.caddyfile_path}."
        content = res.stdout
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed to fetch remote Caddyfile: {exc}"

    existing_domains = parse_caddyfile_domains(content)
    if clean_domain in existing_domains:
        return True, f"Domain '{clean_domain}' is already configured in Caddyfile."

    new_block = format_caddy_route(clean_domain, upstream)
    append_script = f"cat << 'EOF' >> '{cfg.caddyfile_path}'\n{new_block}\nEOF"
    write_cmd = build_ssh_cmd(vps_config, append_script)

    try:
        w_res = subprocess.run(write_cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if w_res.returncode == 0:
            return True, f"Added reverse-proxy route for '{clean_domain}' -> '{upstream}'."
        return False, f"Failed to append route to Caddyfile: {w_res.stderr.strip()}"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed to update remote Caddyfile: {exc}"


def reload_caddy(
    vps_config: VpsSshConfig,
    caddy_config: CaddyConfig | None = None,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Triggers zero-downtime configuration reload on remote Caddy container."""
    cfg = caddy_config or CaddyConfig()
    reload_script = f"docker exec -w /etc/caddy {cfg.container_name} caddy reload >/dev/null 2>&1"
    cmd = build_ssh_cmd(vps_config, reload_script)
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True, f"Successfully reloaded Caddy configuration on container '{cfg.container_name}'."
        return False, f"Caddy reload failed (code {res.returncode}): {res.stderr.strip()}"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Caddy reload command timed out or failed: {exc}"


def setup_reverse_proxy(
    vps_config: VpsSshConfig,
    domain: str,
    upstream: str = DEFAULT_WEB_UPSTREAM,
    s3_domain: str | None = None,
    s3_upstream: str = DEFAULT_S3_UPSTREAM,
    caddy_config: CaddyConfig | None = None,
) -> tuple[bool, str]:
    """High-level orchestration: verifies Caddy, connects network, adds routes, and reloads."""
    cfg = caddy_config or CaddyConfig()

    ok, msg = check_caddy_running(vps_config, cfg)
    if not ok:
        return False, f"Caddy prerequisite check failed: {msg}"

    net_ok, net_msg = ensure_caddy_network(vps_config, cfg)
    if not net_ok:
        return False, f"Caddy network attachment failed: {net_msg}"

    route_ok, route_msg = ensure_caddy_route(vps_config, domain, upstream, cfg)
    if not route_ok:
        return False, f"Web route configuration failed: {route_msg}"

    s3_msg = ""
    if s3_domain:
        s3_ok, s3_res = ensure_caddy_route(vps_config, s3_domain, s3_upstream, cfg)
        if not s3_ok:
            return False, f"S3 route configuration failed: {s3_res}"
        s3_msg = f" and S3 route '{s3_domain}'"

    reload_ok, reload_msg = reload_caddy(vps_config, cfg)
    if not reload_ok:
        return False, f"Route added, but reload failed: {reload_msg}"

    return True, f"Reverse-proxy successfully configured for '{domain}'{s3_msg}. {reload_msg}"


def build_caddy_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for reverse-proxy setup CLI."""
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra caddy",
        description="Configure Caddy reverse-proxy for Resource Plane services on a remote VPS.",
    )
    parser.add_argument("--domain", help="Primary public domain for Resource Plane web console & MCP endpoint.")
    parser.add_argument("--s3-domain", default=None, help="Optional public domain for SeaweedFS S3 API endpoint.")
    parser.add_argument("--upstream", default=DEFAULT_WEB_UPSTREAM, help=f"Upstream web target (default: {DEFAULT_WEB_UPSTREAM}).")
    parser.add_argument("--s3-upstream", default=DEFAULT_S3_UPSTREAM, help=f"Upstream S3 target (default: {DEFAULT_S3_UPSTREAM}).")
    parser.add_argument("--host", help="VPS SSH host (defaults to RESOURCE_PLANE_SSH_HOST env var).")
    parser.add_argument("--user", help="VPS SSH user (defaults to RESOURCE_PLANE_SSH_USER env var or 'root').")
    parser.add_argument("--port", type=int, help="VPS SSH port (defaults to RESOURCE_PLANE_SSH_PORT env var or 22).")
    parser.add_argument("--key", help="Path to private SSH key file (required or RESOURCE_PLANE_SSH_KEY env var).")
    parser.add_argument("--caddy-dir", default=DEFAULT_CADDY_DIR, help=f"Remote Caddy directory (default: {DEFAULT_CADDY_DIR}).")
    parser.add_argument("--caddyfile", default=DEFAULT_CADDYFILE_PATH, help=f"Remote Caddyfile path (default: {DEFAULT_CADDYFILE_PATH}).")
    parser.add_argument("--check-only", action="store_true", help="Only verify Caddy status and connectivity without altering configuration.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for Caddy reverse-proxy setup."""
    parser = build_caddy_parser()
    args = parser.parse_args(argv)

    root = resolve_factory_root()
    env_file = root / ".env"
    file_env = parse_env_file(env_file) if env_file.exists() else {}

    try:
        vps_config = resolve_vps_ssh_config(
            host=args.host,
            user=args.user,
            port=args.port,
            key_path=args.key,
            dotenv=file_env,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        return 1

    caddy_cfg = CaddyConfig(
        caddy_dir=args.caddy_dir,
        caddyfile_path=args.caddyfile,
    )

    if args.check_only:
        print(f"🔍 Probing Caddy on VPS {vps_config.user}@{vps_config.host}:{vps_config.port}...")
        ok, msg = check_caddy_running(vps_config, caddy_cfg)
        if ok:
            print(f"✓ {msg}")
            net_ok, net_msg = ensure_caddy_network(vps_config, caddy_cfg)
            print(f"✓ {net_msg}" if net_ok else f"⚠ {net_msg}")
            return 0
        print(f"❌ {msg}", file=sys.stderr)
        return 1

    domain = (
        args.domain
        or os.environ.get("RESOURCE_PLANE_DOMAIN")
        or file_env.get("RESOURCE_PLANE_DOMAIN")
    )
    if not domain or not domain.strip():
        print("❌ Missing domain. Provide --domain or set RESOURCE_PLANE_DOMAIN in .env.", file=sys.stderr)
        return 1

    print(f"🔒 Configuring Caddy reverse-proxy on {vps_config.user}@{vps_config.host} for domain '{domain}'...")
    success, message = setup_reverse_proxy(
        vps_config=vps_config,
        domain=domain.strip(),
        upstream=args.upstream,
        s3_domain=args.s3_domain.strip() if args.s3_domain else None,
        s3_upstream=args.s3_upstream,
        caddy_config=caddy_cfg,
    )

    if success:
        print(f"✓ {message}")
        return 0
    print(f"❌ {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
