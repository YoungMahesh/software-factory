"""Pure Caddyfile rendering, domain normalization, and upstream validation helpers."""

from __future__ import annotations

import os
import re
import urllib.parse

DEFAULT_WEB_UPSTREAM = "db-host-web:3000"
DEFAULT_DASHBOARD_WEB_UPSTREAM = "sandbox-dashboard-web:3000"
DEFAULT_S3_UPSTREAM = "neon-seaweedfs:8333"

SITES_IMPORT_PATTERN = re.compile(
    r"^\s*import\s+(?:/etc/caddy/sites/\*\.caddy|sites/\*\.caddy)\s*$",
    re.MULTILINE,
)
DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DASHBOARD_CLI_PROXY_RE = re.compile(
    r"@sandbox_dashboard_cli\b.*?handle\s+@sandbox_dashboard_cli\s*\{.*?reverse_proxy\s+(\S+)",
    re.DOTALL,
)
DASHBOARD_PROXY_RE = re.compile(
    r"@sandbox_dashboard\s+host\s+\S+\s*.*?handle\s+@sandbox_dashboard\s*\{.*?reverse_proxy\s+(\S+)",
    re.DOTALL,
)


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
    """Normalizes and validates a base DNS domain (e.g. apps.example.com)."""
    cleaned = raw_domain.strip()
    if "://" in cleaned:
        parsed = urllib.parse.urlparse(cleaned)
        cleaned = parsed.netloc or parsed.path
    cleaned = cleaned.split("/", 1)[0].split(":", 1)[0].strip().lower().lstrip("*.").rstrip(".")
    labels = [part for part in cleaned.split(".") if part]
    if len(labels) < 2 or not all(DNS_LABEL_RE.match(lbl) for lbl in labels):
        raise ValueError(f"Invalid base domain '{raw_domain}'. Expected a DNS domain like 'apps.example.com'.")
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


def _validate_origin_parts(
    raw_url: str,
    *,
    default_scheme: str,
    base_domain: str | None,
    label: str,
) -> tuple[urllib.parse.SplitResult, bool]:
    cleaned = raw_url.strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty.")
    has_scheme = "://" in cleaned
    probe = cleaned if has_scheme else f"{default_scheme}://{cleaned}"
    parsed = urllib.parse.urlsplit(probe)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"Invalid {label.lower()} '{raw_url}'.")
    if (parsed.path and parsed.path != "/") or parsed.query or parsed.fragment:
        raise ValueError(f"{label} '{raw_url}' must not include path, query, or fragment.")
    if base_domain and is_subdomain_of(parsed.hostname, base_domain):
        raise ValueError(
            f"{label} '{raw_url}' cannot target '{base_domain}' or its subdomains "
            "(would create a reverse-proxy loop)."
        )
    return parsed, has_scheme


def normalize_dashboard_upstream(raw_url: str, *, base_domain: str | None = None) -> str:
    """Normalizes and validates the Sandbox Web Dashboard Modal origin URL."""
    parsed, _ = _validate_origin_parts(
        raw_url,
        default_scheme="https",
        base_domain=base_domain,
        label="Dashboard upstream URL",
    )
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def normalize_dashboard_web_upstream(raw_url: str, *, base_domain: str | None = None) -> str:
    """Normalizes and validates a Next.js dashboard web upstream (Docker service or http(s) origin)."""
    parsed, has_scheme = _validate_origin_parts(
        raw_url,
        default_scheme="http",
        base_domain=base_domain,
        label="Dashboard web upstream",
    )
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}" if has_scheme else parsed.netloc.lower()


def extract_dashboard_upstream(site_content: str) -> str | None:
    """Extracts an existing Modal Control Plane upstream from apps-wildcard.caddy."""
    cli_match = DASHBOARD_CLI_PROXY_RE.search(site_content)
    if cli_match:
        return cli_match.group(1).strip()
    match = DASHBOARD_PROXY_RE.search(site_content)
    return match.group(1).strip() if match else None


def extract_dashboard_web_upstream(site_content: str) -> str | None:
    """Extracts an existing Next.js dashboard web upstream when split apex routing is active."""
    if not DASHBOARD_CLI_PROXY_RE.search(site_content):
        return None
    match = DASHBOARD_PROXY_RE.search(site_content)
    return match.group(1).strip() if match else None


def _format_proxy_handle(
    matcher_name: str,
    matcher_decl: str,
    upstream: str,
    *,
    preserve_host: bool = False,
) -> str:
    host_line = "\t\t\theader_up Host {upstream_hostport}\n" if preserve_host else ""
    return (
        f"{matcher_decl}"
        f"\thandle @{matcher_name} {{\n"
        f"\t\treverse_proxy {upstream} {{\n"
        f"{host_line}"
        "\t\t\tflush_interval -1\n"
        "\t\t}\n"
        "\t}\n"
    )


def render_wildcard_site(
    base_domain: str,
    *,
    dashboard_upstream: str | None = None,
    dashboard_web_upstream: str | None = None,
    apex_cli_only: bool = False,
) -> str:
    """Renders the Caddy wildcard site block backed by Cloudflare DNS-01."""
    clean = normalize_base_domain(base_domain)
    has_modal = bool(dashboard_upstream and dashboard_upstream.strip())
    has_web = bool(dashboard_web_upstream and dashboard_web_upstream.strip())

    handles: list[str] = []
    if has_modal and (has_web or apex_cli_only):
        normalized_modal = normalize_dashboard_upstream(dashboard_upstream, base_domain=clean)
        cli_decl = f"\t@sandbox_dashboard_cli {{\n\t\thost {clean}\n\t\tpath /launch /snapshot /health /api/codex/profiles\n\t}}\n"
        handles.append(_format_proxy_handle("sandbox_dashboard_cli", cli_decl, normalized_modal, preserve_host=True))
        if has_web:
            normalized_web = normalize_dashboard_web_upstream(dashboard_web_upstream, base_domain=clean)
            handles.append(_format_proxy_handle("sandbox_dashboard", f"\t@sandbox_dashboard host {clean}\n", normalized_web))
    elif has_web:
        normalized_web = normalize_dashboard_web_upstream(dashboard_web_upstream, base_domain=clean)
        handles.append(_format_proxy_handle("sandbox_dashboard", f"\t@sandbox_dashboard host {clean}\n", normalized_web))
    elif has_modal:
        normalized = normalize_dashboard_upstream(dashboard_upstream, base_domain=clean)
        handles.append(_format_proxy_handle("sandbox_dashboard", f"\t@sandbox_dashboard host {clean}\n", normalized, preserve_host=True))

    return (
        "# Managed by modal-sandbox infra caddy (wildcard ingress)\n"
        f"{clean}, *.{clean} {{\n"
        "\ttls {\n"
        "\t\tdns cloudflare {env.CLOUDFLARE_DNS_API_TOKEN}\n"
        "\t}\n"
        "\timport /etc/caddy/apps/*.caddy\n"
        f"{''.join(handles)}"
        "\thandle {\n"
        '\t\trespond "Not Found" 404\n'
        "\t}\n"
        "}\n"
    )
