"""Scratchpad Catalog Cache models and atomic merge transitions for factory-state-v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScratchpadSection = Literal["ideas", "raw"]


class CachedScratchpadNote(BaseModel):
    """Persisted metadata for one Idea Note or Raw Note in Central Config Store."""

    section: ScratchpadSection = "ideas"
    filename: str
    slug: str
    path: str
    title: str
    sha: str
    size: int = 0
    html_url: str | None = None


class CachedScratchpadBody(BaseModel):
    """Cached UTF-8 content for an individual Scratchpad note keyed by repo path and SHA."""

    sha: str
    content: str
    title: str
    html_url: str | None = None


class ScratchpadCatalogCache(BaseModel):
    """Persisted index of Idea Notes and Raw Notes stored in factory-state-v1."""

    config_repo: str | None = None
    refreshed_at: str | None = None
    ideas: list[CachedScratchpadNote] = Field(default_factory=list)
    raw: list[CachedScratchpadNote] = Field(default_factory=list)
    bodies: dict[str, CachedScratchpadBody] = Field(default_factory=dict)

    def notes_for(self, section: ScratchpadSection) -> list[CachedScratchpadNote]:
        """Returns cached note summaries for the given section."""
        return self.ideas if section == "ideas" else self.raw

    def find_note(self, section: ScratchpadSection, filename: str) -> CachedScratchpadNote | None:
        """Finds a cached summary entry by section and filename."""
        for item in self.notes_for(section):
            if item.filename == filename:
                return item
        return None


def _retained_bodies(existing: ScratchpadCatalogCache, config_repo: str) -> dict[str, CachedScratchpadBody]:
    if existing.config_repo and existing.config_repo != config_repo:
        return {}
    return dict(existing.bodies)


def merge_refreshed_scratchpad_catalog(
    existing: ScratchpadCatalogCache,
    config_repo: str,
    refreshed_at: str,
    ideas: list[CachedScratchpadNote],
    raw: list[CachedScratchpadNote],
) -> ScratchpadCatalogCache:
    """Replaces section indexes on refresh while retaining body caches with matching SHAs."""
    prior_bodies = _retained_bodies(existing, config_repo)
    next_bodies: dict[str, CachedScratchpadBody] = {}

    def _reconcile(items: list[CachedScratchpadNote]) -> list[CachedScratchpadNote]:
        out: list[CachedScratchpadNote] = []
        for item in sorted(items, key=lambda n: n.filename):
            cached = prior_bodies.get(item.path)
            if cached is not None and cached.sha == item.sha:
                next_bodies[item.path] = cached
                if cached.title and item.section == "ideas":
                    item = item.model_copy(update={"title": cached.title})
            out.append(item)
        return out

    return ScratchpadCatalogCache(
        config_repo=config_repo,
        refreshed_at=refreshed_at,
        ideas=_reconcile(ideas),
        raw=_reconcile(raw),
        bodies=next_bodies,
    )


def apply_scratchpad_commit(
    existing: ScratchpadCatalogCache,
    config_repo: str,
    note: CachedScratchpadNote,
    content: str,
) -> ScratchpadCatalogCache:
    """Upserts a newly committed note and its body into the persisted catalog."""
    same_repo = not existing.config_repo or existing.config_repo == config_repo
    ideas = list(existing.ideas) if same_repo else []
    raw = list(existing.raw) if same_repo else []
    bodies = _retained_bodies(existing, config_repo)

    target_list = ideas if note.section == "ideas" else raw
    updated_list = [n for n in target_list if n.filename != note.filename]
    updated_list.append(note)
    updated_list.sort(key=lambda n: n.filename)

    bodies[note.path] = CachedScratchpadBody(
        sha=note.sha,
        content=content,
        title=note.title,
        html_url=note.html_url,
    )
    return ScratchpadCatalogCache(
        config_repo=config_repo,
        refreshed_at=existing.refreshed_at if same_repo else None,
        ideas=updated_list if note.section == "ideas" else ideas,
        raw=updated_list if note.section == "raw" else raw,
        bodies=bodies,
    )


def apply_scratchpad_body(
    existing: ScratchpadCatalogCache,
    config_repo: str,
    note: CachedScratchpadNote,
    content: str,
) -> ScratchpadCatalogCache:
    """Caches an individual lazily fetched note body and updates its matching summary."""
    same_repo = not existing.config_repo or existing.config_repo == config_repo
    ideas = list(existing.ideas) if same_repo else []
    raw = list(existing.raw) if same_repo else []
    bodies = _retained_bodies(existing, config_repo)

    bodies[note.path] = CachedScratchpadBody(
        sha=note.sha,
        content=content,
        title=note.title,
        html_url=note.html_url,
    )
    target_list = ideas if note.section == "ideas" else raw
    replaced = [note if n.filename == note.filename else n for n in target_list]
    return ScratchpadCatalogCache(
        config_repo=config_repo,
        refreshed_at=existing.refreshed_at if same_repo else None,
        ideas=replaced if note.section == "ideas" else ideas,
        raw=replaced if note.section == "raw" else raw,
        bodies=bodies,
    )
