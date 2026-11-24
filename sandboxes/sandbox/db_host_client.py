"""Client and core transport logic for db-host control plane interaction.

Integrates with the db-host control plane MCP server (JSON-RPC 2.0 over HTTP)
and handles project resolution, TLS root CA certificate caching, and .env
synchronization behind a unified client seam.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

import httpx

from sandbox.env_store import detect_repo_name


DEFAULT_CONFIG_DIR = (
    Path.home() / ".config" / "resource-plane"
    if (Path.home() / ".config" / "resource-plane").exists()
    else Path.home() / ".config" / "db-host"
)
DEFAULT_CA_FILENAME = "ca.crt"
DEFAULT_PORT = 54320


@dataclass
class DbHostConfig:
    """Configuration required to connect to Resource Plane (formerly db-host)."""
    domain: str
    admin_token: str
    base_url: str


ResourcePlaneConfig = DbHostConfig


def normalize_base_url(domain_or_url: str) -> str:
    """Normalizes domain or URL to https://<host> scheme."""
    cleaned = domain_or_url.strip()
    if not cleaned:
        raise ValueError("Domain or base URL cannot be empty.")
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        parsed = urllib.parse.urlparse(cleaned)
        scheme = parsed.scheme
        netloc = parsed.netloc or parsed.path
        return f"{scheme}://{netloc}".rstrip("/")
    return f"https://{cleaned}".rstrip("/")


def resolve_db_host_config(
    domain: str | None = None,
    token: str | None = None,
) -> DbHostConfig:
    """Resolves Resource Plane domain and authentication token from args or environment."""
    resolved_domain = (
        domain
        or os.environ.get("RESOURCE_PLANE_DOMAIN")
        or os.environ.get("RESOURCE_PLANE_URL")
        or os.environ.get("DB_HOST_DOMAIN")
        or os.environ.get("DB_HOST_URL")
    )
    if not resolved_domain or not resolved_domain.strip():
        raise ValueError(
            "Missing db-host domain (or Resource Plane domain). Set RESOURCE_PLANE_DOMAIN or DB_HOST_DOMAIN in .env or provide --domain."
        )

    resolved_token = (
        token
        or os.environ.get("RESOURCE_PLANE_ADMIN_TOKEN")
        or os.environ.get("RESOURCE_PLANE_TOKEN")
        or os.environ.get("DB_HOST_ADMIN_TOKEN")
        or os.environ.get("DB_HOST_TOKEN")
    )
    if not resolved_token or not resolved_token.strip():
        raise ValueError(
            "Missing db-host admin token (or Resource Plane token). Set RESOURCE_PLANE_ADMIN_TOKEN or DB_HOST_ADMIN_TOKEN in .env or provide --token."
        )

    base_url = normalize_base_url(resolved_domain)
    clean_domain = urllib.parse.urlparse(base_url).netloc

    return DbHostConfig(
        domain=clean_domain,
        admin_token=resolved_token.strip(),
        base_url=base_url,
    )


def download_ca_cert(
    base_url: str,
    dest_path: Path | None = None,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
) -> Path:
    """Downloads root CA certificate from db-host /api/ca.crt and caches it locally."""
    target_path = dest_path or (DEFAULT_CONFIG_DIR / DEFAULT_CA_FILENAME)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    ca_url = f"{base_url.rstrip('/')}/api/ca.crt"

    if client is not None:
        resp = client.get(ca_url)
        resp.raise_for_status()
        content = resp.text
    else:
        with httpx.Client(timeout=timeout, verify=True) as temp_client:
            resp = temp_client.get(ca_url)
            resp.raise_for_status()
            content = resp.text

    if not content or "BEGIN CERTIFICATE" not in content:
        raise ValueError(f"Endpoint {ca_url} did not return a valid PEM certificate.")

    target_path.write_text(content, encoding="utf-8")
    return target_path.resolve()


def get_or_download_ca_cert(
    base_url: str,
    dest_path: Path | None = None,
    client: httpx.Client | None = None,
) -> Path:
    """Retrieves existing cached CA cert or downloads it if missing."""
    target_path = dest_path or (DEFAULT_CONFIG_DIR / DEFAULT_CA_FILENAME)
    if target_path.is_file() and target_path.stat().st_size > 0:
        return target_path.resolve()
    return download_ca_cert(base_url, dest_path=target_path, client=client)


def call_mcp_tool(
    base_url: str,
    admin_token: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> Any:
    """Invokes an MCP tool on db-host via JSON-RPC 2.0 over HTTP."""
    mcp_endpoint = f"{base_url.rstrip('/')}/api/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }

    if client is not None:
        resp = client.post(mcp_endpoint, json=payload, headers=headers)
    else:
        with httpx.Client(timeout=timeout) as temp_client:
            resp = temp_client.post(mcp_endpoint, json=payload, headers=headers)

    resp.raise_for_status()
    body = resp.json()

    if "error" in body:
        err = body["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"MCP tool '{tool_name}' failed: {msg}")

    result = body.get("result", {})
    if result.get("isError"):
        content_items = result.get("content", [])
        err_msg = content_items[0].get("text", "Unknown MCP tool execution error") if content_items else "Tool execution error"
        raise RuntimeError(f"MCP tool '{tool_name}' returned error: {err_msg}")

    content_items = result.get("content", [])
    if not content_items:
        return {}

    raw_text = content_items[0].get("text", "")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text


def resolve_project_name(
    custom_project: str | None = None,
    cwd: Path | None = None,
) -> str:
    """Determines project name from explicit argument, git repository name, or default."""
    if custom_project and custom_project.strip():
        return custom_project.strip()

    _, repo_name = detect_repo_name(cwd or Path.cwd())
    if repo_name and repo_name.strip() and repo_name != ".":
        return repo_name.strip()

    return "default"


def ensure_project(
    base_url: str,
    admin_token: str,
    project_name: str,
    client: httpx.Client | None = None,
    call_tool_fn: Any = None,
) -> dict[str, Any]:
    """Ensures a project exists in db-host, creating it via MCP if missing."""
    fn = call_tool_fn or call_mcp_tool
    projects_list = fn(
        base_url=base_url,
        admin_token=admin_token,
        tool_name="list_projects",
        arguments={},
        client=client,
    )

    clean_name = project_name.strip()
    clean_slug = clean_name.lower().replace(" ", "-")

    if isinstance(projects_list, list):
        for p in projects_list:
            if isinstance(p, dict):
                if p.get("name") == clean_name or p.get("slug") == clean_slug or p.get("id") == clean_name:
                    return p

    created = fn(
        base_url=base_url,
        admin_token=admin_token,
        tool_name="create_project",
        arguments={"name": clean_name},
        client=client,
    )
    return created


def update_env_file(env_file_path: Path | str, key: str, value: str) -> bool:
    """Injects or updates an environment variable in a .env file."""
    env_file = Path(env_file_path)
    new_line = f'{key}="{value}"\n'

    if not env_file.exists():
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(new_line, encoding="utf-8")
        return True

    content = env_file.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(key)}\s*=.*$")
    replaced = False
    new_lines: list[str] = []

    for line in lines:
        if pattern.match(line):
            new_lines.append(new_line)
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(new_line)

    env_file.write_text("".join(new_lines), encoding="utf-8")
    return True


class DbHostClient:
    """Deep client encapsulating db-host control plane JSON-RPC transport and project scoping."""

    def __init__(
        self,
        config: DbHostConfig | None = None,
        domain: str | None = None,
        token: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ):
        if config is not None:
            self.config = config
        else:
            self.config = resolve_db_host_config(domain=domain, token=token)
        self.http_client = http_client
        self.timeout = timeout

    @classmethod
    def from_env(
        cls,
        domain: str | None = None,
        token: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> DbHostClient:
        """Instantiates a DbHostClient from explicit arguments or environment variables."""
        return cls(domain=domain, token=token, http_client=http_client)

    @property
    def base_url(self) -> str:
        return self.config.base_url

    @property
    def admin_token(self) -> str:
        return self.config.admin_token

    @property
    def domain(self) -> str:
        return self.config.domain

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float | None = None,
    ) -> Any:
        """Invokes an MCP tool on db-host via JSON-RPC 2.0 over HTTP."""
        return call_mcp_tool(
            base_url=self.base_url,
            admin_token=self.admin_token,
            tool_name=tool_name,
            arguments=arguments,
            timeout=timeout or self.timeout,
            client=self.http_client,
        )

    def ensure_project(self, project_name: str) -> dict[str, Any]:
        """Ensures a project exists on db-host, creating it via MCP if missing."""
        return ensure_project(
            base_url=self.base_url,
            admin_token=self.admin_token,
            project_name=project_name,
            client=self.http_client,
        )

    def get_or_download_ca_cert(self, dest_path: Path | None = None) -> Path:
        """Retrieves existing cached CA cert or downloads it if missing."""
        return get_or_download_ca_cert(
            base_url=self.base_url,
            dest_path=dest_path,
            client=self.http_client,
        )

    def download_ca_cert(
        self,
        dest_path: Path | None = None,
        timeout: float = 15.0,
    ) -> Path:
        """Downloads root CA certificate from db-host /api/ca.crt."""
        return download_ca_cert(
            base_url=self.base_url,
            dest_path=dest_path,
            timeout=timeout,
            client=self.http_client,
        )

    def update_env_file(self, env_file_path: Path | str, key: str, value: str) -> bool:
        """Updates or injects an environment variable in a .env file."""
        return update_env_file(env_file_path, key, value)


# Canonical domain aliases for Resource Plane
ResourcePlaneClient = DbHostClient
resolve_resource_plane_config = resolve_db_host_config
