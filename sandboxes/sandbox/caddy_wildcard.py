"""Wildcard TLS and host ingress rendering helpers for Host Ingress Proxy (/opt/caddy)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import subprocess
import urllib.parse

from sandbox.host_ingress import apply_configuration, prepare_runtime
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
    """Converges wildcard runtime and configuration in one recoverable change."""
    clean_base = normalize_base_domain(base_domain)
    clean_token = resolve_cloudflare_dns_token(cf_dns_token)
    result = prepare_runtime(
        vps_config, source_dir=source_dir, bootstrap=bootstrap, email=email,
        files={"conf/sites/apps-wildcard.caddy": render_wildcard_site(clean_base)},
        cf_dns_token=clean_token, require_cloudflare=True, caddy_dir=caddy_dir,
        container_name=container_name, network=network,
    )
    return result.success, result.message
