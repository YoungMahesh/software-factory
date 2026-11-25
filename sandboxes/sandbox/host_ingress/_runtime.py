"""Prepare the canonical Compose build context for every ingress bootstrap path."""

from pathlib import Path
import os
from typing import Sequence

from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.infra_deploy import VpsSshConfig, find_resource_plane_source_dir

from ._apply import IngressResult, apply_configuration


def prepare_runtime(
    vps_config: VpsSshConfig,
    *,
    source_dir: Path | None = None,
    files: dict[str, str] | None = None,
    delete: Sequence[str] = (),
    prune: bool = False,
    bootstrap: bool = False,
    email: str | None = None,
    cf_dns_token: str | None = None,
    require_cloudflare: bool = False,
    caddy_dir: str = "/opt/caddy",
    container_name: str = "caddy",
    network: str = "dbhost-network",
    timeout: int = 360,
) -> IngressResult:
    source = source_dir or find_resource_plane_source_dir() / "caddy"
    desired = {
        name: (source / name).read_text(encoding="utf-8")
        for name in ("Dockerfile", "docker-compose.yml")
    }
    desired.update(files or {})
    default_files = []
    if "conf/Caddyfile" not in desired:
        desired["conf/Caddyfile"] = (source / "conf" / "Caddyfile").read_text(encoding="utf-8")
        default_files.append("conf/Caddyfile")
    if email and email.strip():
        desired["conf/Caddyfile"] = f"{{\n\temail {email.strip()}\n}}\n\nimport /etc/caddy/sites/*.caddy\n"
        default_files = []
    if require_cloudflare:
        root = resolve_factory_root()
        dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
        token = (
            cf_dns_token
            or os.environ.get("CLOUDFLARE_DNS_API_TOKEN")
            or dotenv.get("CLOUDFLARE_DNS_API_TOKEN")
            or os.environ.get("CLOUDFLARE_API_TOKEN")
            or dotenv.get("CLOUDFLARE_API_TOKEN")
        )
        if token and token.strip():
            if any(character in token for character in ("\n", "\r")):
                raise ValueError("Cloudflare DNS token must be a single line.")
            desired[".env"] = f"CLOUDFLARE_DNS_API_TOKEN={token.strip()}\n"
    return apply_configuration(
        vps_config, desired, defaults=default_files, delete=delete, prune=prune,
        bootstrap=bootstrap,
        require_cloudflare=require_cloudflare, require_sites_import=require_cloudflare,
        caddy_dir=caddy_dir,
        container_name=container_name, network=network, timeout=timeout,
    )
