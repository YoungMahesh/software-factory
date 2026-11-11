#!/usr/bin/env python3
"""Pull decrypted environment secrets from the Central Environment Store (env-store).

Retrieves and decrypts target repository secrets from github.com/${GH_ORG_NAME}/env-store
to a local workstation .env file as defined in ADR 0096.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from sandbox.env_store import DEFAULT_VAULT_REPO, fetch_vault_env
from scripts.push_repo_env import detect_repo_name


def pull_repo_env(
    repo_name: str | None = None,
    org_name: str | None = None,
    dest_file: Path | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
) -> bool:
    """Pulls and decrypts environment secrets from env-store into a local destination file."""
    cwd = Path.cwd()
    detected_org, detected_name = detect_repo_name(cwd)
    final_repo = repo_name or detected_name
    final_org = org_name or detected_org or os.environ.get("GH_ORG_NAME")
    final_dest = dest_file or (cwd / ".env")

    env_dict = fetch_vault_env(
        repo_name=final_repo,
        org_name=final_org,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=vault_repo,
    )

    if not env_dict:
        return False

    final_dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}\n" for k, v in env_dict.items()]
    final_dest.write_text("".join(lines), encoding="utf-8")
    final_dest.chmod(0o600)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull decrypted .env secrets from env-store vault.")
    parser.add_argument("-r", "--repo", help="Target repository name (defaults to git remote origin).")
    parser.add_argument("-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME).")
    parser.add_argument("-d", "--dest", type=Path, default=Path(".env"), help="Path to destination .env file.")
    args = parser.parse_args()

    success = pull_repo_env(repo_name=args.repo, org_name=args.org, dest_file=args.dest)
    if success:
        print(f"✅ Successfully pulled and decrypted secrets into {args.dest.resolve()} (mode 0600).")
        sys.exit(0)
    else:
        print(f"❌ Could not find or decrypt secrets for repository '{args.repo or 'current'}' in env-store.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
