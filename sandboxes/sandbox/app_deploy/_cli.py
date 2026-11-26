"""CLI entrypoint for deploying and tearing down Hosted Apps on the Resource Plane VPS."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ._config import AppDeployRequest
from ._deploy import deploy_app, teardown_app


def build_deploy_app_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for deploy-app / modal-sandbox deploy-app."""
    parser = argparse.ArgumentParser(
        prog="deploy-app",
        description="Deploy a Hosted App to /root/<repo-name> on the Resource Plane VPS with wildcard HTTPS.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Local project path, repo name, or 'down' subcommand (defaults to current directory).",
    )
    parser.add_argument(
        "extra_target",
        nargs="?",
        default=None,
        help="Optional app name/path when using 'deploy-app down <target>'.",
    )
    parser.add_argument("--repo", default=None, help="GitHub repository (<repo> or <owner>/<repo>) to deploy from GitHub + env-store.")
    parser.add_argument("-b", "--branch", default="main", help="Git branch to pull in --repo mode (default: main).")
    parser.add_argument("--subdomain", default=None, help="Override subdomain label under APPS_BASE_DOMAIN.")
    parser.add_argument("--base-domain", default=None, help="Override APPS_BASE_DOMAIN (e.g. apps.example.com).")
    parser.add_argument("--cf-dns-token", default=None, help="Cloudflare DNS-01 token if wildcard Caddy setup is needed.")
    parser.add_argument("--skip-migrate", action="store_true", help="Skip automatic Drizzle database migration on deploy.")
    parser.add_argument("--down", action="store_true", help="Stop containers and remove the Caddy route for the app.")
    parser.add_argument("--purge", action="store_true", help="With down/--down, also remove /root/<repo-name> on the VPS.")
    parser.add_argument("--sync", action="store_true", help="Back up /opt/caddy to caddy-store after updating routes.")
    parser.add_argument("--profile", default=None, help="Logical VPS profile folder in caddy-store.")
    parser.add_argument("--host", default=None, help="VPS SSH host (defaults to RESOURCE_PLANE_SSH_HOST).")
    parser.add_argument("--user", default=None, help="VPS SSH user (defaults to RESOURCE_PLANE_SSH_USER or 'root').")
    parser.add_argument("--port", type=int, default=None, help="VPS SSH port (defaults to RESOURCE_PLANE_SSH_PORT or 22).")
    parser.add_argument("--key", default=None, help="Path to private SSH key (defaults to RESOURCE_PLANE_SSH_KEY).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Runs deploy-app or teardown from CLI arguments."""
    arg_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_deploy_app_parser()
    args = parser.parse_args(arg_list)

    is_down = bool(args.down)
    target = args.target
    if args.target == "down":
        is_down = True
        target = args.extra_target
    elif args.extra_target is not None:
        parser.error(f"Unexpected argument: {args.extra_target}")

    if args.purge and not is_down:
        parser.error("--purge can only be used with down / --down.")

    req = AppDeployRequest(
        target=target,
        repo=args.repo,
        branch=args.branch,
        subdomain=args.subdomain,
        base_domain=args.base_domain,
        cf_dns_token=args.cf_dns_token,
        skip_migrate=args.skip_migrate,
        sync_caddy_store=args.sync,
        profile=args.profile,
        host=args.host,
        user=args.user,
        port=args.port,
        key_path=args.key,
    )

    try:
        if is_down:
            res = teardown_app(req, purge=args.purge)
            print(f"✓ {res.message}")
            return 0

        res = deploy_app(req)
        print(f"\n✅ Hosted App '{res.repo_name}' is live!")
        print(f"   URL:       {res.url}")
        print(f"   VPS Path:  {res.remote_dir}")
        print(f"   Container: {res.container_name}")
        if res.migrated:
            print("   Database:  Migrations applied")
        return 0
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
