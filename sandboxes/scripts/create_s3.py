#!/usr/bin/env python3
"""CLI utility to provision and resolve S3 object storage buckets on db-host.

Provisions a SeaweedFS S3 bucket under an auto-detected or specified project
on db-host, retrieves IAM access credentials, and optionally outputs or injects
standard AWS SDK environment variables into the local project .env file.
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

from sandbox.s3_host import (
    S3BucketInfo,
    create_s3_bucket,
    write_s3_env_vars,
)


def create_parser() -> argparse.ArgumentParser:
    """Builds argument parser for create-s3 CLI."""
    parser = argparse.ArgumentParser(
        prog="create-s3",
        description="Provision a new S3 object storage bucket and credentials on db-host.",
    )
    parser.add_argument(
        "name",
        metavar="BUCKET_NAME",
        help="Name of the S3 bucket to provision or resolve (3-63 lowercase alphanumeric/hyphen chars).",
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
        help="Inject or update standard AWS SDK environment variables in the local .env file.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        metavar="PATH",
        help="Path to .env file when --write-env is enabled (default: .env).",
    )
    parser.add_argument(
        "--prefix",
        default="",
        metavar="PREFIX",
        help="Prefix prepended to environment variable names (e.g. 'UPLOADS_').",
    )
    parser.add_argument(
        "--push-vault",
        action="store_true",
        help="Automatically encrypt and push updated .env to Central Config Store (config).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw bucket credentials and code snippets as JSON.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Output only the canonical S3 URI (s3://<bucket-name>).",
    )
    parser.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Fail if the bucket already exists instead of returning existing credentials.",
    )
    return parser


def format_text_output(
    info: S3BucketInfo,
    written_env: list[str] | None = None,
    env_path: Path | None = None,
) -> str:
    """Formats bucket details nicely for terminal display."""
    status_str = "Reused existing S3 bucket" if info.already_existed else "Created new S3 bucket"
    status_icon = "🔄" if info.already_existed else "✨"

    lines = [
        f"{status_icon} {status_str}: {info.bucket_name}",
        f"   • Project:         {info.project_name} (ID: {info.project_id})",
        f"   • S3 URI:          {info.s3_uri}",
        f"   • Endpoint:        {info.endpoint}",
        f"   • Region:          {info.region}",
        f"   • Access Key ID:   {info.access_key_id}",
        "",
        "💻 Quick Test (AWS CLI):",
        f"   aws s3 ls {info.s3_uri} --endpoint-url {info.endpoint}",
    ]

    if written_env and env_path:
        lines.append("")
        lines.append(f"📝 Injected into {env_path}:")
        for key in written_env:
            lines.append(f"   • {key}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for create-s3."""
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        info = create_s3_bucket(
            bucket_name=args.name,
            project_name=args.project,
            domain=args.domain,
            token=args.token,
            if_not_exists=not args.fail_if_exists,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    written_env_keys: list[str] | None = None
    env_file_path: Path | None = None

    if args.write_env:
        env_file_path = Path(args.env_file)
        written_env_keys = write_s3_env_vars(
            env_file_path=env_file_path,
            info=info,
            prefix=args.prefix,
        )

        if args.push_vault:
            print("🔐 Pushing updated secrets to Central Config Store...")
            cmd = ["push-repo-env", "-e", str(env_file_path)]
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                print("Warning: push-repo-env exited with non-zero status.", file=sys.stderr)

    if args.json:
        payload = info.as_dict()
        if args.write_env and env_file_path and written_env_keys:
            payload["env_file_updated"] = str(env_file_path)
            payload["env_vars_written"] = written_env_keys
        print(json.dumps(payload, indent=2))
    elif args.quiet:
        print(info.s3_uri)
    else:
        print(format_text_output(info, written_env=written_env_keys, env_path=env_file_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
