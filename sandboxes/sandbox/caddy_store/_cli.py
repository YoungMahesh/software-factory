"""CLI subcommand and deploy-flag integration for Central Config Store (caddy/)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Sequence

from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.infra_deploy import VpsSshConfig, resolve_vps_ssh_config

from ._sync import backup_caddy_to_store, restore_caddy_from_store
from ._vps import DEFAULT_CADDY_DIR


def _build_store_subparser(subcmd: str) -> argparse.ArgumentParser:
    """Builds parser for `modal-sandbox infra caddy backup|restore`."""
    desc = (
        "Capture /opt/caddy configuration from VPS into Central Config Store (config under caddy/<profile>/)."
        if subcmd == "backup"
        else "Restore /opt/caddy configuration from Central Config Store (config under caddy/<profile>/) onto VPS."
    )
    parser = argparse.ArgumentParser(prog=f"modal-sandbox infra caddy {subcmd}", description=desc)
    parser.add_argument("--profile", default=None, help="Logical VPS profile folder under caddy/ in config repo (defaults to CADDY_STORE_PROFILE or 'default').")
    parser.add_argument("-o", "--org", default=None, help="GitHub organization owning config repo (defaults to GH_ORG_NAME).")
    parser.add_argument("-t", "--token", default=None, help="GitHub token (defaults to GH_TOKEN / GITHUB_TOKEN / gh auth token).")
    parser.add_argument("--dir", type=Path, default=None, help="Optional local directory to write a copy for inspection.")
    parser.add_argument("--from-dir", type=Path, default=None, help="Optional local directory to read instead of VPS (backup) or config repo (restore).")
    if subcmd == "restore":
        parser.add_argument("--prune", action="store_true", help="Remove extra files under /opt/caddy/conf/ not in config repo caddy/<profile>/ (never removes Caddyfile).")
        parser.add_argument("--bootstrap", action="store_true", help=f"Provision {DEFAULT_CADDY_DIR} on a fresh VPS before restoring.")
    parser.add_argument("--host", help="VPS SSH host (defaults to RESOURCE_PLANE_SSH_HOST env var).")
    parser.add_argument("--user", help="VPS SSH user (defaults to RESOURCE_PLANE_SSH_USER env var or 'root').")
    parser.add_argument("--port", type=int, help="VPS SSH port (defaults to RESOURCE_PLANE_SSH_PORT env var or 22).")
    parser.add_argument("--key", help="Path to private SSH key file (required or RESOURCE_PLANE_SSH_KEY env var).")
    return parser


def run_caddy_store_subcommand(subcmd: str, argv: Sequence[str]) -> int:
    """CLI handler for `modal-sandbox infra caddy backup|restore`."""
    parser = _build_store_subparser(subcmd)
    args = parser.parse_args(argv)
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    try:
        vps_config = (
            None
            if (subcmd == "backup" and args.from_dir is not None)
            else resolve_vps_ssh_config(
                host=args.host, user=args.user, port=args.port, key_path=args.key, dotenv=dotenv
            )
        )
        if subcmd == "backup":
            res = backup_caddy_to_store(
                vps_config,
                profile=args.profile,
                org_name=args.org,
                gh_token=args.token,
                dir_out=args.dir,
                from_dir=args.from_dir,
            )
        else:
            assert vps_config is not None
            res = restore_caddy_from_store(
                vps_config,
                profile=args.profile,
                org_name=args.org,
                gh_token=args.token,
                prune=args.prune,
                bootstrap=args.bootstrap,
                dir_out=args.dir,
                from_dir=args.from_dir,
            )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if res.success:
        print(f"✓ {res.message}")
        return 0
    print(f"❌ {res.message}", file=sys.stderr)
    return 1


def maybe_sync_after_deploy(vps_config: VpsSshConfig, profile: str | None) -> int:
    """Runs post-deploy backup to caddy-store and prints result."""
    try:
        res = backup_caddy_to_store(vps_config, profile=profile)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    if res.success:
        print(f"✓ {res.message}")
        return 0
    print(f"❌ {res.message}", file=sys.stderr)
    return 1


def run_bootstrap_from_store(
    vps_config: VpsSshConfig,
    *,
    profile: str | None,
    domain: str | None,
    upstream: str,
    s3_domain: str | None,
    s3_upstream: str,
    sync: bool,
    caddy_cfg: Any,
) -> int:
    """Handles `modal-sandbox infra caddy --bootstrap --from-store` flow."""
    from sandbox.caddy_deploy import setup_reverse_proxy

    try:
        res = restore_caddy_from_store(vps_config, profile=profile, bootstrap=True)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    if not res.success:
        print(f"❌ {res.message}", file=sys.stderr)
        return 1
    print(f"✓ {res.message}")

    if domain and domain.strip():
        ok, msg = setup_reverse_proxy(
            vps_config=vps_config,
            domain=domain.strip(),
            upstream=upstream,
            s3_domain=s3_domain.strip() if s3_domain else None,
            s3_upstream=s3_upstream,
            bootstrap=False,
            caddy_config=caddy_cfg,
        )
        if not ok:
            print(f"❌ {msg}", file=sys.stderr)
            return 1
        print(f"✓ {msg}")

    return maybe_sync_after_deploy(vps_config, profile) if sync else 0
