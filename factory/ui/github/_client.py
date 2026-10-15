"""Raw GitHub REST API client, credentials decryption, and core helpers."""

import logging
import os
from pathlib import Path
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TEST_ORG = "software-factory-09-test"
FALLBACK_REPOS = ["test1", "test2", "test3"]

_cached_token: str | None = None


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    """Resolves software-factory root directory."""
    if repo_root is not None:
        return repo_root.resolve()
    return Path(__file__).resolve().parent.parent.parent.parent


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


def strip_repo_owner(repo_name: str, org: str = DEFAULT_TEST_ORG) -> str:
    """Strips org/ prefix from repository name if present."""
    clean = repo_name.strip()
    if clean.startswith(f"{org}/"):
        return clean[len(f"{org}/") :]
    return clean


def _fallback_repo_items(org: str = DEFAULT_TEST_ORG) -> list[dict[str, Any]]:
    """Generates default fallback repository items when organization credentials or API calls are unavailable."""
    return [
        {
            "name": r,
            "is_tanstack_compatible": False,
            "description": None,
            "html_url": f"https://github.com/{org}/{r}",
            "topics": [],
            "default_branch": "main",
            "private": False,
        }
        for r in sorted(FALLBACK_REPOS)
    ]
