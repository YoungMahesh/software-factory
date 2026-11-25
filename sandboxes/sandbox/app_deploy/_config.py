"""Configuration, target resolution, domain naming, and env synthesis for deploy-app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import urllib.parse

from sandbox.caddy_wildcard import (
    normalize_base_domain,
    sanitize_app_slug,
    validate_subdomain_label,
)

GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$")


@dataclass
class AppDeployRequest:
    """Options controlling host-only deployment of a Hosted App to the VPS."""

    target: str | None = None
    repo: str | None = None
    branch: str = "main"
    subdomain: str | None = None
    base_domain: str | None = None
    cf_dns_token: str | None = None
    skip_migrate: bool = False
    sync_caddy_store: bool = False
    profile: str | None = None
    host: str | None = None
    user: str | None = None
    port: int | None = None
    key_path: str | Path | None = None
    remote_base_dir: str = "/root"


@dataclass
class AppDeployResult:
    """Summary returned after deploying a Hosted App to the VPS."""

    repo_name: str
    app_slug: str
    remote_dir: str
    domain: str
    url: str
    container_name: str
    source_mode: str
    migrated: bool


@dataclass
class AppTeardownResult:
    """Summary returned after tearing down a Hosted App from the VPS."""

    repo_name: str
    app_slug: str
    remote_dir: str
    purged: bool
    message: str


@dataclass
class DeployTarget:
    """Resolved local or GitHub repository deployment target."""

    source_mode: str  # "local" or "github"
    bare_repo: str
    app_slug: str
    org_name: str | None = None
    local_dir: Path | None = None

    def __post_init__(self) -> None:
        for label, value in (("repository", self.bare_repo), ("owner", self.org_name)):
            if value is not None and (
                not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in {".", ".."}
            ):
                raise ValueError(f"Invalid Hosted App {label}: {value!r}")

    def remote_directory(self, base_dir: str) -> str:
        base = PurePosixPath(base_dir)
        if not base.is_absolute() or ".." in base.parts or any(char in base_dir for char in ("'", "\n", "\r", "\0")):
            raise ValueError("Hosted App remote base directory must be an absolute, unambiguous path.")
        return (base / self.bare_repo).as_posix()


def parse_git_github_repo(project_dir: Path) -> tuple[str, str] | None:
    """Extracts (owner, repo_name) from git remote origin if it points to GitHub."""
    if not (project_dir / ".git").exists():
        return None
    res = subprocess.run(
        ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    match = GITHUB_REMOTE_RE.search(res.stdout.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _is_factory_checkout(path: Path) -> bool:
    return (path / "GLOSSARY.md").is_file() and (path / "sandboxes").is_dir() and (path / "app-template").is_dir()


def _parse_repo_spec(repo: str, default_org: str | None) -> tuple[str | None, str]:
    clean = repo.strip().rstrip("/")
    if "/" in clean:
        owner, bare = clean.split("/", 1)
        return owner.strip(), bare.strip()
    return (default_org.strip() if default_org else None), clean


def resolve_deploy_target(
    target: str | None = None,
    repo: str | None = None,
    *,
    cwd: Path | None = None,
    default_org: str | None = None,
) -> DeployTarget:
    """Resolves whether deployment reads a local directory or clones/pulls a GitHub repo."""
    work_dir = (cwd or Path.cwd()).resolve()

    if target and target.strip():
        raw_target = target.strip()
        cand = Path(raw_target).expanduser()
        if not cand.is_absolute():
            cand = (work_dir / cand).resolve()
        if cand.is_dir():
            if _is_factory_checkout(cand):
                raise ValueError("Refusing to deploy the software-factory monorepo itself as a Hosted App.")
            git_pair = parse_git_github_repo(cand)
            if repo:
                org, bare = _parse_repo_spec(repo, default_org or (git_pair[0] if git_pair else None))
            elif git_pair:
                org, bare = git_pair
            else:
                org, bare = default_org, cand.name
            return DeployTarget(
                source_mode="local",
                bare_repo=bare,
                app_slug=sanitize_app_slug(bare),
                org_name=org,
                local_dir=cand,
            )

        if raw_target.startswith((".", "/", "~")):
            raise FileNotFoundError(f"Target project directory not found: {cand}")

        org, bare = _parse_repo_spec(repo or raw_target, default_org)
        return DeployTarget(
            source_mode="github",
            bare_repo=bare,
            app_slug=sanitize_app_slug(bare),
            org_name=org,
        )

    if repo and repo.strip():
        org, bare = _parse_repo_spec(repo, default_org)
        return DeployTarget(
            source_mode="github",
            bare_repo=bare,
            app_slug=sanitize_app_slug(bare),
            org_name=org,
        )

    if _is_factory_checkout(work_dir):
        raise ValueError(
            "Pass a project directory or --repo <name> when running deploy-app from the software-factory root."
        )
    if not (work_dir / "docker-compose.yml").is_file() and not (work_dir / "package.json").is_file():
        raise ValueError(
            f"Current directory '{work_dir}' does not look like a scaffolded app. "
            "Pass a project path or --repo <name>."
        )
    git_pair = parse_git_github_repo(work_dir)
    org, bare = git_pair if git_pair else (default_org, work_dir.name)
    return DeployTarget(
        source_mode="local",
        bare_repo=bare,
        app_slug=sanitize_app_slug(bare),
        org_name=org,
        local_dir=work_dir,
    )


def resolve_app_domain(
    app_slug: str,
    base_domain: str,
    subdomain: str | None = None,
) -> tuple[str, str]:
    """Resolves (subdomain_label, fqdn) for a Hosted App under the App Base Domain."""
    clean_base = normalize_base_domain(base_domain)
    if subdomain and subdomain.strip():
        raw_sub = subdomain.strip().lower()
        suffix = f".{clean_base}"
        if raw_sub.endswith(suffix):
            raw_sub = raw_sub[: -len(suffix)]
        label = validate_subdomain_label(raw_sub)
    else:
        label = validate_subdomain_label(sanitize_app_slug(app_slug))
    return label, f"{label}.{clean_base}"


def rewrite_sslrootcert(database_url: str, cert_path: str = "/app/.certs/ca.crt") -> str:
    """Normalizes sslrootcert in DATABASE_URL so containerized apps resolve staged certs."""
    raw = database_url.strip()
    if not raw or "ssl" not in raw.lower():
        return raw
    try:
        parsed = urllib.parse.urlsplit(raw)
        params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return raw

    has_cert = any(k == "sslrootcert" for k, _ in params)
    has_verify = any(k == "sslmode" and v == "verify-full" for k, v in params)
    if not has_cert and not has_verify:
        return raw

    updated_params: list[tuple[str, str]] = []
    replaced = False
    for k, v in params:
        if k == "sslrootcert":
            updated_params.append((k, cert_path))
            replaced = True
        else:
            updated_params.append((k, v))
    if not replaced:
        updated_params.append(("sslrootcert", cert_path))

    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(updated_params), parsed.fragment)
    )


def build_remote_app_env(
    base_env: dict[str, str],
    *,
    fqdn: str,
    container_name: str,
) -> dict[str, str]:
    """Produces production runtime/build env vars for the remote Hosted App."""
    merged = dict(base_env)
    app_url = f"https://{fqdn}"
    merged["NODE_ENV"] = "production"
    merged["NEXT_PUBLIC_APP_URL"] = app_url
    merged["EXPO_PUBLIC_API_URL"] = app_url
    merged["APP_CONTAINER_NAME"] = container_name
    merged["RESOURCE_PLANE_CA_CERT"] = "/app/.certs/ca.crt"
    if merged.get("DATABASE_URL"):
        merged["DATABASE_URL"] = rewrite_sslrootcert(merged["DATABASE_URL"])
    return merged


def serialize_dotenv(env_dict: dict[str, str]) -> str:
    """Serializes environment mappings cleanly into UTF-8 .env text."""
    lines: list[str] = []
    for key, val in env_dict.items():
        if val == "" or any(ch in val for ch in (" ", "\t", "\n", "#", "'", '"', "$")):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={val}")
    return "\n".join(lines) + ("\n" if lines else "")
