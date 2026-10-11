#!/usr/bin/env python3
"""Sync Target Repository Skills and Architectural Decision Records.

Backfills Matt Pocock engineering skills (.agents/skills/), domain glossary (CONTEXT.md),
docs/agents/, and baseline ADRs (docs/adr/0001-tanstack-start-spa-architecture.md)
across existing target repositories in the organization.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.ui.github import DEFAULT_TEST_ORG, fetch_test_org_repos, get_test_org_token
from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill skills and ADR structures into existing target repositories."
    )
    parser.add_argument(
        "--repo",
        type=str,
        help="Specific repository name to sync (e.g. 'test2').",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all repositories in the organization.",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=DEFAULT_TEST_ORG,
        help=f"GitHub organization (default: {DEFAULT_TEST_ORG}).",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Target Git branch to commit scaffolding to (default: main).",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub personal access token (defaults to ephemerally decrypted organization credentials for the test organization).",
    )
    return parser.parse_args(argv)


def sync_repos(
    repos: list[str],
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    branch: str = "main",
) -> int:
    auth_token = token or get_test_org_token()
    if not auth_token:
        print(f"[ERROR] Failed to resolve organization credentials for {org}.", file=sys.stderr)
        return 1

    success_count = 0
    failure_count = 0

    print(f"Syncing engineering skills and ADRs for {len(repos)} repository(s) in {org}...")

    for repo in repos:
        try:
            print(f" -> Syncing {org}/{repo} (branch: {branch})...")
            result = scaffold_target_repo(
                repo_name=repo,
                token=auth_token,
                org=org,
                branch=branch,
                repo_root=PROJECT_ROOT,
            )
            sha = result.get("commit_sha", "unknown")[:7]
            count = result.get("files_count", 0)
            print(f" [OK] {repo}: successfully scaffolded {count} files (commit {sha}).")
            success_count += 1
        except Exception as e:
            print(f" [FAILED] {repo}: {e}", file=sys.stderr)
            failure_count += 1

    print(f"\nSync summary: {success_count} succeeded, {failure_count} failed.")
    return 0 if failure_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    auth_token = args.token or get_test_org_token()
    if not auth_token:
        print(f"[ERROR] Organization credentials for {args.org} not found.", file=sys.stderr)
        return 1

    if args.repo:
        target_repos = [args.repo.strip()]
    elif args.all:
        target_repos = fetch_test_org_repos(token=auth_token, org=args.org)
    else:
        print("[ERROR] Please specify either --repo <name> or --all.", file=sys.stderr)
        return 2

    return sync_repos(target_repos, token=auth_token, org=args.org, branch=args.branch)


if __name__ == "__main__":
    sys.exit(main())
