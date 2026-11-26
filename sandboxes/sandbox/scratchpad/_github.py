"""GitHub Central Config Store persistence for Scratchpad Markdown notes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from sandbox.config_store import CentralConfigStore, ConfigStoreHTTPError
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


def list_scratchpad_notes(
    owner: str,
    token: str,
    *,
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> list[ScratchpadNoteSummary]:
    """Lists Markdown notes under scratchpad/ in github.com/<owner>/config."""
    body = CentralConfigStore(owner, token, config_repo).list_directory(SCRATCHPAD_DIR)
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
    file = CentralConfigStore(owner, token, config_repo).read(f"{SCRATCHPAD_DIR}/{clean_name}")
    if file is None:
        raise FileNotFoundError(f"Scratchpad note '{SCRATCHPAD_DIR}/{clean_name}' was not found.")
    content = file.content.decode("utf-8")
    return ScratchpadNoteDetail(
        filename=clean_name, slug=Path(clean_name).stem, path=file.path,
        title=extract_title_from_markdown(content, clean_name), content=content,
        sha=file.sha, html_url=file.html_url,
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
    note_size = len(encoded_bytes)
    taken: set[str] = set()

    for attempt in range(8):
        existing = [n.filename for n in list_scratchpad_notes(owner, token, config_repo=config_repo)]
        slug, filename = resolve_unique_slug(clean_title, set(existing) | taken)
        rel_path = f"{SCRATCHPAD_DIR}/{filename}"
        try:
            commit = CentralConfigStore(owner, token, config_repo).write(
                rel_path, encoded_bytes, f"chore(scratchpad): add {filename}",
            )
        except ConfigStoreHTTPError as error:
            if error.creation_collision and attempt < 7:
                taken.add(filename)
                continue
            raise
        return ScratchpadSaveResult(
            filename=filename, slug=slug, path=commit.path, title=clean_title,
            sha=commit.sha or commit.commit_sha, content=normalized_md,
            size=commit.size or note_size, html_url=commit.html_url,
        )

    raise RuntimeError(f"Could not resolve a unique filename for scratchpad note '{clean_title}'.")
