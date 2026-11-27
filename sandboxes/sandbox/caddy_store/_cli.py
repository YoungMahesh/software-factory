"""CLI subcommand and deploy-flag integration for Central Config Store (caddy/)."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

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
    if subcmd == "restore":
        parser.add_argument("--prune", action="store_true", help="Remove extra files under /opt/caddy/conf/ not in config repo caddy/<profile>/ (never removes Caddyfile).")
        parser.add_argument("--bootstrap", action="store_true", help=f"Provision {DEFAULT_CADDY_DIR} on a fresh VPS before restoring.")
    return parser


def run_caddy_store_subcommand(subcmd: str, argv: Sequence[str]) -> int:
    """CLI handler for `modal-sandbox infra caddy backup|restore`."""
    parser = _build_store_subparser(subcmd)
    args = parser.parse_args(argv)
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    try:
        vps_config = resolve_vps_ssh_config(dotenv=dotenv)
        if subcmd == "backup":
            res = backup_caddy_to_store(vps_config, profile=args.profile)
        else:
            res = restore_caddy_from_store(
                vps_config,
                profile=args.profile,
                prune=args.prune,
                bootstrap=args.bootstrap,
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
