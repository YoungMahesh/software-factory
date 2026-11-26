"""GitHub REST API persistence helpers for Central Config Store (caddy/)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from sandbox.config_store import CentralConfigStore, ConfigStoreError, DEFAULT_CONFIG_REPO

CANONICAL_CONFIG_REPO = DEFAULT_CONFIG_REPO
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


def ensure_caddy_store_repo(owner: str, token: str, create_if_missing: bool = False) -> None:
    """Ensure the canonical repository exists before backing up ingress files."""
    CentralConfigStore(owner, token).ensure_private_repository(create_if_missing=create_if_missing)


def list_caddy_store_profile_blobs(owner: str, profile: str, token: str) -> dict[str, str]:
    """Lists {rel_path: blob_sha} under caddy/<profile>/ in Central Config Store."""
    entries = CentralConfigStore(owner, token).list_tree()
    prefix = f"{CADDY_STORE_PREFIX}/{profile}/"
    blobs: dict[str, str] = {}
    for entry in entries:
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
    store = CentralConfigStore(owner, token)
    for rel in sorted(blobs):
        file = store.read(f"{CADDY_STORE_PREFIX}/{profile}/{rel}")
        if file is None:
            raise ConfigStoreError("Host Ingress Proxy backup changed while reading; retry the operation.")
        files[rel] = file.content.decode("utf-8")
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
    CentralConfigStore(owner, token).write(path, content_bytes, commit_message, expected_sha=sha)


def delete_caddy_store_file(
    owner: str,
    path: str,
    sha: str,
    token: str,
    commit_message: str,
) -> None:
    """Deletes a file from caddy-store via GitHub Contents API."""
    CentralConfigStore(owner, token).delete(path, sha, commit_message)
