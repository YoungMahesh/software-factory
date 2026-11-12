#!/usr/bin/env python3
"""Pull decrypted environment secrets from the Central Environment Store (env-store).

Retrieves and decrypts target repository secrets from github.com/${GH_ORG_NAME}/env-store
to a local workstation .env file as defined in ADR 0065.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.env_store import DEFAULT_VAULT_REPO, fetch_vault_env_raw, resolve_gh_token
from scripts.push_repo_env import detect_repo_name


def pull_repo_env(
    repo_name: str | None = None,
    org_name: str | None = None,
    dest_file: Path | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    optional: bool = False,
) -> bool:
    """Pulls and decrypts environment secrets from env-store into a local destination file."""
    cwd = Path.cwd()
    detected_org, detected_name = detect_repo_name(cwd)
    final_repo = repo_name or detected_name
    final_org = org_name or detected_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    final_dest = dest_file or (cwd / ".env")

    token = resolve_gh_token(gh_token)
    if not token:
        if optional:
            print("ℹ️ GitHub token not found. Skipping optional env-store pull.", file=sys.stderr)
            return False
        print(
            "❌ GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass --token.",
            file=sys.stderr,
        )
        return False

    if not final_org:
        if optional:
            print("ℹ️ GitHub organization not found. Skipping optional env-store pull.", file=sys.stderr)
            return False
        print(
            "❌ GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.",
            file=sys.stderr,
        )
        return False

    try:
        raw_env = fetch_vault_env_raw(
            repo_name=final_repo,
            org_name=final_org,
            gh_token=token,
            age_key=age_key,
            env_repo_name=vault_repo,
        )
    except Exception as e:
        if optional:
            print(f"ℹ️ Could not decrypt secrets from env-store for repository '{final_repo}': {e}", file=sys.stderr)
            return False
        raise

    if raw_env is None:
        if optional:
            print(f"ℹ️ No secrets found for repository '{final_repo}' in env-store ({vault_repo}).", file=sys.stderr)
        return False

    final_dest.parent.mkdir(parents=True, exist_ok=True)
    if raw_env and not raw_env.endswith("\n"):
        raw_env += "\n"
    final_dest.write_text(raw_env, encoding="utf-8")
    final_dest.chmod(0o600)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull decrypted .env secrets from env-store vault.")
    parser.add_argument("-r", "--repo", help="Target repository name (defaults to git remote origin).")
    parser.add_argument("-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME).")
    parser.add_argument("-t", "--token", help="GitHub Personal Access Token (defaults to GH_TOKEN / GITHUB_TOKEN / gh auth token).")
    parser.add_argument("-k", "--key", help="Age private key (defaults to AGE_PRIVATE_KEY / SOPS_AGE_KEY).")
    parser.add_argument("-d", "--dest", type=Path, default=Path(".env"), help="Path to destination .env file.")
    parser.add_argument(
        "--optional",
        "--ignore-missing",
        dest="optional",
        action="store_true",
        help="Do not exit with error if secrets are missing or decryption keys are unavailable.",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    _, detected_name = detect_repo_name(cwd)
    target_repo = args.repo or detected_name

    success = pull_repo_env(
        repo_name=args.repo,
        org_name=args.org,
        dest_file=args.dest,
        gh_token=args.token,
        age_key=args.key,
        optional=args.optional,
    )
    if success:
        print(f"✅ Successfully pulled and decrypted secrets into {args.dest.resolve()} (mode 0600).")
        sys.exit(0)
    elif args.optional:
        sys.exit(0)
    else:
        print(
            f"❌ Could not find or decrypt secrets for repository '{target_repo}' in env-store.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
