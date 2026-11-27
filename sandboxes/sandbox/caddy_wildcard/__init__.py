"""Wildcard TLS and host ingress helpers for Host Ingress Proxy (/opt/caddy)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess

from sandbox.config import resolve_factory_configuration
from sandbox.host_ingress import apply_configuration, prepare_runtime
from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd
from sandbox.profiles import get_client_for_profile

from ._rendering import (
    DASHBOARD_CLI_PROXY_RE,
    DASHBOARD_PROXY_RE,
    DEFAULT_DASHBOARD_WEB_UPSTREAM,
    DEFAULT_S3_UPSTREAM,
    DEFAULT_WEB_UPSTREAM,
    DNS_LABEL_RE,
    SITES_IMPORT_PATTERN,
    caddyfile_imports_sites,
    extract_dashboard_upstream,
    extract_dashboard_web_upstream,
    format_caddy_route,
    is_subdomain_of,
    normalize_base_domain,
    normalize_dashboard_upstream,
    normalize_dashboard_web_upstream,
    parse_caddyfile_domains,
    render_base_caddyfile,
    render_resource_plane_site,
    render_wildcard_site,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    sanitize_app_slug,
    validate_subdomain_label,
)

DEFAULT_CADDY_DIR = "/opt/caddy"
DEFAULT_CADDY_CONTAINER = "caddy"
DEFAULT_CADDY_NETWORK = "dbhost-network"
CONTROL_PLANE_APP_NAME = "sandbox-control-plane"
CONTROL_PLANE_FUNCTION_NAME = "fastapi_app"


def lookup_control_plane_web_url(
    *,
    dotenv: dict[str, str] | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Discovers the deployed Modal Sandbox Control Plane origin URL via Modal SDK."""
    import modal
    from sandbox.profiles import get_active_profile_name, load_profiles_config

    if dotenv:
        resolve_factory_configuration(repo_root=repo_root, env=dotenv, mutate_environ=True)
    else:
        resolve_factory_configuration(repo_root=repo_root, mutate_environ=True)

    active_profile = get_active_profile_name()
    profiles = load_profiles_config()
    env_name = profiles.get(active_profile, {}).get("environment") if active_profile else None
    client = get_client_for_profile(None, use_cache=False)
    fn = modal.Function.from_name(
        CONTROL_PLANE_APP_NAME,
        CONTROL_PLANE_FUNCTION_NAME,
        environment_name=env_name or None,
        client=client,
    )
    return fn.get_web_url()


def resolve_dashboard_upstream(
    explicit_upstream: str | None = None,
    *,
    base_domain: str,
    dotenv: dict[str, str] | None = None,
    repo_root: Path | None = None,
    lookup_fn=None,
) -> tuple[str | None, str | None]:
    """Resolves the Modal Control Plane upstream URL, returning (upstream, warning_or_error)."""
    env_map = dotenv or {}
    raw = (
        explicit_upstream
        or os.environ.get("SANDBOX_DASHBOARD_UPSTREAM")
        or env_map.get("SANDBOX_DASHBOARD_UPSTREAM")
    )
    if raw and raw.strip():
        return normalize_dashboard_upstream(raw, base_domain=base_domain), None

    lookup_err: str | None = None
    discover = lookup_fn or (lambda: lookup_control_plane_web_url(dotenv=env_map, repo_root=repo_root))
    try:
        discovered = discover()
        if discovered and discovered.strip():
            return normalize_dashboard_upstream(discovered, base_domain=base_domain), None
        lookup_err = f"Deployed Modal function '{CONTROL_PLANE_APP_NAME}.{CONTROL_PLANE_FUNCTION_NAME}' has no web URL."
    except Exception as exc:
        lookup_err = f"Could not look up Modal Control Plane web URL: {exc}"

    endpoint_fallback = os.environ.get("MODAL_SANDBOX_ENDPOINT_URL") or env_map.get("MODAL_SANDBOX_ENDPOINT_URL")
    if endpoint_fallback and endpoint_fallback.strip():
        try:
            return normalize_dashboard_upstream(endpoint_fallback, base_domain=base_domain), None
        except ValueError:
            pass

    return None, lookup_err


def _ssh_run(vps_config: VpsSshConfig, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(build_ssh_cmd(vps_config, cmd), timeout=timeout, capture_output=True, text=True, check=False)


def _read_remote(vps_config: VpsSshConfig, path: str, timeout: int = 20) -> tuple[bool, str]:
    try:
        res = _ssh_run(vps_config, f"cat '{path}' 2>/dev/null || true", timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed reading {path}: {exc}"
    if res.returncode != 0:
        return False, f"Could not read {path}: {res.stderr.strip()}"
    return True, res.stdout


def _write_remote_b64(
    vps_config: VpsSshConfig,
    remote_path: str,
    content: str,
    *,
    mode: str | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    parent = str(Path(remote_path).parent)
    chmod_part = f" && chmod {mode} '{remote_path}'" if mode else ""
    script = (
        f"mkdir -p '{parent}' && printf '%s' '{encoded}' | base64 -d > '{remote_path}.tmp' && "
        f"mv '{remote_path}.tmp' '{remote_path}'{chmod_part}"
    )
    try:
        res = _ssh_run(vps_config, script, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed writing {remote_path}: {exc}"
    if res.returncode != 0:
        return False, f"Failed writing {remote_path}: {res.stderr.strip()}"
    return True, f"Updated {remote_path}."


def write_and_validate_caddy_file(
    vps_config: VpsSshConfig,
    remote_path: str,
    desired: str,
    *,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    timeout: int = 90,
) -> tuple[bool, bool, str]:
    """Applies and activates a Caddy conf file, restoring prior state on failure."""
    caddy_dir, separator, relative_path = remote_path.partition("/conf/")
    if not separator:
        raise ValueError("Caddy configuration files must be under the Host Ingress Proxy conf directory.")
    result = apply_configuration(
        vps_config, {f"conf/{relative_path}": desired},
        caddy_dir=caddy_dir, container_name=container_name, timeout=timeout,
    )
    return result.success, result.changed, result.message


def check_caddy_has_cloudflare_module(
    vps_config: VpsSshConfig,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    timeout: int = 15,
) -> bool:
    """Returns True if the running Caddy binary includes dns.providers.cloudflare."""
    try:
        res = _ssh_run(
            vps_config,
            f"docker exec {container_name} caddy list-modules 2>/dev/null | grep -qE '(^|[[:space:]])dns\\.providers\\.cloudflare([[:space:]]|$)'",
            timeout=timeout,
        )
        return res.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def sync_caddy_wildcard_runtime(
    vps_config: VpsSshConfig,
    cf_dns_token: str,
    *,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    source_dir: Path | None = None,
    timeout: int = 360,
) -> tuple[bool, bool, str]:
    """Converges the canonical build context and wildcard DNS credential."""
    result = prepare_runtime(
        vps_config, source_dir=source_dir, cf_dns_token=cf_dns_token,
        require_cloudflare=True, caddy_dir=caddy_dir,
        container_name=container_name, timeout=timeout,
    )
    return result.success, result.changed, result.message


def resolve_wildcard_dashboard_upstream(
    base_domain: str,
    *,
    explicit_upstream: str | None = None,
    require_dashboard: bool = False,
    no_dashboard: bool = False,
    dotenv: dict[str, str] | None = None,
    lookup_fn=None,
) -> tuple[bool, str | None, str]:
    """Resolves dashboard upstream for wildcard Caddy setup without remote SSH probes."""
    if no_dashboard:
        return True, None, "Apex dashboard routing disabled (--no-dashboard); apex returns 404."

    try:
        upstream, lookup_note = resolve_dashboard_upstream(
            explicit_upstream, base_domain=base_domain, dotenv=dotenv, lookup_fn=lookup_fn,
        )
    except ValueError as exc:
        return False, None, str(exc)

    if upstream:
        return True, upstream, f"Routing apex 'https://{base_domain}' -> '{upstream}'."

    if require_dashboard or (explicit_upstream and explicit_upstream.strip()):
        return False, None, lookup_note or "Sandbox Web Dashboard upstream URL could not be resolved."

    note = f"{lookup_note} " if lookup_note else ""
    return True, None, (
        f"Warning: {note}Preserving existing apex route if configured, or 404 until "
        "sandbox-control-plane is deployed and re-run with --dashboard."
    )


def ensure_wildcard_caddy(
    vps_config: VpsSshConfig,
    base_domain: str,
    cf_dns_token: str,
    *,
    bootstrap: bool = False,
    email: str | None = None,
    dashboard_upstream: str | None = None,
    dashboard_web_upstream: str | None = None,
    preserve_dashboard: bool = False,
    apex_cli_only: bool = False,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    network: str = DEFAULT_CADDY_NETWORK,
    source_dir: Path | None = None,
) -> tuple[bool, str]:
    """Converges wildcard runtime and configuration in one recoverable change."""
    clean_base = normalize_base_domain(base_domain)
    clean_token = resolve_cloudflare_dns_token(cf_dns_token)
    effective_upstream = dashboard_upstream
    effective_web_upstream = dashboard_web_upstream
    if (not effective_upstream or not effective_web_upstream) and preserve_dashboard and not bootstrap:
        ok_read, remote_site = _read_remote(vps_config, f"{caddy_dir}/conf/sites/apps-wildcard.caddy")
        if ok_read and remote_site.strip():
            if not effective_upstream:
                preserved = extract_dashboard_upstream(remote_site)
                if preserved:
                    try:
                        effective_upstream = normalize_dashboard_upstream(preserved, base_domain=clean_base)
                    except ValueError:
                        effective_upstream = None
            if not effective_web_upstream:
                preserved_web = extract_dashboard_web_upstream(remote_site)
                if preserved_web:
                    try:
                        effective_web_upstream = normalize_dashboard_web_upstream(preserved_web, base_domain=clean_base)
                    except ValueError:
                        effective_web_upstream = None
    site_content = render_wildcard_site(
        clean_base,
        dashboard_upstream=effective_upstream,
        dashboard_web_upstream=effective_web_upstream,
        apex_cli_only=apex_cli_only and not effective_web_upstream,
    )
    result = prepare_runtime(
        vps_config, source_dir=source_dir, bootstrap=bootstrap, email=email,
        files={"conf/sites/apps-wildcard.caddy": site_content},
        cf_dns_token=clean_token, require_cloudflare=True, caddy_dir=caddy_dir,
        container_name=container_name, network=network,
    )
    return result.success, result.message


__all__ = [
    "CONTROL_PLANE_APP_NAME",
    "CONTROL_PLANE_FUNCTION_NAME",
    "DASHBOARD_CLI_PROXY_RE",
    "DASHBOARD_PROXY_RE",
    "DEFAULT_CADDY_CONTAINER",
    "DEFAULT_CADDY_DIR",
    "DEFAULT_CADDY_NETWORK",
    "DEFAULT_DASHBOARD_WEB_UPSTREAM",
    "DEFAULT_S3_UPSTREAM",
    "DEFAULT_WEB_UPSTREAM",
    "DNS_LABEL_RE",
    "SITES_IMPORT_PATTERN",
    "_read_remote",
    "_ssh_run",
    "_write_remote_b64",
    "apply_configuration",
    "build_ssh_cmd",
    "caddyfile_imports_sites",
    "check_caddy_has_cloudflare_module",
    "ensure_wildcard_caddy",
    "extract_dashboard_upstream",
    "extract_dashboard_web_upstream",
    "format_caddy_route",
    "get_client_for_profile",
    "is_subdomain_of",
    "lookup_control_plane_web_url",
    "normalize_base_domain",
    "normalize_dashboard_upstream",
    "normalize_dashboard_web_upstream",
    "parse_caddyfile_domains",
    "prepare_runtime",
    "render_base_caddyfile",
    "render_resource_plane_site",
    "render_wildcard_site",
    "resolve_apps_base_domain",
    "resolve_cloudflare_dns_token",
    "resolve_dashboard_upstream",
    "resolve_factory_configuration",
    "resolve_wildcard_dashboard_upstream",
    "sanitize_app_slug",
    "sync_caddy_wildcard_runtime",
    "validate_subdomain_label",
    "write_and_validate_caddy_file",
]
