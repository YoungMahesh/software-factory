#!/usr/bin/env python3
"""CLI utility to create and resolve PostgreSQL database connections on db-host.

Provisions a database under an auto-detected or specified project on db-host,
downloads and caches the root CA certificate, and outputs or injects the
connection URI with sslrootcert into the local project .env file.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Attempt to load local .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sandbox.db_host import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_CA_FILENAME,
    DatabaseConnectionInfo,
    create_database_connection,
    update_env_file,
)


def create_parser() -> argparse.ArgumentParser:
    """Builds argument parser for create-db CLI."""
    parser = argparse.ArgumentParser(
        prog="create-db",
        description="Provision a new PostgreSQL database and connection on db-host.",
    )
    parser.add_argument(
        "name",
        metavar="DATABASE_NAME",
        help="Name of the PostgreSQL database to provision or resolve.",
    )
    parser.add_argument(
        "-p",
        "--project",
        default=None,
        metavar="PROJECT",
        help="Project name on db-host (defaults to current Git repo name or 'default').",
    )
    parser.add_argument(
        "--domain",
        default=None,
        metavar="DOMAIN",
        help="db-host domain or URL (defaults to DB_HOST_DOMAIN env var).",
    )
    parser.add_argument(
        "--token",
        default=None,
        metavar="TOKEN",
        help="db-host admin authentication token (defaults to DB_HOST_ADMIN_TOKEN env var).",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Inject or update the database connection URI in the local .env file.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        metavar="PATH",
        help="Path to .env file when --write-env is enabled (default: .env).",
    )
    parser.add_argument(
        "--env-var",
        default="DATABASE_URL",
        metavar="VAR_NAME",
        help="Environment variable name for connection URI (default: DATABASE_URL).",
    )
    parser.add_argument(
        "--push-vault",
        action="store_true",
        help="Automatically encrypt and push updated .env to central env-store vault.",
    )
    parser.add_argument(
        "--ca-path",
        default=None,
        metavar="PATH",
        help=f"Custom destination path for root CA certificate (default: {DEFAULT_CONFIG_DIR / DEFAULT_CA_FILENAME}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw connection details as JSON.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Output only the PostgreSQL connection URI.",
    )
    parser.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Fail if the database already exists instead of returning existing connection.",
    )
    return parser


def format_text_output(info: DatabaseConnectionInfo, written_env: str | None = None) -> str:
    """Formats connection details nicely for terminal display."""
    status_str = "Reused existing database" if info.already_existed else "Created new database"
    status_icon = "🔄" if info.already_existed else "✨"

    lines = [
        f"{status_icon} {status_str}: {info.name}",
        f"   • Project:         {info.project_name} (ID: {info.project_id})",
        f"   • Host:            {info.host}:{info.port}",
        f"   • User:            {info.username}",
        f"   • CA Certificate:  {info.ca_cert_path}",
        "",
        "🔗 Connection URI:",
        f"   {info.connection_string}",
    ]

    if written_env:
        lines.append("")
        lines.append(f"📝 Injected into {written_env}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for create-db."""
    parser = create_parser()
    args = parser.parse_args(argv)

    custom_ca = Path(args.ca_path) if args.ca_path else None

    try:
        info = create_database_connection(
            database_name=args.name,
            project_name=args.project,
            domain=args.domain,
            token=args.token,
            if_not_exists=not args.fail_if_exists,
            custom_ca_path=custom_ca,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    written_env_msg = None
    if args.write_env:
        env_path = Path(args.env_file)
        update_env_file(env_path, args.env_var, info.connection_string)
        written_env_msg = f"{env_path} as {args.env_var}"

        if args.push_vault:
            print("🔐 Pushing updated secrets to central env-store...")
            cmd = ["push-repo-env"]
            if str(env_path) != ".env":
                cmd.extend(["-e", str(env_path), "-d", env_path.name])
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                print("Warning: push-repo-env exited with non-zero status.", file=sys.stderr)

    if args.json:
        payload = info.as_dict()
        if args.write_env:
            payload["env_file_updated"] = str(args.env_file)
            payload["env_var"] = args.env_var
        print(json.dumps(payload, indent=2))
    elif args.quiet:
        print(info.connection_string)
    else:
        print(format_text_output(info, written_env=written_env_msg))

    return 0


if __name__ == "__main__":
    sys.exit(main())
