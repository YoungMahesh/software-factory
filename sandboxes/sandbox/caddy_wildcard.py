"""Wildcard TLS and host ingress rendering helpers for Host Ingress Proxy (/opt/caddy)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import subprocess
import urllib.parse

from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd

DEFAULT_CADDY_DIR = "/opt/caddy"
DEFAULT_CADDY_CONTAINER = "caddy"
DEFAULT_CADDY_NETWORK = "dbhost-network"
DEFAULT_WEB_UPSTREAM = "db-host-web:3000"
DEFAULT_S3_UPSTREAM = "neon-seaweedfs:8333"

SITES_IMPORT_PATTERN = re.compile(
    r"^\s*import\s+(?:/etc/caddy/sites/\*\.caddy|sites/\*\.caddy)\s*$",
    re.MULTILINE,
)
DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def render_base_caddyfile(email: str | None = None) -> str:
    """Renders root Caddyfile containing global options and sites import."""
    global_block = f"{{\n\temail {email.strip()}\n}}\n" if email and email.strip() else "{\n}\n"
    return f"{global_block}\nimport /etc/caddy/sites/*.caddy\n"


def format_caddy_route(domain: str, upstream: str) -> str:
    """Formats a standard Caddy reverse_proxy site block."""
    return f"{domain.strip().lower()} {{\n\treverse_proxy {upstream}\n}}\n"


def render_resource_plane_site(
    domain: str,
    upstream: str = DEFAULT_WEB_UPSTREAM,
    s3_domain: str | None = None,
    s3_upstream: str = DEFAULT_S3_UPSTREAM,
) -> str:
    """Renders the declarative Resource Plane site configuration file."""
    blocks = ["# Managed by modal-sandbox infra caddy\n", format_caddy_route(domain, upstream)]
    if s3_domain and s3_domain.strip():
        blocks.append("\n" + format_caddy_route(s3_domain, s3_upstream))
    return "".join(blocks)


def caddyfile_imports_sites(caddyfile_content: str) -> bool:
    """Checks whether Caddyfile imports modular /etc/caddy/sites/*.caddy files."""
    stripped = "\n".join(line.split("#", 1)[0] for line in caddyfile_content.splitlines())
    return bool(SITES_IMPORT_PATTERN.search(stripped))


def parse_caddyfile_domains(caddyfile_content: str) -> list[str]:
    """Parses site block domain names from Caddyfile text."""
    domains: list[str] = []
    for line in caddyfile_content.splitlines():
        cleaned = line.split("#", 1)[0].strip()
        if not cleaned or cleaned.startswith("{") or cleaned.startswith("}"):
            continue
        match = re.match(r"^([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}(?::\d+)?)\s*\{?", cleaned)
        if match:
            domains.append(match.group(1))
    return domains


def normalize_base_domain(raw_domain: str) -> str:
    """Normalizes and validates a base DNS domain (e.g. sf.mahesh0.dev)."""
    cleaned = raw_domain.strip()
    if "://" in cleaned:
        parsed = urllib.parse.urlparse(cleaned)
        cleaned = parsed.netloc or parsed.path
    cleaned = cleaned.split("/", 1)[0].split(":", 1)[0].strip().lower().lstrip("*.").rstrip(".")
    labels = [part for part in cleaned.split(".") if part]
    if len(labels) < 2 or not all(DNS_LABEL_RE.match(lbl) for lbl in labels):
        raise ValueError(f"Invalid base domain '{raw_domain}'. Expected a DNS domain like 'sf.mahesh0.dev'.")
    return ".".join(labels)


def resolve_apps_base_domain(
    base_domain: str | None = None,
    *,
    dotenv: dict[str, str] | None = None,
) -> str:
    """Resolves APPS_BASE_DOMAIN from explicit arg, os.environ, or .env."""
    raw = base_domain or os.environ.get("APPS_BASE_DOMAIN") or (dotenv or {}).get("APPS_BASE_DOMAIN")
    if not raw or not raw.strip():
        raise ValueError("Missing App Base Domain. Set APPS_BASE_DOMAIN in .env or pass --base-domain.")
    return normalize_base_domain(raw)


def resolve_cloudflare_dns_token(
    token: str | None = None,
    *,
    dotenv: dict[str, str] | None = None,
) -> str:
    """Resolves Cloudflare DNS-01 token from explicit arg, env, or .env."""
    env_map = dotenv or {}
    resolved = (
        token
        or os.environ.get("CLOUDFLARE_DNS_API_TOKEN")
        or env_map.get("CLOUDFLARE_DNS_API_TOKEN")
        or os.environ.get("CLOUDFLARE_API_TOKEN")
        or env_map.get("CLOUDFLARE_API_TOKEN")
    )
    if not resolved or not resolved.strip():
        raise ValueError(
            "Missing Cloudflare DNS API token. Set CLOUDFLARE_DNS_API_TOKEN (or CLOUDFLARE_API_TOKEN "
            "with Zone:DNS:Edit) in .env or pass --cf-dns-token."
        )
    return resolved.strip()


def sanitize_app_slug(name: str) -> str:
    """Derives a safe DNS/container slug from a repository or app name."""
    cleaned = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return (cleaned[:63].strip("-") or "app") if cleaned else "app"


def validate_subdomain_label(label: str) -> str:
    """Normalizes and validates a single DNS subdomain label."""
    cleaned = label.strip().lower()
    if not DNS_LABEL_RE.match(cleaned):
        raise ValueError(
            f"Invalid subdomain label '{label}'. Use 1-63 lowercase alphanumeric characters or hyphens."
        )
    return cleaned


def is_subdomain_of(domain: str, base_domain: str) -> bool:
    """Returns True if domain equals base_domain or is a subdomain of it."""
    clean_domain = domain.strip().lower().rstrip(".")
    clean_base = normalize_base_domain(base_domain)
    return clean_domain == clean_base or clean_domain.endswith(f".{clean_base}")


def render_wildcard_site(base_domain: str) -> str:
    """Renders the Caddy wildcard site block backed by Cloudflare DNS-01."""
    clean = normalize_base_domain(base_domain)
    return (
        "# Managed by modal-sandbox infra caddy (wildcard ingress)\n"
        f"{clean}, *.{clean} {{\n"
        "\ttls {\n"
        "\t\tdns cloudflare {env.CLOUDFLARE_DNS_API_TOKEN}\n"
        "\t}\n"
        "\timport /etc/caddy/apps/*.caddy\n"
        "\thandle {\n"
        '\t\trespond "Not Found" 404\n'
        "\t}\n"
        "}\n"
    )


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
    timeout: int = 30,
) -> tuple[bool, bool, str]:
    """Atomically writes a Caddy conf file, validates with caddy validate, and rolls back on error."""
    ok_cur, existing = _read_remote(vps_config, remote_path, timeout=timeout)
    if not ok_cur:
        return False, False, existing
    if existing == desired:
        return True, False, f"'{remote_path}' is already up to date."

    encoded = base64.b64encode(desired.encode("utf-8")).decode("ascii")
    parent = str(Path(remote_path).parent)
    script = (
        f"mkdir -p '{parent}' && "
        f"if [ -f '{remote_path}' ]; then cp '{remote_path}' '{remote_path}.bak'; else rm -f '{remote_path}.bak'; fi && "
        f"printf '%s' '{encoded}' | base64 -d > '{remote_path}' && "
        f"if ! docker exec {container_name} caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then "
        f"  err=$(docker exec {container_name} caddy validate --config /etc/caddy/Caddyfile 2>&1 || true); "
        f"  if [ -f '{remote_path}.bak' ]; then mv '{remote_path}.bak' '{remote_path}'; else rm -f '{remote_path}'; fi; "
        f"  echo \"VALIDATION_ERR:$err\" >&2; exit 1; "
        f"fi && rm -f '{remote_path}.bak'"
    )
    try:
        res = _ssh_run(vps_config, script, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, False, f"Failed updating {remote_path}: {exc}"
    if res.returncode != 0:
        return False, False, f"Failed updating {remote_path}: {res.stderr.strip() or res.stdout.strip()}"
    return True, True, f"Updated '{remote_path}'."


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
    """Ensures /opt/caddy uses the caddy-dns/cloudflare build and /opt/caddy/.env token."""
    from sandbox.caddy_deploy import find_caddy_source_dir

    src = source_dir or find_caddy_source_dir()
    dockerfile_path = src / "Dockerfile"
    compose_path = src / "docker-compose.yml"
    if not dockerfile_path.is_file():
        return False, False, f"Missing Caddy Dockerfile at {dockerfile_path}."

    desired_df = dockerfile_path.read_text(encoding="utf-8")
    desired_dc = compose_path.read_text(encoding="utf-8")
    desired_env = f"CLOUDFLARE_DNS_API_TOKEN={cf_dns_token.strip()}\n"

    ok_df, cur_df = _read_remote(vps_config, f"{caddy_dir}/Dockerfile")
    ok_dc, cur_dc = _read_remote(vps_config, f"{caddy_dir}/docker-compose.yml")
    ok_env, cur_env = _read_remote(vps_config, f"{caddy_dir}/.env")
    if not ok_df or not ok_dc or not ok_env:
        return False, False, cur_df if not ok_df else (cur_dc if not ok_dc else cur_env)

    has_cf = check_caddy_has_cloudflare_module(vps_config, container_name=container_name)
    needs_rebuild = cur_df != desired_df or cur_dc != desired_dc or cur_env != desired_env or not has_cf

    for path, cur, desired, mode in (
        (f"{caddy_dir}/Dockerfile", cur_df, desired_df, None),
        (f"{caddy_dir}/docker-compose.yml", cur_dc, desired_dc, None),
        (f"{caddy_dir}/.env", cur_env, desired_env, "0600"),
    ):
        if cur != desired:
            ok, msg = _write_remote_b64(vps_config, path, desired, mode=mode)
            if not ok:
                return False, False, msg

    _ssh_run(vps_config, f"mkdir -p '{caddy_dir}/conf/sites' '{caddy_dir}/conf/apps'", timeout=15)
    if not needs_rebuild:
        return True, False, "Caddy wildcard runtime and Cloudflare DNS token are up to date."

    build_flag = "--build " if (cur_df != desired_df or not has_cf) else ""
    try:
        res = _ssh_run(vps_config, f"cd '{caddy_dir}' && docker compose up -d {build_flag}".strip(), timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, False, f"Failed rebuilding/restarting {caddy_dir}: {exc}"
    if res.returncode != 0:
        return False, False, f"Failed rebuilding/restarting {caddy_dir}: {res.stderr.strip() or res.stdout.strip()}"
    return True, True, "Upgraded /opt/caddy with caddy-dns/cloudflare and /opt/caddy/.env."


def ensure_wildcard_caddy(
    vps_config: VpsSshConfig,
    base_domain: str,
    cf_dns_token: str,
    *,
    bootstrap: bool = False,
    email: str | None = None,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    container_name: str = DEFAULT_CADDY_CONTAINER,
    network: str = DEFAULT_CADDY_NETWORK,
    source_dir: Path | None = None,
) -> tuple[bool, str]:
    """Configures /opt/caddy with caddy-dns/cloudflare and a single wildcard cert block."""
    from sandbox.caddy_deploy import (
        CaddyConfig,
        check_caddy_running,
        check_ports_available,
        ensure_caddy_network,
        ensure_docker_network,
        find_caddy_source_dir,
        reload_caddy,
    )

    clean_base = normalize_base_domain(base_domain)
    clean_token = resolve_cloudflare_dns_token(cf_dns_token)
    cfg = CaddyConfig(caddy_dir=caddy_dir, container_name=container_name, network=network)
    wildcard_path = f"{caddy_dir}/conf/sites/apps-wildcard.caddy"

    running, _ = check_caddy_running(vps_config, cfg)
    if not running:
        if not bootstrap:
            return False, f"Caddy container '{container_name}' is not running. Re-run with --bootstrap."
        ports_ok, ports_msg = check_ports_available(vps_config)
        if not ports_ok:
            return False, ports_msg
        net_ok, net_msg = ensure_docker_network(vps_config, network)
        if not net_ok:
            return False, net_msg

        src = source_dir or find_caddy_source_dir()
        cf_probe = _ssh_run(vps_config, f"test -f '{caddy_dir}/conf/Caddyfile' && echo exists || echo missing", timeout=15)
        if cf_probe.returncode != 0:
            return False, f"Failed probing {caddy_dir}/conf/Caddyfile: {cf_probe.stderr.strip()}"
        if cf_probe.stdout.strip() == "missing" or (email and email.strip()):
            cf_content = render_base_caddyfile(email) if (email and email.strip()) else (src / "conf" / "Caddyfile").read_text(encoding="utf-8")
            ok_cf, msg_cf = _write_remote_b64(vps_config, f"{caddy_dir}/conf/Caddyfile", cf_content)
            if not ok_cf:
                return False, msg_cf
        ok_wc, msg_wc = _write_remote_b64(vps_config, wildcard_path, render_wildcard_site(clean_base))
        if not ok_wc:
            return False, msg_wc

        rt_ok, _, rt_msg = sync_caddy_wildcard_runtime(
            vps_config, clean_token, caddy_dir=caddy_dir, container_name=container_name, source_dir=src
        )
        if not rt_ok:
            return False, rt_msg
        run_ok, run_msg = check_caddy_running(vps_config, cfg)
        if not run_ok:
            return False, f"Caddy wildcard bootstrap failed health check: {run_msg}"
        return True, f"Bootstrapped wildcard Caddy ingress for '{clean_base}, *.{clean_base}' at {caddy_dir}."

    net_ok, net_msg = ensure_caddy_network(vps_config, cfg)
    if not net_ok:
        return False, net_msg

    ok_cf, cf_content = _read_remote(vps_config, f"{caddy_dir}/conf/Caddyfile")
    if not ok_cf:
        return False, cf_content
    if not caddyfile_imports_sites(cf_content):
        return False, f"Remote Caddyfile at {caddy_dir}/conf/Caddyfile does not import sites/*.caddy."

    rt_ok, rt_changed, rt_msg = sync_caddy_wildcard_runtime(
        vps_config, clean_token, caddy_dir=caddy_dir, container_name=container_name, source_dir=source_dir
    )
    if not rt_ok:
        return False, rt_msg

    _ssh_run(vps_config, f"mkdir -p '{caddy_dir}/conf/apps'", timeout=15)
    site_ok, site_changed, site_msg = write_and_validate_caddy_file(
        vps_config, wildcard_path, render_wildcard_site(clean_base), container_name=container_name
    )
    if not site_ok:
        return False, site_msg
    if not rt_changed and not site_changed:
        return True, f"Wildcard Caddy ingress for '{clean_base}, *.{clean_base}' is already up to date."

    rel_ok, rel_msg = reload_caddy(vps_config, cfg)
    if not rel_ok:
        return False, f"Wildcard site updated, but Caddy reload failed: {rel_msg}"
    return True, f"Configured wildcard Caddy ingress for '{clean_base}, *.{clean_base}'. {rel_msg}"
