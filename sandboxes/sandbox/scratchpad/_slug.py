"""Slugification, collision resolution, and Markdown normalization for Scratchpad notes."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
import unicodedata

SCRATCHPAD_DIR = "scratchpad"
MAX_SLUG_LENGTH = 80
FILENAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_HEADING_H1_RE = re.compile(r"^#\s+(.+?)\s*$")


def slugify_title(title: str, fallback: str = "untitled-note") -> str:
    """Converts an arbitrary note title into lowercase kebab-case without extension."""
    normalized = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("-", normalized.lower()).strip("-")
    if len(slug) > MAX_SLUG_LENGTH:
        slug = slug[:MAX_SLUG_LENGTH].rstrip("-")
    return slug or fallback


def validate_note_filename(filename: str) -> str:
    """Validates and normalizes a Scratchpad filename to prevent traversal."""
    clean = (filename or "").strip()
    if "/" in clean or "\\" in clean or ".." in clean or not FILENAME_RE.match(clean):
        raise ValueError(f"Invalid scratchpad note filename: '{filename}'.")
    return clean


def resolve_unique_slug(title: str, existing_filenames: Iterable[str]) -> tuple[str, str]:
    """Resolves a collision-free (slug, '<slug>.md') pair using -2, -3 suffixes."""
    existing_lower = {Path(name).name.lower() for name in existing_filenames if name}
    base_slug = slugify_title(title)
    candidate_slug = base_slug
    counter = 2
    while f"{candidate_slug}.md" in existing_lower:
        suffix = f"-{counter}"
        stem = base_slug[: max(1, MAX_SLUG_LENGTH - len(suffix))].rstrip("-")
        candidate_slug = f"{stem}{suffix}"
        counter += 1
    return candidate_slug, f"{candidate_slug}.md"


def strip_leading_h1(markdown_body: str) -> str:
    """Removes a leading H1 ('# Title') line and following blank lines from Markdown body."""
    lines = (markdown_body or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\n").splitlines()
    if lines and _HEADING_H1_RE.match(lines[0]):
        idx = 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        return "\n".join(lines[idx:]).strip()
    return "\n".join(lines).strip()


def normalize_note_markdown(title: str, body: str) -> str:
    """Formats a note consistently with '# <Title>' heading followed by cleaned Markdown body."""
    clean_title = " ".join((title or "").strip().splitlines()).strip() or "Untitled Note"
    clean_body = strip_leading_h1(body)
    if not clean_body:
        return f"# {clean_title}\n"
    return f"# {clean_title}\n\n{clean_body}\n"


def extract_title_from_markdown(markdown_text: str, fallback_filename: str = "") -> str:
    """Extracts the primary H1 heading from Markdown content or formats fallback_filename."""
    for line in (markdown_text or "").splitlines():
        m = _HEADING_H1_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    stem = Path(fallback_filename).stem if fallback_filename else ""
    if stem:
        return stem.replace("-", " ").strip().title()
    return "Untitled Note"


def title_from_filename(filename: str) -> str:
    """Human-readable label derived from '<slug>.md'."""
    stem = Path(filename).stem
    return stem.replace("-", " ").strip().title() or filename
