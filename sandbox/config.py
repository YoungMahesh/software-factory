"""Configuration constants, environment parsing, and factory credential models."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 22 * 60 * 60  # 22 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_ORG = os.environ.get("GH_ORG_NAME", "")

DEFAULT_WEB_PORT = 3000
DEFAULT_METRO_PORT = 8081
DEFAULT_T3_PORT = 3775
DEFAULT_XFCE_PORT = DEFAULT_WEB_PORT

DEFAULT_SNAPSHOT_TIMEOUT = 180
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE") or os.environ.get("TZ") or "Asia/Kolkata"


def parse_env_file(path_or_content: str | Path) -> dict[str, str]:
    """Parses environment variables from a file path or raw text content.

    Handles leading 'export ', comments ('#'), inline whitespace, and strips
    outer single or double quotes.
    """
    text: str = ""
    if isinstance(path_or_content, Path) or (
        isinstance(path_or_content, str)
        and "\n" not in path_or_content
        and Path(path_or_content).is_file()
    ):
        try:
            text = Path(path_or_content).read_text(encoding="utf-8")
        except Exception:
            return {}
    else:
        text = str(path_or_content)

    env_dict: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[6:].strip()
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            env_dict[key] = val
    return env_dict


@dataclass
class FactoryCredentials:
    gh_token: str | None = None
    gh_org_name: str | None = None
    age_private_key: str | None = None
    modal_tokens: str | None = None
    cloudflare_tunnel_token: str | None = None
    default_timezone: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


def resolve_timezone(repo_root: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Resolves timezone from environment, .env file, or default (Asia/Kolkata)."""
    parsed: dict[str, str] = {}
    if env is not None:
        parsed.update(env)
    elif repo_root:
        dotenv_path = repo_root / ".env"
        if dotenv_path.is_file():
            parsed.update(parse_env_file(dotenv_path))
    else:
        for p in (Path("/root/.env"), Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
            if p.is_file():
                parsed.update(parse_env_file(p))
                break

    return (
        parsed.get("DEFAULT_TIMEZONE")
        or parsed.get("TZ")
        or os.environ.get("DEFAULT_TIMEZONE")
        or os.environ.get("TZ")
        or DEFAULT_TIMEZONE
    )


def resolve_factory_credentials(
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    mutate_environ: bool = True,
) -> FactoryCredentials:
    """Discovers and resolves factory credentials from repo .env and host os.environ."""
    parsed: dict[str, str] = {}
    if env is not None:
        parsed.update(env)
    elif repo_root:
        dotenv_path = repo_root / ".env"
        if dotenv_path.is_file():
            parsed.update(parse_env_file(dotenv_path))

    if mutate_environ and parsed:
        for k in (
            "GH_TOKEN",
            "GH_ORG_NAME",
            "MODAL_TOKENS",
            "AGE_PRIVATE_KEY",
            "CLOUDFLARE_TUNNEL_TOKEN",
            "DEFAULT_TIMEZONE",
            "TZ",
        ):
            if k in parsed and parsed[k] and not os.environ.get(k):
                os.environ[k] = parsed[k]

    gh_token = (
        parsed.get("GH_TOKEN")
        or os.environ.get("GH_TOKEN")
        or parsed.get("GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
    )
    gh_org_name = parsed.get("GH_ORG_NAME") or os.environ.get("GH_ORG_NAME")
    age_private_key = parsed.get("AGE_PRIVATE_KEY") or os.environ.get("AGE_PRIVATE_KEY")
    modal_tokens = parsed.get("MODAL_TOKENS") or os.environ.get("MODAL_TOKENS")
    cf_token = parsed.get("CLOUDFLARE_TUNNEL_TOKEN") or os.environ.get("CLOUDFLARE_TUNNEL_TOKEN")
    tz = resolve_timezone(repo_root=repo_root, env=parsed)

    return FactoryCredentials(
        gh_token=gh_token,
        gh_org_name=gh_org_name,
        age_private_key=age_private_key,
        modal_tokens=modal_tokens,
        cloudflare_tunnel_token=cf_token,
        default_timezone=tz,
        extra_env=parsed,
    )
