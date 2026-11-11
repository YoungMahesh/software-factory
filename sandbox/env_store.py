"""Central Environment Store vault resolver module.

Retrieves and decrypts target repository secrets from the private
github.com/${GH_ORG_NAME}/env-store vault host-side for injection
into Modal sandboxes as defined in ADR 0096.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

DEFAULT_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"
DEFAULT_VAULT_REPO = "env-store"


def parse_env_text(raw_text: str) -> dict[str, str]:
    """Parses .env string content into a dictionary of key-value pairs."""
    env_dict: dict[str, str] = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            env_dict[key] = val
    return env_dict


def fetch_github_file(owner: str, repo: str, path: str, token: str) -> str | None:
    """Fetches a file from GitHub repository using the Contents REST API.

    Returns the decoded plaintext/ciphertext content, or None if not found (404).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "software-factory-env-store",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "content" in data:
                content_b64 = data["content"]
                return base64.b64decode(content_b64).decode("utf-8")
            return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None


def decrypt_sops_payload(ciphertext: str, age_private_key: str | None = None) -> str:
    """Decrypts a SOPS-encrypted payload string returning plaintext."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    env = os.environ.copy()
    if age_private_key:
        env["SOPS_AGE_KEY"] = age_private_key.strip()
    elif "SOPS_AGE_KEY" not in env and DEFAULT_KEY_FILE.is_file():
        env["SOPS_AGE_KEY_FILE"] = str(DEFAULT_KEY_FILE)

    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp:
        tmp.write(ciphertext)
        tmp_path = Path(tmp.name)

    try:
        res = subprocess.run(
            ["sops", "decrypt", str(tmp_path)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"SOPS decryption failed: {res.stderr.strip()}")
        return res.stdout
    finally:
        if tmp_path.is_file():
            tmp_path.unlink()


def fetch_vault_env(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, str] | None:
    """Fetches and decrypts environment variables for a target repository from env-store.

    Returns the decrypted dictionary, or None if not found in the vault.
    """
    clean_repo = repo_name.strip().rstrip("/")
    bare_repo = clean_repo.split("/", 1)[1] if "/" in clean_repo else clean_repo
    resolved_org = org_name or os.environ.get("GH_ORG_NAME")
    resolved_token = gh_token or os.environ.get("GH_TOKEN")
    resolved_age_key = age_key or os.environ.get("AGE_PRIVATE_KEY")

    if not resolved_org or not resolved_token:
        return None

    file_path = f"{bare_repo}/default.env"
    ciphertext = fetch_github_file(resolved_org, env_repo_name, file_path, token=resolved_token)
    if not ciphertext:
        return None

    plaintext = decrypt_sops_payload(ciphertext, age_private_key=resolved_age_key)
    return parse_env_text(plaintext)
