"""Client and core domain logic for db-host PostgreSQL provisioning.

Integrates with the db-host control plane MCP server (JSON-RPC over HTTP)
and handles project resolution, TLS root CA certificate caching, and connection
URI construction with sslrootcert.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import urllib.parse
from typing import Any
import urllib.request
import urllib.error

import httpx

from sandbox.env_store import detect_repo_name


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "db-host"
DEFAULT_CA_FILENAME = "ca.crt"
DEFAULT_PORT = 54320


@dataclass
class DbHostConfig:
    """Configuration required to connect to db-host."""
    domain: str
    admin_token: str
    base_url: str


@dataclass
class DatabaseConnectionInfo:
    """Connection details and credentials for a provisioned PostgreSQL database."""
    name: str
    username: str
    password: str
    host: str
    port: int
    connection_string: str
    ca_cert_path: Path
    project_name: str
    project_id: str
    already_existed: bool

    def as_dict(self) -> dict[str, Any]:
        """Returns connection information as a dictionary."""
        return {
            "name": self.name,
            "username": self.username,
            "password": self.password,
            "host": self.host,
            "port": self.port,
            "connection_string": self.connection_string,
            "ca_cert_path": str(self.ca_cert_path),
            "project_name": self.project_name,
            "project_id": self.project_id,
            "already_existed": self.already_existed,
        }


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
    """Resolves db-host domain and authentication token from args or environment."""
    resolved_domain = (
        domain
        or os.environ.get("DB_HOST_DOMAIN")
        or os.environ.get("DB_HOST_URL")
    )
    if not resolved_domain or not resolved_domain.strip():
        raise ValueError(
            "Missing db-host domain. Set DB_HOST_DOMAIN in .env or provide --domain."
        )

    resolved_token = (
        token
        or os.environ.get("DB_HOST_ADMIN_TOKEN")
        or os.environ.get("DB_HOST_TOKEN")
    )
    if not resolved_token or not resolved_token.strip():
        raise ValueError(
            "Missing db-host admin token. Set DB_HOST_ADMIN_TOKEN in .env or provide --token."
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
) -> Path:
    """Downloads root CA certificate from db-host /api/ca.crt and caches it locally."""
    target_path = dest_path or (DEFAULT_CONFIG_DIR / DEFAULT_CA_FILENAME)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    ca_url = f"{base_url.rstrip('/')}/api/ca.crt"

    with httpx.Client(timeout=timeout, verify=True) as client:
        resp = client.get(ca_url)
        resp.raise_for_status()
        content = resp.text

    if not content or "BEGIN CERTIFICATE" not in content:
        raise ValueError(f"Endpoint {ca_url} did not return a valid PEM certificate.")

    target_path.write_text(content, encoding="utf-8")
    return target_path.resolve()


def get_or_download_ca_cert(
    base_url: str,
    dest_path: Path | None = None,
) -> Path:
    """Retrieves existing cached CA cert or downloads it if missing."""
    target_path = dest_path or (DEFAULT_CONFIG_DIR / DEFAULT_CA_FILENAME)
    if target_path.is_file() and target_path.stat().st_size > 0:
        return target_path.resolve()
    return download_ca_cert(base_url, dest_path=target_path)


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
) -> dict[str, Any]:
    """Ensures a project exists in db-host, creating it via MCP if missing."""
    projects_list = call_mcp_tool(
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

    created = call_mcp_tool(
        base_url=base_url,
        admin_token=admin_token,
        tool_name="create_project",
        arguments={"name": clean_name},
        client=client,
    )
    return created


def create_database_connection(
    database_name: str,
    project_name: str | None = None,
    domain: str | None = None,
    token: str | None = None,
    if_not_exists: bool = True,
    custom_ca_path: Path | None = None,
    client: httpx.Client | None = None,
) -> DatabaseConnectionInfo:
    """High-level orchestration: ensures project, creates/resolves DB, caches CA, and builds URI."""
    config = resolve_db_host_config(domain=domain, token=token)
    resolved_proj_name = resolve_project_name(project_name)

    # 1. Download or locate root CA certificate
    ca_path = get_or_download_ca_cert(config.base_url, dest_path=custom_ca_path)

    # 2. Ensure project exists
    project = ensure_project(
        base_url=config.base_url,
        admin_token=config.admin_token,
        project_name=resolved_proj_name,
        client=client,
    )
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError(f"Could not resolve project ID for project '{resolved_proj_name}'.")

    # 3. Provision or resolve existing database
    clean_db_name = database_name.strip()
    already_existed = False

    try:
        call_mcp_tool(
            base_url=config.base_url,
            admin_token=config.admin_token,
            tool_name="create_database",
            arguments={
                "projectId": project_id,
                "databaseName": clean_db_name,
            },
            client=client,
        )
    except RuntimeError as err:
        err_msg = str(err)
        if "already exists" in err_msg.lower():
            if not if_not_exists:
                raise
            already_existed = True
        else:
            raise

    # 4. Fetch full database credentials
    creds = call_mcp_tool(
        base_url=config.base_url,
        admin_token=config.admin_token,
        tool_name="get_database_credentials",
        arguments={
            "databaseName": clean_db_name,
            "projectId": project_id,
        },
        client=client,
    )

    db_user = creds.get("username", "")
    db_pass = creds.get("password", "")
    db_name = creds.get("name", clean_db_name)
    host = creds.get("host") or config.domain

    # Determine port: prefer 54320 for external TLS proxy if returned or default
    raw_conn = creds.get("connectionString", "")
    if f":{DEFAULT_PORT}" in raw_conn:
        port = DEFAULT_PORT
    elif creds.get("port") and creds.get("port") != 5432:
        port = int(creds["port"])
    else:
        port = DEFAULT_PORT

    # Construct final connection URI with absolute sslrootcert path
    conn_uri = f"postgresql://{db_user}:{db_pass}@{host}:{port}/{db_name}?sslmode=verify-full&sslrootcert={ca_path}"

    return DatabaseConnectionInfo(
        name=db_name,
        username=db_user,
        password=db_pass,
        host=host,
        port=port,
        connection_string=conn_uri,
        ca_cert_path=ca_path,
        project_name=resolved_proj_name,
        project_id=project_id,
        already_existed=already_existed,
    )


def update_env_file(env_file_path: Path, key: str, value: str) -> bool:
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
