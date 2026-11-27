"""GitHub Central Config Store persistence for Scratchpad Idea and Raw notes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from sandbox.apps._scratchpad_cache import ScratchpadSection
from sandbox.config_store import CentralConfigStore, ConfigStoreHTTPError
from sandbox.config import resolve_factory_credentials
from sandbox.env_store import DEFAULT_CONFIG_REPO, resolve_gh_token

from ._slug import (
    FILENAME_RE,
    derive_title_from_body,
    extract_title_from_markdown,
    normalize_note_markdown,
    resolve_section_dir,
    resolve_unique_slug,
    title_from_filename,
    validate_note_filename,
)


@dataclass(frozen=True)
class ScratchpadNoteSummary:
    """Lightweight metadata for one note stored in config/scratchpad/ or config/raw/."""

    filename: str
    slug: str
    path: str
    title: str
    sha: str
    size: int
    html_url: str | None = None
    section: ScratchpadSection = "ideas"


@dataclass(frozen=True)
class ScratchpadNoteDetail:
    """Full UTF-8 note retrieved from config/scratchpad/ or config/raw/."""

    filename: str
    slug: str
    path: str
    title: str
    content: str
    sha: str
    html_url: str | None = None
    section: ScratchpadSection = "ideas"


@dataclass(frozen=True)
class ScratchpadSaveResult:
    """Result of committing a new Idea Note or Raw Note to Central Config Store."""

    filename: str
    slug: str
    path: str
    title: str
    sha: str
    content: str
    size: int = 0
    html_url: str | None = None
    section: ScratchpadSection = "ideas"


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
    section: ScratchpadSection = "ideas",
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> list[ScratchpadNoteSummary]:
    """Lists Markdown notes under scratchpad/ (ideas) or raw/ in github.com/<owner>/config."""
    clean_section, directory = resolve_section_dir(section)
    body = CentralConfigStore(owner, token, config_repo).list_directory(directory)
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
                section=clean_section,
                filename=name,
                slug=slug,
                path=str(entry.get("path") or f"{directory}/{name}"),
                title=title_from_filename(name),
                sha=str(entry.get("sha") or ""),
                size=int(entry.get("size") or 0),
                html_url=entry.get("html_url"),
            )
        )
    notes.sort(key=lambda item: item.filename)
    return notes


def list_all_scratchpad_notes(
    owner: str,
    token: str,
    *,
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> tuple[list[ScratchpadNoteSummary], list[ScratchpadNoteSummary]]:
    """Lists both Ideas (scratchpad/) and Raw (raw/) directories from Central Config Store."""
    return (
        list_scratchpad_notes(owner, token, section="ideas", config_repo=config_repo),
        list_scratchpad_notes(owner, token, section="raw", config_repo=config_repo),
    )


def read_scratchpad_note(
    owner: str,
    filename: str,
    token: str,
    *,
    section: ScratchpadSection = "ideas",
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> ScratchpadNoteDetail:
    """Reads and decodes a single note from config/scratchpad/ or config/raw/."""
    clean_section, directory = resolve_section_dir(section)
    clean_name = validate_note_filename(filename)
    file = CentralConfigStore(owner, token, config_repo).read(f"{directory}/{clean_name}")
    if file is None:
        raise FileNotFoundError(f"Scratchpad note '{directory}/{clean_name}' was not found.")
    content = file.content.decode("utf-8")
    title = (
        extract_title_from_markdown(content, clean_name)
        if clean_section == "ideas"
        else title_from_filename(clean_name)
    )
    return ScratchpadNoteDetail(
        section=clean_section,
        filename=clean_name,
        slug=Path(clean_name).stem,
        path=file.path,
        title=title,
        content=content,
        sha=file.sha,
        html_url=file.html_url,
    )


def commit_scratchpad_note(
    owner: str,
    *,
    title: str,
    content: str,
    token: str,
    section: ScratchpadSection = "ideas",
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> ScratchpadSaveResult:
    """Commits an Idea Note (normalized Markdown) or Raw Note (verbatim UTF-8) to GitHub."""
    clean_section, directory = resolve_section_dir(section)
    clean_title = " ".join((title or "").strip().splitlines()).strip() or derive_title_from_body(content)
    if clean_section == "ideas":
        if not (content or "").strip():
            raise ValueError("Note content cannot be empty.")
        payload_text = normalize_note_markdown(clean_title, content)
    else:
        if not content or not content.strip():
            raise ValueError("Raw note content cannot be empty.")
        payload_text = content

    encoded_bytes = payload_text.encode("utf-8")
    note_size = len(encoded_bytes)
    taken: set[str] = set()

    for attempt in range(8):
        existing = [
            n.filename
            for n in list_scratchpad_notes(owner, token, section=clean_section, config_repo=config_repo)
        ]
        slug, filename = resolve_unique_slug(clean_title, set(existing) | taken)
        rel_path = f"{directory}/{filename}"
        try:
            commit = CentralConfigStore(owner, token, config_repo).write(
                rel_path, encoded_bytes, f"chore({directory}): add {filename}",
            )
        except ConfigStoreHTTPError as error:
            if error.creation_collision and attempt < 7:
                taken.add(filename)
                continue
            raise
        return ScratchpadSaveResult(
            section=clean_section,
            filename=filename,
            slug=slug,
            path=commit.path,
            title=clean_title,
            sha=commit.sha or commit.commit_sha,
            content=payload_text,
            size=commit.size or note_size,
            html_url=commit.html_url,
        )

    raise RuntimeError(f"Could not resolve a unique filename for {clean_section} note '{clean_title}'.")


def delete_scratchpad_note(
    owner: str,
    *,
    filename: str,
    token: str,
    section: ScratchpadSection = "ideas",
    config_repo: str = DEFAULT_CONFIG_REPO,
) -> str:
    """Deletes an Idea Note or Raw Note Markdown file from the Central Config Store on GitHub."""
    clean_section, directory = resolve_section_dir(section)
    clean_name = validate_note_filename(filename)
    rel_path = f"{directory}/{clean_name}"
    store = CentralConfigStore(owner, token, config_repo)
    metadata = store._file_metadata(rel_path)
    if metadata is None:
        raise FileNotFoundError(f"Scratchpad note '{clean_name}' not found in {rel_path}.")
    sha = str(metadata.get("sha") or "").strip()
    if not sha:
        raise RuntimeError(f"GitHub did not return a blob sha for '{rel_path}'.")
    store.delete(rel_path, sha, f"chore({directory}): delete {clean_name}")
    return rel_path
