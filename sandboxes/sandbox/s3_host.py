"""Client and core domain logic for db-host S3 object storage provisioning.

Integrates with the db-host control plane MCP server (JSON-RPC over HTTP)
and handles project resolution, bucket name validation, SeaweedFS S3 bucket
provisioning, credential retrieval, and environment variable formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import httpx

from sandbox import db_host_client as _client_mod
from sandbox.db_host_client import (
    DbHostClient,
    call_mcp_tool,
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


_BUCKET_NAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


@dataclass
class S3BucketInfo:
    """Connection details and credentials for a provisioned S3 object storage bucket."""
    id: str
    bucket_name: str
    project_name: str
    project_id: str
    access_key_id: str
    secret_access_key: str
    endpoint: str
    region: str
    already_existed: bool
    s3_uri: str
    formatted_env: str
    formatted_aws_cli: str
    formatted_node_sdk: str
    formatted_boto3: str

    def as_dict(self) -> dict[str, Any]:
        """Returns bucket details as a serializable dictionary."""
        return {
            "id": self.id,
            "bucket_name": self.bucket_name,
            "project_name": self.project_name,
            "project_id": self.project_id,
            "access_key_id": self.access_key_id,
            "secret_access_key": self.secret_access_key,
            "endpoint": self.endpoint,
            "region": self.region,
            "already_existed": self.already_existed,
            "s3_uri": self.s3_uri,
            "formatted": {
                "env": self.formatted_env,
                "awsCli": self.formatted_aws_cli,
                "nodeSdk": self.formatted_node_sdk,
                "boto3": self.formatted_boto3,
            },
        }


def validate_bucket_name(bucket_name: str) -> str:
    """Validates an S3 bucket name against standard naming conventions.

    Bucket names must:
    - Be between 3 and 63 characters long
    - Consist only of lowercase letters, numbers, and hyphens
    - Start and end with a lowercase letter or number
    """
    clean_name = bucket_name.strip()
    if not clean_name:
        raise ValueError("Bucket name cannot be empty.")

    if len(clean_name) < 3 or len(clean_name) > 63:
        raise ValueError(
            f"Invalid bucket name '{clean_name}': must be between 3 and 63 characters long."
        )

    if not _BUCKET_NAME_REGEX.match(clean_name):
        raise ValueError(
            f"Invalid bucket name '{clean_name}': must start and end with a lowercase letter "
            "or number and contain only lowercase letters, numbers, and hyphens."
        )

    return clean_name


def generate_boto3_snippet(
    endpoint: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    bucket_name: str,
) -> str:
    """Generates turnkey Python boto3 client initialization and sample code."""
    return (
        "import boto3\n\n"
        "s3 = boto3.client(\n"
        "    's3',\n"
        f"    endpoint_url='{endpoint}',\n"
        f"    region_name='{region}',\n"
        f"    aws_access_key_id='{access_key_id}',\n"
        f"    aws_secret_access_key='{secret_access_key}',\n"
        ")\n\n"
        f"# Example: list objects in bucket\n"
        f"response = s3.list_objects_v2(Bucket='{bucket_name}')\n"
        "for obj in response.get('Contents', []):\n"
        "    print(obj['Key'])\n"
    )


def write_s3_env_vars(
    env_file_path: Path,
    info: S3BucketInfo,
    prefix: str = "",
) -> list[str]:
    """Injects standard AWS SDK environment variables into a .env file."""
    clean_prefix = prefix.strip()
    key_map = {
        f"{clean_prefix}AWS_ACCESS_KEY_ID": info.access_key_id,
        f"{clean_prefix}AWS_SECRET_ACCESS_KEY": info.secret_access_key,
        f"{clean_prefix}AWS_ENDPOINT_URL_S3": info.endpoint,
        f"{clean_prefix}AWS_REGION": info.region,
        f"{clean_prefix}S3_BUCKET_NAME": info.bucket_name,
    }

    updated_keys: list[str] = []
    for key, value in key_map.items():
        update_env_file(env_file_path, key, value)
        updated_keys.append(key)

    return updated_keys


def create_s3_bucket(
    bucket_name: str,
    project_name: str | None = None,
    domain: str | None = None,
    token: str | None = None,
    if_not_exists: bool = True,
    client: httpx.Client | None = None,
    db_host_client: DbHostClient | None = None,
) -> S3BucketInfo:
    """High-level orchestration: validates name, ensures project, creates/resolves bucket, and retrieves credentials."""
    clean_bucket_name = validate_bucket_name(bucket_name)
    db_client = db_host_client or DbHostClient(
        domain=domain,
        token=token,
        http_client=client,
    )
    resolved_proj_name = resolve_project_name(project_name)

    # 1. Ensure target project exists
    project = ensure_project(
        base_url=db_client.base_url,
        admin_token=db_client.admin_token,
        project_name=resolved_proj_name,
        client=db_client.http_client,
    )
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError(f"Could not resolve project ID for project '{resolved_proj_name}'.")

    # 2. Provision or resolve existing S3 bucket
    already_existed = False
    try:
        call_mcp_tool(
            base_url=db_client.base_url,
            admin_token=db_client.admin_token,
            tool_name="create_object_storage",
            arguments={
                "projectId": project_id,
                "bucketName": clean_bucket_name,
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

    # 3. Retrieve storage credentials
    creds = call_mcp_tool(
        base_url=db_client.base_url,
        admin_token=db_client.admin_token,
        tool_name="get_storage_credentials",
        arguments={
            "bucketName": clean_bucket_name,
            "projectId": project_id,
        },
        client=db_client.http_client,
    )

    storage_id = creds.get("id", "")
    access_key_id = creds.get("accessKeyId", "")
    secret_access_key = creds.get("secretAccessKey", "")
    endpoint = creds.get("endpoint", "")
    region = creds.get("region", "us-east-1")
    resolved_bucket_name = creds.get("bucketName", clean_bucket_name)

    formatted = creds.get("formatted", {}) if isinstance(creds.get("formatted"), dict) else {}
    formatted_env = formatted.get("env", "")
    formatted_aws_cli = formatted.get("awsCli", "")
    formatted_node_sdk = formatted.get("nodeSdk", "")

    formatted_boto3 = generate_boto3_snippet(
        endpoint=endpoint,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=region,
        bucket_name=resolved_bucket_name,
    )

    s3_uri = f"s3://{resolved_bucket_name}"

    return S3BucketInfo(
        id=storage_id,
        bucket_name=resolved_bucket_name,
        project_name=resolved_proj_name,
        project_id=project_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        endpoint=endpoint,
        region=region,
        already_existed=already_existed,
        s3_uri=s3_uri,
        formatted_env=formatted_env,
        formatted_aws_cli=formatted_aws_cli,
        formatted_node_sdk=formatted_node_sdk,
        formatted_boto3=formatted_boto3,
    )
