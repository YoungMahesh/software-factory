"""GitHub REST API persistence helpers for Central Config Store (caddy/)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import urllib.error
import urllib.request

from sandbox.env_store import fetch_github_file

CANONICAL_CONFIG_REPO = "config"
CANONICAL_CADDY_STORE_REPO = CANONICAL_CONFIG_REPO
CADDY_STORE_PREFIX = "caddy"
DEFAULT_CADDY_STORE_PROFILE = "default"
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TRANSIENT_SUFFIXES = (".bak", ".tmp", ".swp", "~")
TRANSIENT_NAMES = {".gitkeep", ".DS_Store"}


def is_declarative_caddy_relpath(rel_path: str) -> bool:
    """Returns True if rel_path belongs in the Host Ingress Store bundle."""
    clean = rel_path.replace("\\", "/").lstrip("./")
    if not clean or ".." in Path(clean).parts:
        return False
    name = Path(clean).name
    if name in TRANSIENT_NAMES or any(name.endswith(sfx) for sfx in TRANSIENT_SUFFIXES):
        return False
    if clean == "docker-compose.override.yml":
        return True
    return clean.startswith("conf/") and clean != "conf/"


def git_blob_sha(content: bytes) -> str:
    """Computes Git's SHA-1 object hash for a file blob."""
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _github_request(
    url: str,
    token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Executes an authenticated GitHub REST API request returning (status, json_body)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "software-factory-caddy-store",
    }
    data: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(err_raw) if err_raw else {}
        except Exception:
            body = {"message": err_raw}
        return exc.code, body


def ensure_caddy_store_repo(owner: str, token: str, create_if_missing: bool = False) -> None:
    """Verifies ${GH_ORG_NAME}/config exists, optionally creating it as a private repo."""
    status, body = _github_request(
        f"https://api.github.com/repos/{owner}/{CANONICAL_CADDY_STORE_REPO}", token
    )
    if status == 200:
        return
    if status != 404:
        msg = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
        raise RuntimeError(f"Failed inspecting '{owner}/{CANONICAL_CADDY_STORE_REPO}': {msg}")
    if not create_if_missing:
        raise FileNotFoundError(
            f"Repository '{owner}/{CANONICAL_CADDY_STORE_REPO}' does not exist yet. "
            "Run 'modal-sandbox infra caddy backup' first or create the private repository on GitHub."
        )

    u_status, u_body = _github_request(f"https://api.github.com/users/{owner}", token)
    is_org = u_status == 200 and isinstance(u_body, dict) and u_body.get("type") == "Organization"
    create_url = (
        f"https://api.github.com/orgs/{owner}/repos"
        if is_org
        else "https://api.github.com/user/repos"
    )
    c_status, c_body = _github_request(
        create_url,
        token,
        method="POST",
        payload={
            "name": CANONICAL_CADDY_STORE_REPO,
            "private": True,
            "auto_init": True,
            "description": "Private Central Config Store (env/, caddy/, scratchpad/) for Software Factory",
        },
    )
    if c_status not in (200, 201):
        msg = c_body.get("message", f"HTTP {c_status}") if isinstance(c_body, dict) else str(c_body)
        raise RuntimeError(
            f"Could not auto-create private repository '{owner}/{CANONICAL_CADDY_STORE_REPO}': {msg}. "
            f"Create it manually with: gh repo create {owner}/{CANONICAL_CADDY_STORE_REPO} --private"
        )


def list_caddy_store_profile_blobs(owner: str, profile: str, token: str) -> dict[str, str]:
    """Lists {rel_path: blob_sha} under caddy/<profile>/ in Central Config Store."""
    status, body = _github_request(
        f"https://api.github.com/repos/{owner}/{CANONICAL_CADDY_STORE_REPO}/git/trees/HEAD?recursive=1",
        token,
    )
    if status in (404, 409):
        return {}
    if status != 200 or not isinstance(body, dict):
        msg = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
        raise RuntimeError(f"Failed listing '{owner}/{CANONICAL_CADDY_STORE_REPO}': {msg}")

    prefix = f"{CADDY_STORE_PREFIX}/{profile}/"
    blobs: dict[str, str] = {}
    for entry in body.get("tree", []):
        if entry.get("type") != "blob":
            continue
        path = str(entry.get("path", ""))
        if path.startswith(prefix):
            rel = path[len(prefix) :]
            if is_declarative_caddy_relpath(rel):
                blobs[rel] = str(entry.get("sha", ""))
    return blobs


def fetch_caddy_store_bundle(owner: str, profile: str, token: str) -> dict[str, str]:
    """Fetches all declarative files for a profile from caddy/<profile>/ in Central Config Store."""
    blobs = list_caddy_store_profile_blobs(owner, profile, token)
    files: dict[str, str] = {}
    for rel in sorted(blobs):
        content = fetch_github_file(
            owner, CANONICAL_CADDY_STORE_REPO, f"{CADDY_STORE_PREFIX}/{profile}/{rel}", token
        )
        if content is not None:
            files[rel] = content
    return files


def commit_caddy_store_file(
    owner: str,
    path: str,
    content_bytes: bytes,
    token: str,
    commit_message: str,
    sha: str | None = None,
) -> None:
    """Creates or updates a single file in Central Config Store via GitHub Contents API."""
    payload: dict[str, Any] = {
        "message": commit_message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    status, body = _github_request(
        f"https://api.github.com/repos/{owner}/{CANONICAL_CADDY_STORE_REPO}/contents/{path}",
        token,
        method="PUT",
        payload=payload,
    )
    if status not in (200, 201):
        msg = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
        raise RuntimeError(
            f"Failed committing '{path}' to '{owner}/{CANONICAL_CADDY_STORE_REPO}': {msg}"
        )


def delete_caddy_store_file(
    owner: str,
    path: str,
    sha: str,
    token: str,
    commit_message: str,
) -> None:
    """Deletes a file from caddy-store via GitHub Contents API."""
    status, body = _github_request(
        f"https://api.github.com/repos/{owner}/{CANONICAL_CADDY_STORE_REPO}/contents/{path}",
        token,
        method="DELETE",
        payload={"message": commit_message, "sha": sha},
    )
    if status != 200:
        msg = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
        raise RuntimeError(
            f"Failed deleting '{path}' from '{owner}/{CANONICAL_CADDY_STORE_REPO}': {msg}"
        )
