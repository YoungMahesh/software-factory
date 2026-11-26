"""Central Config Store persistence: GitHub contents, versions and failure semantics."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_CONFIG_REPO = "config"
GITHUB_TIMEOUT_SECONDS = 20


class ConfigStoreError(RuntimeError):
    """A failed repository operation; absence is represented separately."""


class ConfigStoreHTTPError(ConfigStoreError):
    def __init__(self, status: int, body: Any, location: str):
        self.status = status
        self.body = body
        message = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
        super().__init__(f"Central Config Store operation failed for '{location}' (HTTP {status}): {message}")

    @property
    def creation_collision(self) -> bool:
        message = str(self.body).lower()
        return self.status == 409 or (self.status == 422 and (
            "already exists" in message or ("sha" in message and "supplied" in message)
        ))


def github_json_request(url: str, token: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, Any]:
    """HTTP adapter. Every request is authenticated, bounded and asks for fresh content."""
    headers = {
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "software-factory-config-store", "Cache-Control": "no-cache, max-age=0",
        "Pragma": "no-cache",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"message": raw[:500]}
        return error.code, body
    except (OSError, ValueError) as error:
        # Never turn connectivity or decoding failures into "missing file".
        raise ConfigStoreError(f"Central Config Store request failed: {type(error).__name__}") from error


@dataclass(frozen=True)
class StoredFile:
    path: str
    content: bytes
    sha: str
    html_url: str | None = None


@dataclass(frozen=True)
class StoredCommit:
    path: str
    sha: str
    commit_sha: str
    html_url: str | None = None
    size: int = 0


class CentralConfigStore:
    """Repository-scoped persistence with explicit create/update/delete preconditions.

    The injected request adapter is the sole external seam. Domain modules keep
    plaintext/encryption, naming and filtering policies. Writes are never retried
    automatically: a stale SHA or ambiguous network failure requires caller intent.
    """

    def __init__(self, owner: str, token: str, repo: str = DEFAULT_CONFIG_REPO, *, request: Callable | None = None):
        self.owner, self.repo, self.token = owner, repo, token
        self._request = request or github_json_request
        self._base = f"https://api.github.com/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"

    def _contents_url(self, path: str) -> str:
        if path and (PurePosixPath(path).is_absolute() or "\\" in path or "\0" in path
                     or any(part in ("", ".", "..") for part in path.split("/"))):
            raise ValueError(f"Invalid Central Config Store path: {path!r}")
        return f"{self._base}/contents/{urllib.parse.quote(path, safe='/')}"

    def _call(self, url: str, *, method: str = "GET", payload: dict | None = None, accepted=(200,)):
        status, body = self._request(url, self.token, method=method, payload=payload)
        if status not in accepted:
            raise ConfigStoreHTTPError(status, body, url.removeprefix("https://api.github.com/repos/"))
        return status, body

    def _file_metadata(self, path: str) -> dict | None:
        status, body = self._call(self._contents_url(path), accepted=(200, 404))
        if status == 404:
            return None
        if not isinstance(body, dict):
            raise ConfigStoreError(f"Expected file metadata for '{path}'")
        return body

    def read(self, path: str) -> StoredFile | None:
        body = self._file_metadata(path)
        if body is None:
            return None
        if body.get("encoding", "base64") != "base64" or not isinstance(body.get("content"), str):
            raise ConfigStoreError(f"Expected base64 file content for '{path}'")
        try:
            # GitHub wraps base64 in newlines; reject invalid content rather than
            # silently decoding garbage into an empty or incomplete secret file.
            encoded = "".join(body["content"].split()).encode("ascii")
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ConfigStoreError(f"Malformed base64 file content for '{path}'") from error
        return StoredFile(str(body.get("path") or path), content, str(body.get("sha") or ""), body.get("html_url"))

    def list_directory(self, path: str) -> list[dict]:
        status, body = self._call(self._contents_url(path), accepted=(200, 404))
        if status == 404:
            return []
        if not isinstance(body, list) or not all(isinstance(item, dict) for item in body):
            raise ConfigStoreError(f"Expected directory entries for '{path}'")
        return body

    def list_tree(self) -> list[dict]:
        status, body = self._call(f"{self._base}/git/trees/HEAD?recursive=1", accepted=(200, 404, 409))
        if status == 404 or (status == 409 and isinstance(body, dict) and "empty" in str(body.get("message", "")).lower()):
            return []
        if status == 409:
            raise ConfigStoreHTTPError(status, body, self._base)
        if (not isinstance(body, dict) or not isinstance(body.get("tree"), list) or body.get("truncated")
                or not all(isinstance(entry, dict) for entry in body["tree"])):
            raise ConfigStoreError("Central Config Store tree was malformed or incomplete")
        return body["tree"]

    def write(self, path: str, content: bytes, message: str, *, expected_sha: str | None = None) -> StoredCommit:
        """None means create-only; an explicit SHA means conditional replacement."""
        if not path:
            raise ValueError("A file path is required")
        payload = {"message": message, "content": base64.b64encode(content).decode("ascii")}
        if expected_sha is not None:
            payload["sha"] = expected_sha
        _, body = self._call(self._contents_url(path), method="PUT", payload=payload, accepted=(200, 201))
        if not isinstance(body, dict):
            raise ConfigStoreError(f"Malformed commit response for '{path}'")
        file = body.get("content") or {}
        commit = body.get("commit") or {}
        if (not isinstance(file, dict) or not isinstance(commit, dict)
                or not (file.get("sha") or commit.get("sha"))):
            raise ConfigStoreError(f"Malformed commit response for '{path}'")
        return StoredCommit(str(file.get("path") or path), str(file.get("sha") or ""),
                            str(commit.get("sha") or ""), file.get("html_url"), int(file.get("size") or len(content)))

    def upsert(self, path: str, content: bytes, message: str) -> StoredCommit:
        """Discover the current version once and conditionally write; conflicts propagate."""
        current = self._file_metadata(path)
        if current is not None and not current.get("sha"):
            raise ConfigStoreError(f"Missing file version for '{path}'")
        return self.write(path, content, message, expected_sha=current["sha"] if current else None)

    def delete(self, path: str, expected_sha: str, message: str) -> None:
        if not path or not expected_sha:
            raise ValueError("Deletion requires a file path and expected SHA")
        self._call(self._contents_url(path), method="DELETE", payload={"message": message, "sha": expected_sha})

    def ensure_private_repository(self, *, create_if_missing: bool = False) -> None:
        status, _ = self._call(self._base, accepted=(200, 404))
        if status == 200:
            return
        if not create_if_missing:
            raise FileNotFoundError(f"Repository '{self.owner}/{self.repo}' does not exist yet.")
        _, owner = self._call(f"https://api.github.com/users/{urllib.parse.quote(self.owner, safe='')}")
        if not isinstance(owner, dict):
            raise ConfigStoreError("Malformed GitHub owner metadata")
        url = (f"https://api.github.com/orgs/{urllib.parse.quote(self.owner, safe='')}/repos"
               if owner.get("type") == "Organization" else "https://api.github.com/user/repos")
        self._call(url, method="POST", payload={
            "name": self.repo, "private": True, "auto_init": True,
            "description": "Private Central Config Store (env/, caddy/, scratchpad/) for Software Factory",
        }, accepted=(200, 201))
