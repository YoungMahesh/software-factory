"""Client and core domain logic for db-host PostgreSQL provisioning.

Integrates with the db-host control plane MCP server (JSON-RPC over HTTP)
and handles project resolution, TLS root CA certificate caching, and connection
URI construction with sslrootcert.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from sandbox import db_host_client as _client_mod
from sandbox.db_host_client import (
    DEFAULT_CA_FILENAME,
    DEFAULT_CONFIG_DIR,
    DEFAULT_PORT,
    DbHostClient,
    DbHostConfig,
    call_mcp_tool,
    download_ca_cert,
    get_or_download_ca_cert,
    normalize_base_url,
    resolve_db_host_config,
    resolve_project_name,
    update_env_file,
)


def ensure_project(
    base_url: str,
    admin_token: str,
    project_name: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Ensures a project exists in db-host, routing tool calls through module call_mcp_tool."""
    return _client_mod.ensure_project(
        base_url=base_url,
        admin_token=admin_token,
        project_name=project_name,
        client=client,
        call_tool_fn=call_mcp_tool,
    )


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


def create_database_connection(
    database_name: str,
    project_name: str | None = None,
    domain: str | None = None,
    token: str | None = None,
    if_not_exists: bool = True,
    custom_ca_path: Path | None = None,
    client: httpx.Client | None = None,
    db_host_client: DbHostClient | None = None,
) -> DatabaseConnectionInfo:
    """High-level orchestration: ensures project, creates/resolves DB, caches CA, and builds URI."""
    db_client = db_host_client or DbHostClient(
        domain=domain,
        token=token,
        http_client=client,
    )
    resolved_proj_name = resolve_project_name(project_name)

    # 1. Download or locate root CA certificate
    ca_path = get_or_download_ca_cert(db_client.base_url, dest_path=custom_ca_path, client=db_client.http_client)

    # 2. Ensure project exists
    project = ensure_project(
        base_url=db_client.base_url,
        admin_token=db_client.admin_token,
        project_name=resolved_proj_name,
        client=db_client.http_client,
    )
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError(f"Could not resolve project ID for project '{resolved_proj_name}'.")

    # 3. Provision or resolve existing database
    clean_db_name = database_name.strip()
    already_existed = False

    try:
        call_mcp_tool(
            base_url=db_client.base_url,
            admin_token=db_client.admin_token,
            tool_name="create_database",
            arguments={
                "projectId": project_id,
                "databaseName": clean_db_name,
            },
            client=db_client.http_client,
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
        base_url=db_client.base_url,
        admin_token=db_client.admin_token,
        tool_name="get_database_credentials",
        arguments={
            "databaseName": clean_db_name,
            "projectId": project_id,
        },
        client=db_client.http_client,
    )

    db_user = creds.get("username", "")
    db_pass = creds.get("password", "")
    db_name = creds.get("name", clean_db_name)
    host = creds.get("host") or db_client.domain

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
