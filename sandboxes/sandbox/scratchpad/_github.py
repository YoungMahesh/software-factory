"""GitHub Central Config Store persistence for Scratchpad Markdown notes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from sandbox.config import resolve_factory_credentials
from sandbox.env_store import DEFAULT_CONFIG_REPO, resolve_gh_token

from ._slug import (
    FILENAME_RE,
    SCRATCHPAD_DIR,
    extract_title_from_markdown,
    normalize_note_markdown,
    resolve_unique_slug,
    title_from_filename,
    validate_note_filename,
)


@dataclass(frozen=True)
class ScratchpadNoteSummary:
    """Lightweight metadata for one note stored in config/scratchpad/."""

    filename: str
    slug: str
    path: str
    title: str
    sha: str
    size: int
    html_url: str | None = None


@dataclass(frozen=True)
class ScratchpadNoteDetail:
    """Full Markdown note retrieved from config/scratchpad/."""

    filename: str
    slug: str
    path: str
    title: str
    content: str
    sha: str
    html_url: str | None = None


@dataclass(frozen=True)
class ScratchpadSaveResult:
    """Result of committing a new Scratchpad note to config/scratchpad/."""

    filename: str
    slug: str
    path: str
    title: str
    sha: str
    content: str
    size: int = 0
    html_url: str | None = None


def resolve_config_repo_context(
    *,
    org_name: str | None = None,
    gh_token: str | None = None,
) -> tuple[str, str]:
    """Resolves (GH_ORG_NAME, GH_TOKEN) from explicit overrides, env, or factory .env."""
    creds = resolve_factory_credentials(mutate_environ=False)
    extra = creds.extra_env
    owner = (
        org_name
        or os.environ.get("GH_ORG_NAME")
        or os.environ.get("GH_ORG")
        or extra.get("GH_ORG_NAME")
        or extra.get("GH_ORG")
        or ""
    ).strip()
    token = resolve_gh_token(
        gh_token
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or extra.get("GH_TOKEN")
        or extra.get("GITHUB_TOKEN")
    )
    if not owner:
        raise ValueError("GH_ORG_NAME is not configured on the control plane.")
    if not token:
        raise ValueError("GH_TOKEN is not configured on the control plane.")
    return owner, token


def _github_json_request(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "Cache-Control": "no-cache, max-age=0",
        "Pragma": "no-cache",
        "User-Agent": "software-factory-scratchpad",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(err_raw) if err_raw else {}
        except json.JSONDecodeError:
            body = {"message": err_raw}
        return exc.code, body


def list_scratchpad_notes(
    owner: str,
    token: str,
    *,
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> list[ScratchpadNoteSummary]:
    """Lists Markdown notes under scratchpad/ in github.com/<owner>/config."""
    url = f"https://api.github.com/repos/{owner}/{config_repo}/contents/{SCRATCHPAD_DIR}?_cb={time.time_ns()}"
    status_code, body = _github_json_request(url, token)
    if status_code == 404:
        return []
    if status_code != 200:
        msg = body.get("message", f"HTTP {status_code}") if isinstance(body, dict) else str(body)
        raise RuntimeError(f"Failed listing '{owner}/{config_repo}/{SCRATCHPAD_DIR}': {msg}")
    if not isinstance(body, list):
        return []

    notes: list[ScratchpadNoteSummary] = []
    for entry in body:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        name = str(entry.get("name") or "")
        if not FILENAME_RE.match(name):
            continue
        slug = Path(name).stem
        notes.append(
            ScratchpadNoteSummary(
                filename=name,
                slug=slug,
                path=str(entry.get("path") or f"{SCRATCHPAD_DIR}/{name}"),
                title=title_from_filename(name),
                sha=str(entry.get("sha") or ""),
                size=int(entry.get("size") or 0),
                html_url=entry.get("html_url"),
            )
        )
    notes.sort(key=lambda item: item.filename)
    return notes


def read_scratchpad_note(
    owner: str,
    filename: str,
    token: str,
    *,
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> ScratchpadNoteDetail:
    """Reads and decodes a single Markdown note from github.com/<owner>/config/scratchpad/."""
    clean_name = validate_note_filename(filename)
    quoted_name = urllib.parse.quote(clean_name, safe="")
    url = f"https://api.github.com/repos/{owner}/{config_repo}/contents/{SCRATCHPAD_DIR}/{quoted_name}"
    status_code, body = _github_json_request(url, token)
    if status_code == 404:
        raise FileNotFoundError(f"Scratchpad note '{SCRATCHPAD_DIR}/{clean_name}' was not found.")
    if status_code != 200 or not isinstance(body, dict):
        msg = body.get("message", f"HTTP {status_code}") if isinstance(body, dict) else str(body)
        raise RuntimeError(f"Failed reading '{owner}/{config_repo}/{SCRATCHPAD_DIR}/{clean_name}': {msg}")

    raw_b64 = str(body.get("content") or "")
    content = base64.b64decode(raw_b64.encode("ascii")).decode("utf-8") if raw_b64 else ""
    return ScratchpadNoteDetail(
        filename=clean_name,
        slug=Path(clean_name).stem,
        path=str(body.get("path") or f"{SCRATCHPAD_DIR}/{clean_name}"),
        title=extract_title_from_markdown(content, clean_name),
        content=content,
        sha=str(body.get("sha") or ""),
        html_url=body.get("html_url"),
    )


def commit_scratchpad_note(
    owner: str,
    *,
    title: str,
    content: str,
    token: str,
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> ScratchpadSaveResult:
    """Commits a new Scratchpad note to github.com/<owner>/config/scratchpad/<slug>.md."""
    clean_title = " ".join((title or "").strip().splitlines()).strip() or "Untitled Note"
    normalized_md = normalize_note_markdown(clean_title, content)
    encoded_bytes = normalized_md.encode("utf-8")
    encoded_b64 = base64.b64encode(encoded_bytes).decode("ascii")
    note_size = len(encoded_bytes)
    taken: set[str] = set()

    for attempt in range(8):
        existing = [n.filename for n in list_scratchpad_notes(owner, token, config_repo=config_repo)]
        slug, filename = resolve_unique_slug(clean_title, set(existing) | taken)
        rel_path = f"{SCRATCHPAD_DIR}/{filename}"
        url = f"https://api.github.com/repos/{owner}/{config_repo}/contents/{rel_path}"
        status_code, body = _github_json_request(
            url,
            token,
            method="PUT",
            payload={
                "message": f"chore(scratchpad): add {filename}",
                "content": encoded_b64,
            },
        )
        if status_code in (200, 201) and isinstance(body, dict):
            content_obj = body.get("content") if isinstance(body.get("content"), dict) else {}
            commit_obj = body.get("commit") if isinstance(body.get("commit"), dict) else {}
            return ScratchpadSaveResult(
                filename=filename,
                slug=slug,
                path=str(content_obj.get("path") or rel_path),
                title=clean_title,
                sha=str(content_obj.get("sha") or commit_obj.get("sha") or ""),
                content=normalized_md,
                size=int(content_obj.get("size") or note_size),
                html_url=content_obj.get("html_url"),
            )
        if status_code == 422 and attempt < 7:
            taken.add(filename)
            continue
        msg = body.get("message", f"HTTP {status_code}") if isinstance(body, dict) else str(body)
        raise RuntimeError(f"Failed committing '{rel_path}' to '{owner}/{config_repo}': {msg}")

    raise RuntimeError(f"Could not resolve a unique filename for scratchpad note '{clean_title}'.")
