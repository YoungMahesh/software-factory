"""Central Environment Store vault resolver module.

Retrieves and decrypts target repository secrets from the private
github.com/${GH_ORG_NAME}/env-store vault host-side for injection
into Modal sandboxes as defined in ADR 0057 and ADR 0067.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import urllib.error
import urllib.request
import warnings

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


def serialize_env_dict(env_dict: dict[str, str]) -> str:
    """Serializes a dictionary of environment variables into a .env string.

    Safely quotes values containing spaces, tabs, newlines, '#', or quotes
    so the resulting file can be safely sourced by POSIX shells.
    """
    lines: list[str] = []
    special_chars = (" ", "\t", "\n", "#", "'", '"')
    for k, v in env_dict.items():
        if any(c in v for c in special_chars):
            if "'" not in v:
                lines.append(f"{k}='{v}'")
            elif '"' not in v:
                lines.append(f'{k}="{v}"')
            else:
                escaped = v.replace("'", "'\\''")
                lines.append(f"{k}='{escaped}'")
        else:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + ("\n" if lines else "")


def is_encrypted_sops_payload(raw_text: str) -> bool:
    """Checks if text appears to be a SOPS-encrypted file or JSON/YAML manifest."""
    indicators = ("sops:", "ENC[AES", "ENC[", '"sops":', "mac: ENC")
    return any(ind in raw_text for ind in indicators)


def parse_env_map(raw_text: str) -> list[tuple[str, str]]:
    """Parses plaintext env.map content returning a list of (src_rel, dest_rel) tuples.

    If the manifest is encrypted with SOPS, emits a warning and returns an empty list.
    """
    if is_encrypted_sops_payload(raw_text):
        warnings.warn(
            "env.map is encrypted with SOPS. env.map must be a plaintext manifest. Skipping decryption.",
            UserWarning,
            stacklevel=2,
        )
        return []

    mappings: list[tuple[str, str]] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            src, dest = line.split("=", 1)
            src = src.strip()
            dest = dest.strip().lstrip("/")
            if src and dest:
                mappings.append((src, dest))
    return mappings


def resolve_gh_token(explicit_token: str | None = None) -> str | None:
    """Resolves GitHub token from explicit arg, env (GH_TOKEN/GITHUB_TOKEN), or gh CLI."""
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()
    from_env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if from_env and from_env.strip():
        return from_env.strip()
    if shutil.which("gh"):
        try:
            res = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
    return None


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


def fetch_vault_env_raw(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
    target_filename: str = "default.env",
) -> str | None:
    """Fetches and decrypts environment file text for a target repository from env-store.

    Returns the decrypted plaintext raw string, or None if not found in the vault.
    """
    clean_repo = repo_name.strip().rstrip("/")
    bare_repo = clean_repo.split("/", 1)[1] if "/" in clean_repo else clean_repo
    resolved_org = org_name or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    resolved_token = resolve_gh_token(gh_token)
    resolved_age_key = age_key or os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")

    if not resolved_org or not resolved_token:
        return None

    file_path = f"{bare_repo}/{target_filename}"
    ciphertext = fetch_github_file(resolved_org, env_repo_name, file_path, token=resolved_token)
    if not ciphertext:
        return None

    return decrypt_sops_payload(ciphertext, age_private_key=resolved_age_key)


def fetch_vault_env(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
    target_filename: str = "default.env",
) -> dict[str, str] | None:
    """Fetches and decrypts environment variables for a target repository from env-store.

    Returns the decrypted dictionary, or None if not found in the vault.
    """
    raw_text = fetch_vault_env_raw(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
        target_filename=target_filename,
    )
    if raw_text is None:
        return None
    return parse_env_text(raw_text)


def fetch_vault_env_bundle(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, Any] | None:
    """Fetches environment bundle (mapped files + manifest) for a repository from env-store.

    Checks for env.map. If present and valid plaintext, fetches and decrypts all mapped files.
    If absent, falls back to fetching and decrypting default.env with mapping default.env=.env.
    Returns a bundle dict with 'env_map_content', 'mappings', and 'files', or None if not found.
    """
    clean_repo = repo_name.strip().rstrip("/")
    bare_repo = clean_repo.split("/", 1)[1] if "/" in clean_repo else clean_repo
    resolved_org = org_name or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    resolved_token = resolve_gh_token(gh_token)
    resolved_age_key = age_key or os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")

    if not resolved_org or not resolved_token:
        return None

    env_map_path = f"{bare_repo}/env.map"
    raw_env_map = fetch_github_file(resolved_org, env_repo_name, env_map_path, token=resolved_token)

    mappings: list[tuple[str, str]] = []
    if raw_env_map:
        mappings = parse_env_map(raw_env_map)

    files: dict[str, str] = {}

    if mappings:
        for src, dest in mappings:
            try:
                decrypted = fetch_vault_env_raw(
                    repo_name=bare_repo,
                    org_name=resolved_org,
                    gh_token=resolved_token,
                    age_key=resolved_age_key,
                    env_repo_name=env_repo_name,
                    target_filename=src,
                )
                if decrypted is not None:
                    files[src] = decrypted
                else:
                    warnings.warn(
                        f"Mapped secret file '{src}' not found in {bare_repo} env-store.",
                        UserWarning,
                        stacklevel=2,
                    )
            except Exception as e:
                warnings.warn(
                    f"Failed to decrypt mapped secret file '{src}' for {bare_repo}: {e}",
                    UserWarning,
                    stacklevel=2,
                )

        return {
            "env_map_content": raw_env_map,
            "mappings": mappings,
            "files": files,
        }

    default_env_text = fetch_vault_env_raw(
        repo_name=bare_repo,
        org_name=resolved_org,
        gh_token=resolved_token,
        age_key=resolved_age_key,
        env_repo_name=env_repo_name,
        target_filename="default.env",
    )
    if default_env_text is not None:
        return {
            "env_map_content": "default.env=.env\n",
            "mappings": [("default.env", ".env")],
            "files": {"default.env": default_env_text},
        }

    return None


def fetch_vault_git_identity(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, str] | None:
    """Fetches and decrypts repository-specific git authorship from <repo>/git.env in env-store.

    Returns a dictionary containing author keys (GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL),
    or None if git.env is not configured in the vault.
    """
    return fetch_vault_env(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
        target_filename="git.env",
    )
