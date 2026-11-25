"""Per-app Caddy wildcard snippet routing and collision detection."""

from __future__ import annotations

import re
import subprocess

from sandbox.caddy_wildcard import (
    DEFAULT_CADDY_CONTAINER,
    DEFAULT_CADDY_DIR,
    DEFAULT_CADDY_NETWORK,
    _read_remote,
    _ssh_run,
    ensure_wildcard_caddy,
    sanitize_app_slug,
    write_and_validate_caddy_file,
)
from sandbox.infra_deploy import VpsSshConfig

DEFAULT_CADDY_APPS_DIR = "/opt/caddy/conf/apps"
APP_HOST_MATCHER_RE = re.compile(r"^\s*@\S+\s+host\s+([A-Za-z0-9.-]+)\s*$", re.MULTILINE)


def render_app_route(app_slug: str, fqdn: str, upstream: str) -> str:
    """Renders a host-matched Caddy handle snippet imported inside the wildcard block."""
    clean_slug = sanitize_app_slug(app_slug)
    matcher_id = clean_slug.replace("-", "_")
    clean_host = fqdn.strip().lower()
    return (
        f"# Managed by deploy-app (app: {clean_slug})\n"
        f"@app_{matcher_id} host {clean_host}\n"
        f"handle @app_{matcher_id} {{\n"
        f"\treverse_proxy {upstream.strip()}\n"
        "}\n"
    )


def check_app_route_collision(
    vps_config: VpsSshConfig,
    app_slug: str,
    fqdn: str,
    *,
    apps_dir: str = DEFAULT_CADDY_APPS_DIR,
) -> tuple[bool, str]:
    """Ensures no other Hosted App snippet in conf/apps/*.caddy claims fqdn."""
    clean_slug = sanitize_app_slug(app_slug)
    clean_host = fqdn.strip().lower()
    script = (
        f"if [ -d '{apps_dir}' ]; then "
        f"for f in '{apps_dir}'/*.caddy; do [ -f \"$f\" ] || continue; "
        f"echo \"FILE:$(basename \"$f\")\"; cat \"$f\"; echo '---END---'; "
        f"done; fi"
    )
    try:
        res = _ssh_run(vps_config, script, timeout=20)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed checking existing app routes: {exc}"
    if res.returncode != 0:
        return False, f"Failed checking existing app routes: {res.stderr.strip()}"

    current_file = ""
    current_lines: list[str] = []
    for line in res.stdout.splitlines():
        if line.startswith("FILE:"):
            current_file = line[5:].strip()
            current_lines = []
        elif line == "---END---":
            if current_file and current_file != f"{clean_slug}.caddy":
                hosts = [m.lower() for m in APP_HOST_MATCHER_RE.findall("\n".join(current_lines))]
                if clean_host in hosts:
                    owner_app = current_file.removesuffix(".caddy")
                    return False, (
                        f"Domain '{clean_host}' is already assigned to Hosted App '{owner_app}' "
                        f"({apps_dir}/{current_file}). Pass --subdomain to choose another subdomain."
                    )
            current_file = ""
            current_lines = []
        else:
            current_lines.append(line)
    return True, ""


def ensure_app_caddy_route(
    vps_config: VpsSshConfig,
    app_slug: str,
    fqdn: str,
    upstream: str,
    *,
    base_domain: str | None = None,
    cf_dns_token: str | None = None,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    network: str = DEFAULT_CADDY_NETWORK,
) -> tuple[bool, str]:
    """Adds or updates an app snippet under /opt/caddy/conf/apps/ inside the wildcard block."""
    from sandbox.caddy_deploy import CaddyConfig, check_caddy_running, ensure_caddy_network, reload_caddy

    cfg = CaddyConfig(caddy_dir=caddy_dir, container_name=container_name, network=network)
    running, run_msg = check_caddy_running(vps_config, cfg)
    if not running:
        return False, f"{run_msg} Run 'modal-sandbox infra caddy --bootstrap --wildcard' first."

    net_ok, net_msg = ensure_caddy_network(vps_config, cfg)
    if not net_ok:
        return False, net_msg

    wildcard_path = f"{caddy_dir}/conf/sites/apps-wildcard.caddy"
    ok_wc, wc_content = _read_remote(vps_config, wildcard_path)
    if not ok_wc:
        return False, wc_content
    if not wc_content.strip():
        if base_domain and cf_dns_token:
            wc_ok, wc_msg = ensure_wildcard_caddy(
                vps_config, base_domain, cf_dns_token, caddy_dir=caddy_dir, container_name=container_name, network=network
            )
            if not wc_ok:
                return False, wc_msg
        else:
            return False, (
                f"Wildcard Caddy site '{wildcard_path}' is missing on VPS. "
                "Run 'modal-sandbox infra caddy --wildcard' (with APPS_BASE_DOMAIN and CLOUDFLARE_DNS_API_TOKEN) first."
            )

    apps_dir = f"{caddy_dir}/conf/apps"
    col_ok, col_msg = check_app_route_collision(vps_config, app_slug, fqdn, apps_dir=apps_dir)
    if not col_ok:
        return False, col_msg

    clean_slug = sanitize_app_slug(app_slug)
    route_path = f"{apps_dir}/{clean_slug}.caddy"
    route_ok, changed, route_msg = write_and_validate_caddy_file(
        vps_config, route_path, render_app_route(clean_slug, fqdn, upstream), container_name=container_name
    )
    if not route_ok:
        return False, route_msg
    if not changed:
        return True, f"Caddy route for 'https://{fqdn}' -> '{upstream}' is already up to date."

    rel_ok, rel_msg = reload_caddy(vps_config, cfg)
    if not rel_ok:
        return False, f"App route updated, but reload failed: {rel_msg}"
    return True, f"Configured wildcard Caddy route 'https://{fqdn}' -> '{upstream}'. {rel_msg}"


def remove_app_caddy_route(
    vps_config: VpsSshConfig,
    app_slug: str,
    *,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    network: str = DEFAULT_CADDY_NETWORK,
) -> tuple[bool, str]:
    """Removes a Hosted App's snippet from /opt/caddy/conf/apps/ and reloads Caddy."""
    from sandbox.caddy_deploy import CaddyConfig, check_caddy_running, reload_caddy

    clean_slug = sanitize_app_slug(app_slug)
    route_path = f"{caddy_dir}/conf/apps/{clean_slug}.caddy"
    cfg = CaddyConfig(caddy_dir=caddy_dir, container_name=container_name, network=network)

    running, _ = check_caddy_running(vps_config, cfg)
    ok_cur, existing = _read_remote(vps_config, route_path)
    if not ok_cur:
        return False, existing
    if not existing:
        return True, f"No Caddy route found at '{route_path}' (already clean)."

    try:
        res = _ssh_run(vps_config, f"rm -f '{route_path}'", timeout=20)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed removing {route_path}: {exc}"
    if res.returncode != 0:
        return False, f"Failed removing {route_path}: {res.stderr.strip()}"

    if not running:
        return True, f"Removed '{route_path}' (Caddy not running; reload skipped)."

    rel_ok, rel_msg = reload_caddy(vps_config, cfg)
    if not rel_ok:
        return False, f"Removed '{route_path}', but reload failed: {rel_msg}"
    return True, f"Removed '{route_path}'. {rel_msg}"
