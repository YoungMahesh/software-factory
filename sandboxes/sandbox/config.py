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
TEST_BASELINE_REPO = "software-factory"

DEFAULT_WEB_PORT = 3000
DEFAULT_METRO_PORT = 8081
DEFAULT_T3_PORT = 3775
DEFAULT_XFCE_PORT = DEFAULT_WEB_PORT

DEFAULT_SNAPSHOT_TIMEOUT = 180
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE") or os.environ.get("TZ") or "Asia/Kolkata"

CONTROL_PLANE_SECRET_KEYS: tuple[str, ...] = (
    "GH_TOKEN",
    "GH_ORG_NAME",
    "CLOUDFLARE_TUNNEL_TOKEN",
    "SSH_AUTHORIZED_KEY",
    "MODAL_SANDBOX_TUNNEL_DOMAIN",
    "OPENCODE_GO_API_KEY",
    "ANTIGRAVITY_CLIENT_ID",
    "ANTIGRAVITY_CLIENT_SECRET",
    "ANTIGRAVITY_TOKENS",
    "AGE_PRIVATE_KEY",
    "MODAL_TOKENS",
    "CODEX_PROFILE_VOLUME_PREFIX",
    "CODEX_STATUS_SECRET",
    "MODAL_SANDBOX_ENDPOINT_URL",
    "RESOURCE_PLANE_DOMAIN",
    "RESOURCE_PLANE_ADMIN_TOKEN",
    "RESOURCE_PLANE_SSH_HOST",
    "RESOURCE_PLANE_SSH_USER",
    "RESOURCE_PLANE_SSH_PORT",
    "RESOURCE_PLANE_SSH_PRIVATE_KEY",
    "APPS_BASE_DOMAIN",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_DNS_API_TOKEN",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_PAGES_PROJECT",
    "CLOUDFLARE_PAGES_BRANCH",
    "SANDBOX_DASHBOARD_UPSTREAM",
    "DB_HOST_DOMAIN",
    "DB_HOST_ADMIN_TOKEN",
)


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


def resolve_factory_root() -> Path:
    """Find the checkout root or the package parent in an installed runtime."""
    package_parent = Path(__file__).resolve().parent.parent
    if (package_parent.parent / "GLOSSARY.md").is_file():
        return package_parent.parent
    return package_parent


def resolve_dotenv_candidates(repo_root: Path | None = None) -> list[Path]:
    """Finds candidate .env files in standard repo locations or system paths."""
    if repo_root is not None:
        candidates = [
            repo_root / ".env",
            repo_root / ".secrets" / ".env",
            repo_root / "secrets" / ".env",
        ]
        return [p for p in candidates if p.is_file()]
    system_candidates = [
        Path("/root/.env"),
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    for p in system_candidates:
        if p.is_file() and p not in seen:
            seen.add(p)
            result.append(p)
    return result


@dataclass
class FactoryConfiguration:
    gh_token: str | None = None
    gh_org_name: str | None = None
    age_private_key: str | None = None
    modal_tokens: str | None = None
    cloudflare_tunnel_token: str | None = None
    default_timezone: str | None = None
    web_ui_username: str | None = None
    web_ui_password: str | None = None
    codex_status_secret: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass
class FactoryCredentials(FactoryConfiguration):
    """Backward-compatible credentials container."""
    pass


def resolve_timezone(repo_root: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Resolves timezone from environment, .env file, or default (Asia/Kolkata)."""
    parsed: dict[str, str] = {}
    if env is not None:
        parsed.update(env)
    elif repo_root:
        for p in resolve_dotenv_candidates(repo_root):
            parsed.update(parse_env_file(p))
            break
    else:
        for p in resolve_dotenv_candidates():
            parsed.update(parse_env_file(p))
            break

    return (
        parsed.get("DEFAULT_TIMEZONE")
        or parsed.get("TZ")
        or os.environ.get("DEFAULT_TIMEZONE")
        or os.environ.get("TZ")
        or DEFAULT_TIMEZONE
    )


def resolve_web_ui_credentials(
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    enforce: bool | None = None,
) -> dict[str, str]:
    """Resolves WEB_UI_USERNAME and WEB_UI_PASSWORD with optional enforcement."""
    import sys

    credentials: dict[str, str] = {}
    if env is not None:
        for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD"):
            if env.get(key):
                credentials[key] = env[key]
    else:
        for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD"):
            val = os.environ.get(key)
            if val:
                credentials[key] = val

        if not credentials.get("WEB_UI_USERNAME") or not credentials.get("WEB_UI_PASSWORD"):
            candidates = resolve_dotenv_candidates(repo_root)
            for env_file in candidates:
                parsed = parse_env_file(env_file)
                for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD"):
                    if key in parsed and key not in credentials:
                        credentials[key] = parsed[key]

    if enforce is None:
        is_testing = (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or any("pytest" in str(arg) for arg in sys.argv)
        )
        should_enforce = not is_testing
    else:
        should_enforce = enforce

    if not should_enforce:
        return credentials

    missing = [key for key in ("WEB_UI_USERNAME", "WEB_UI_PASSWORD") if not credentials.get(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variable(s) for Web UI deployment: {missing_str}. "
            "Please configure WEB_UI_USERNAME and WEB_UI_PASSWORD in your environment or .env file "
            "before running 'modal deploy' or 'modal serve'."
        )

    return credentials


def resolve_factory_configuration(
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    mutate_environ: bool = True,
) -> FactoryConfiguration:
    """Discovers and resolves factory configuration from repository .env and host os.environ."""
    parsed: dict[str, str] = {}
    if env is not None:
        parsed.update(env)
    elif repo_root:
        for p in resolve_dotenv_candidates(repo_root):
            for k, v in parse_env_file(p).items():
                if k not in parsed:
                    parsed[k] = v
    else:
        for p in resolve_dotenv_candidates():
            for k, v in parse_env_file(p).items():
                if k not in parsed:
                    parsed[k] = v

    if mutate_environ and parsed:
        for k in (
            "GH_TOKEN",
            "GH_ORG_NAME",
            "MODAL_TOKENS",
            "AGE_PRIVATE_KEY",
            "CLOUDFLARE_TUNNEL_TOKEN",
            "DEFAULT_TIMEZONE",
            "TZ",
            "WEB_UI_USERNAME",
            "WEB_UI_PASSWORD",
            "CODEX_STATUS_SECRET",
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
    age_private_key = (
        parsed.get("AGE_PRIVATE_KEY")
        or os.environ.get("AGE_PRIVATE_KEY")
        or parsed.get("SOPS_AGE_KEY")
        or os.environ.get("SOPS_AGE_KEY")
    )
    modal_tokens = parsed.get("MODAL_TOKENS") or os.environ.get("MODAL_TOKENS")
    cf_token = parsed.get("CLOUDFLARE_TUNNEL_TOKEN") or os.environ.get("CLOUDFLARE_TUNNEL_TOKEN")
    tz = resolve_timezone(repo_root=repo_root, env=parsed)
    web_user = parsed.get("WEB_UI_USERNAME") or os.environ.get("WEB_UI_USERNAME")
    web_pass = parsed.get("WEB_UI_PASSWORD") or os.environ.get("WEB_UI_PASSWORD")
    codex_status = parsed.get("CODEX_STATUS_SECRET") or os.environ.get("CODEX_STATUS_SECRET")

    return FactoryConfiguration(
        gh_token=gh_token,
        gh_org_name=gh_org_name,
        age_private_key=age_private_key,
        modal_tokens=modal_tokens,
        cloudflare_tunnel_token=cf_token,
        default_timezone=tz,
        web_ui_username=web_user,
        web_ui_password=web_pass,
        codex_status_secret=codex_status,
        extra_env=parsed,
    )


def resolve_factory_credentials(
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    mutate_environ: bool = True,
) -> FactoryCredentials:
    """Discovers and resolves factory credentials from repo .env and host os.environ."""
    config = resolve_factory_configuration(repo_root=repo_root, env=env, mutate_environ=mutate_environ)
    return FactoryCredentials(
        gh_token=config.gh_token,
        gh_org_name=config.gh_org_name,
        age_private_key=config.age_private_key,
        modal_tokens=config.modal_tokens,
        cloudflare_tunnel_token=config.cloudflare_tunnel_token,
        default_timezone=config.default_timezone,
        web_ui_username=config.web_ui_username,
        web_ui_password=config.web_ui_password,
        codex_status_secret=config.codex_status_secret,
        extra_env=config.extra_env,
    )


def collect_control_plane_secrets_dict(
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    provenance: dict[str, str] | None = None,
) -> dict[str, str]:
    """Collects control plane secrets from .env, credentials, provenance, and environment."""
    secrets: dict[str, str] = {}
    target_root = repo_root or Path.cwd()
    dotenv_file = target_root / ".env"
    if dotenv_file.is_file():
        secrets.update(parse_env_file(dotenv_file))

    auth_env = resolve_web_ui_credentials(repo_root=target_root, env=env)
    secrets.update(auth_env)

    if provenance is not None:
        secrets.update(provenance)
    else:
        from sandbox.provenance import resolve_host_software_factory_provenance
        secrets.update(resolve_host_software_factory_provenance(target_root))

    for key in CONTROL_PLANE_SECRET_KEYS:
        val = (env.get(key) if env is not None else None) or os.environ.get(key)
        if val and key not in secrets:
            secrets[key] = val

    if not secrets.get("RESOURCE_PLANE_SSH_PRIVATE_KEY"):
        raw_ssh_key = (
            secrets.get("RESOURCE_PLANE_SSH_KEY")
            or (env.get("RESOURCE_PLANE_SSH_KEY") if env is not None else None)
            or os.environ.get("RESOURCE_PLANE_SSH_KEY")
        )
        if raw_ssh_key and raw_ssh_key.strip():
            key_path = Path(raw_ssh_key.strip()).expanduser()
            if not key_path.is_absolute():
                key_path = (target_root / key_path).resolve()
            if key_path.is_file():
                key_text = key_path.read_text(encoding="utf-8")
                if key_text.strip():
                    secrets["RESOURCE_PLANE_SSH_PRIVATE_KEY"] = key_text

    return secrets


def compile_control_plane_secrets(
    repo_root: Path | None = None,
    extra_secrets: dict[str, str] | None = None,
) -> list[Any]:
    """Compiles discovered control plane environment secrets into a modal.Secret list."""
    import modal

    secrets_dict = collect_control_plane_secrets_dict(repo_root=repo_root)
    if extra_secrets:
        secrets_dict.update(extra_secrets)
    return [modal.Secret.from_dict(secrets_dict)]
