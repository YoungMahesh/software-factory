#!/usr/bin/env python3
"""Push local project environment secrets to the Central Environment Store (env-store).

Encrypts a project's .env using the organization's public Age recipient key and
commits it directly to github.com/${GH_ORG_NAME}/env-store via GitHub REST API
as defined in ADR 0057 and ADR 0066.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.env_store import (
    DEFAULT_AGE_RECIPIENT,
    DEFAULT_KEY_FILE,
    DEFAULT_VAULT_REPO,
    PushFileOutcome,
    PushResult,
    commit_to_env_store,
    detect_repo_name,
    ensure_gitignore,
    fetch_github_file,
    push_repo_env as _push_repo_env,
    push_repo_git_identity as _push_repo_git_identity,
    resolve_gh_token,
    run_sops_encrypt,
    update_env_map_content,
)


def push_repo_env(
    repo_dir: Path,
    env_file: Path | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    dest_name: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    allow_binary: bool = False,
    push_all: bool = False,
    **kwargs: Any,
) -> PushResult:
    kwargs.setdefault("encrypt_fn", run_sops_encrypt)
    kwargs.setdefault("commit_fn", commit_to_env_store)
    kwargs.setdefault("fetch_fn", fetch_github_file)
    return _push_repo_env(
        repo_dir=repo_dir,
        env_file=env_file,
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        recipient=recipient,
        dest_name=dest_name,
        vault_repo=vault_repo,
        allow_binary=allow_binary,
        push_all=push_all,
        **kwargs,
    )


def push_repo_git_identity(
    repo_dir: Path,
    name: str | None = None,
    email: str | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    **kwargs: Any,
) -> PushResult:
    kwargs.setdefault("encrypt_fn", run_sops_encrypt)
    kwargs.setdefault("commit_fn", commit_to_env_store)
    return _push_repo_git_identity(
        repo_dir=repo_dir,
        name=name,
        email=email,
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        recipient=recipient,
        vault_repo=vault_repo,
        **kwargs,
    )


def main() -> None:
    # If first argument is 'git', dispatch to git sub-command parser
    is_git_subcommand = len(sys.argv) > 1 and sys.argv[1] == "git"

    if is_git_subcommand:
        git_parser = argparse.ArgumentParser(
            description="Push repository Git authorship (git.env) to env-store vault."
        )
        git_parser.add_argument("subcommand", choices=["git"])
        git_parser.add_argument("--name", help="Git author name (GIT_AUTHOR_NAME).")
        git_parser.add_argument("--email", help="Git author email (GIT_AUTHOR_EMAIL).")
        git_parser.add_argument(
            "-r", "--repo", help="Target repository name (defaults to git remote origin)."
        )
        git_parser.add_argument(
            "-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME)."
        )
        git_parser.add_argument("-t", "--token", help="GitHub Personal Access Token.")
        git_parser.add_argument(
            "--recipient",
            default=DEFAULT_AGE_RECIPIENT,
            help="Age public key recipient for encryption.",
        )
        args = git_parser.parse_args()

        cwd = Path.cwd()
        res = push_repo_git_identity(
            repo_dir=cwd,
            name=args.name,
            email=args.email,
            repo_name=args.repo,
            org_name=args.org,
            gh_token=args.token,
            recipient=args.recipient,
        )
    else:
        parser = argparse.ArgumentParser(
            description="Push local project .env secrets to env-store vault."
        )
        parser.add_argument(
            "-r", "--repo", help="Target repository name (defaults to git remote origin)."
        )
        parser.add_argument(
            "-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME)."
        )
        parser.add_argument(
            "-t",
            "--token",
            help="GitHub Personal Access Token (defaults to GH_TOKEN / GITHUB_TOKEN / gh auth token).",
        )
        parser.add_argument(
            "-e",
            "--env",
            type=Path,
            default=None,
            help="Path to a single local source environment file to push (if omitted, checks env.map).",
        )
        parser.add_argument(
            "-d",
            "--dest",
            default=None,
            help="Destination file name in vault (for single-file push; defaults to mapped env.map name or default.env for root .env).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Push all existing local files mapped in env.map without interactive confirmation.",
        )
        parser.add_argument(
            "--recipient",
            default=DEFAULT_AGE_RECIPIENT,
            help="Age public key recipient for encryption.",
        )
        parser.add_argument(
            "--allow-binary",
            action="store_true",
            default=False,
            help="Allow encrypting destination files with unknown/binary extensions.",
        )
        args = parser.parse_args()

        if args.all and (args.env is not None or args.dest is not None):
            parser.error("--all cannot be combined with -e/--env or -d/--dest.")

        cwd = Path.cwd()
        res = push_repo_env(
            repo_dir=cwd,
            env_file=args.env,
            repo_name=args.repo,
            org_name=args.org,
            gh_token=args.token,
            recipient=args.recipient,
            dest_name=args.dest,
            allow_binary=args.allow_binary,
            push_all=args.all,
        )

    if getattr(res, "declined_all", False):
        print("ℹ️ No files selected to push.")
        sys.exit(0)
    elif res.success:
        org_display = (
            res.org_name
            or getattr(args, "org", None)
            or os.environ.get("GH_ORG_NAME")
            or "env-store"
        )
        pushed_files = getattr(res, "pushed_files", None) or []
        if len(pushed_files) > 1:
            print(f"✅ Successfully encrypted and stored {len(pushed_files)} files in {org_display}/env-store:")
            for item in pushed_files:
                print(f"   • {item.rel_path} -> {item.target_path} (SHA: {item.commit_sha})")
        else:
            print(f"✅ Successfully encrypted and stored {res.target_path} in {org_display}/env-store.")
            print(f"   Commit SHA: {res.commit_sha}")
        print("🚀 Future modal-sandbox launches will automatically inject these settings!")
        sys.exit(0)
    else:
        for item in getattr(res, "pushed_files", None) or []:
            print(f"✅ Stored {item.rel_path} -> {item.target_path} (SHA: {item.commit_sha})")
        for item in getattr(res, "failed_files", None) or []:
            print(f"❌ Failed {item.rel_path} -> {item.target_path}: {item.message}", file=sys.stderr)
        print(f"❌ Failed to push: {res.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
