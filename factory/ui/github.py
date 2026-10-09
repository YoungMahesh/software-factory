"""GitHub Discovery Client for Canonical Test Organization.

Decrypts secrets_org/software-factory-09-test/token ephemerally into memory
and inspects organization repositories and .scratch/ issue tracking trees.
"""

from collections import defaultdict
import os
from pathlib import Path
import subprocess
from typing import Any
import httpx

DEFAULT_TEST_ORG = "software-factory-09-test"
FALLBACK_REPOS = ["test1", "test2", "test3"]

_cached_token: str | None = None


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    """Resolves software-factory root directory."""
    if repo_root is not None:
        return repo_root.resolve()
    return Path(__file__).resolve().parent.parent.parent


def get_test_org_token(repo_root: Path | None = None, force_refresh: bool = False) -> str | None:
    """Ephemerally decrypts the Test Organization token into memory via host SOPS.

    Credentials are never written to disk or exposed in logs.
    """
    global _cached_token
    if _cached_token and not force_refresh:
        return _cached_token

    root = resolve_repo_root(repo_root)
    token_file = root / "secrets_org" / DEFAULT_TEST_ORG / "token"
    if not token_file.is_file():
        return None

    # Check for age key file
    age_key_path = Path.home() / ".config" / "sops" / "age" / "keys.txt"
    env = os.environ.copy()
    if age_key_path.is_file() and "SOPS_AGE_KEY_FILE" not in env:
        env["SOPS_AGE_KEY_FILE"] = str(age_key_path)

    try:
        res = subprocess.run(
            ["sops", "-d", str(token_file)],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        token = res.stdout.strip()
        if token:
            _cached_token = token
            return token
    except Exception:
        pass
    return None


def fetch_test_org_repos(
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> list[str]:
    """Fetches list of member repositories from GitHub API, falling back to known fixtures on error."""
    auth_token = token or get_test_org_token()
    if not auth_token:
        return list(FALLBACK_REPOS)

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }

    url = f"https://api.github.com/orgs/{org}/repos?per_page=100&type=all"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                repos = [r["name"] for r in resp.json() if "name" in r]
                return sorted(repos)
    except Exception:
        pass

    return list(FALLBACK_REPOS)


def fetch_repo_scratch_metadata(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Inspects the repository's Git Tree for .scratch/ feature folders and issue tickets."""
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    features_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    has_scratch = False

    if auth_token:
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SoftwareFactory-TestingConsole/1.0",
        }

        # Try main branch first, then master
        for branch in ("main", "master"):
            url = f"https://api.github.com/repos/{org}/{clean_repo}/git/trees/{branch}?recursive=1"
            try:
                with httpx.Client(timeout=timeout_secs) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        tree = resp.json().get("tree", [])
                        for item in tree:
                            path_str = item.get("path", "")
                            if not path_str.startswith(".scratch/"):
                                continue
                            has_scratch = True
                            parts = path_str.split("/")
                            if len(parts) >= 2:
                                feature_slug = parts[1]
                                if len(parts) >= 4 and parts[2] == "issues" and parts[3].endswith(".md"):
                                    issue_file = parts[3]
                                    # Extract issue number or prefix e.g. "01" from "01-name.md"
                                    issue_id = issue_file.split("-")[0]
                                    issue_slug = issue_file[:-3]  # remove .md
                                    features_map[feature_slug].append({
                                        "id": issue_id,
                                        "slug": issue_slug,
                                        "filename": issue_file,
                                    })
                        break
            except Exception:
                pass

    feature_list = []
    for slug, issues in sorted(features_map.items()):
        # Sort issues by ID
        sorted_issues = sorted(issues, key=lambda x: x["id"])
        feature_list.append({
            "slug": slug,
            "issues": sorted_issues,
        })

    return {
        "repo": clean_repo,
        "org": org,
        "has_scratch": has_scratch or bool(feature_list),
        "features": feature_list,
    }
