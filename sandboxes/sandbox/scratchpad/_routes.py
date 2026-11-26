"""FastAPI REST router for Dashboard Scratchpad Ideas, Raw notes, and catalog cache."""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from sandbox.apps._models import utc_now_iso
from sandbox.apps._scratchpad_cache import (
    CachedScratchpadNote,
    ScratchpadCatalogCache,
    ScratchpadSection,
)
from sandbox.apps._store import get_default_store
from sandbox.env_store import DEFAULT_CONFIG_REPO

from ._ai import MAX_RAW_NOTE_CHARS, suggest_scratchpad_note
from ._github import (
    commit_scratchpad_note,
    list_scratchpad_notes,
    read_scratchpad_note,
    resolve_config_repo_context,
)
from ._slug import (
    RAW_SCRATCHPAD_DIR,
    SCRATCHPAD_DIR,
    derive_title_from_body,
    resolve_section_dir,
    resolve_unique_slug,
    validate_note_filename,
)

logger = logging.getLogger(__name__)

scratchpad_router = APIRouter(prefix="/api/scratchpad", tags=["scratchpad"])

_SUGGEST_FN: Callable[..., Any] | None = None
_LIST_NOTES_FN: Callable[..., Any] | None = None
_READ_NOTE_FN: Callable[..., Any] | None = None
_COMMIT_NOTE_FN: Callable[..., Any] | None = None
_CONTEXT_FN: Callable[..., tuple[str, str]] | None = None
_STORE_FN: Callable[[], Any] | None = None


def set_scratchpad_overrides(
    *,
    suggest_fn: Callable[..., Any] | None = None,
    list_notes_fn: Callable[..., Any] | None = None,
    read_note_fn: Callable[..., Any] | None = None,
    commit_note_fn: Callable[..., Any] | None = None,
    context_fn: Callable[..., tuple[str, str]] | None = None,
    store_fn: Callable[[], Any] | None = None,
) -> None:
    """Overrides backend collaborators and state store for unit testing."""
    global _SUGGEST_FN, _LIST_NOTES_FN, _READ_NOTE_FN, _COMMIT_NOTE_FN, _CONTEXT_FN, _STORE_FN
    _SUGGEST_FN = suggest_fn
    _LIST_NOTES_FN = list_notes_fn
    _READ_NOTE_FN = read_note_fn
    _COMMIT_NOTE_FN = commit_note_fn
    _CONTEXT_FN = context_fn
    _STORE_FN = store_fn


class ScratchpadSuggestRequest(BaseModel):
    """Request body for AI structuring/refinement of an Idea draft."""

    raw_text: str
    title_hint: str | None = None
    model: str | None = None


class ScratchpadSuggestResponse(BaseModel):
    """Suggested title, target path, and improved Markdown returned to the popup modal."""

    title: str
    slug: str
    filename: str
    target_path: str
    content: str
    model: str


class ScratchpadSaveRequest(BaseModel):
    """Request body for committing an Idea Note or verbatim Raw Note."""

    title: str = ""
    content: str
    section: ScratchpadSection = "ideas"
    mode: Literal["ai", "raw"] | None = None


class ScratchpadNoteSummaryView(BaseModel):
    """Serializable note summary entry for Ideas or Raw browsers."""

    section: ScratchpadSection = "ideas"
    filename: str
    slug: str
    path: str
    title: str
    sha: str
    size: int
    html_url: str | None = None


class ScratchpadCatalogResponse(BaseModel):
    """Persisted Scratchpad catalog covering both Ideas (scratchpad/) and Raw (raw/)."""

    config_repo: str = ""
    refreshed_at: str | None = None
    ideas_directory: str = SCRATCHPAD_DIR
    raw_directory: str = RAW_SCRATCHPAD_DIR
    ideas: list[ScratchpadNoteSummaryView] = Field(default_factory=list)
    raw: list[ScratchpadNoteSummaryView] = Field(default_factory=list)


class ScratchpadNoteDetailView(BaseModel):
    """Full UTF-8 note payload."""

    section: ScratchpadSection = "ideas"
    filename: str
    slug: str
    path: str
    title: str
    content: str
    sha: str
    html_url: str | None = None


class ScratchpadSaveResponse(BaseModel):
    """Response payload returned after committing an Idea Note or Raw Note."""

    section: ScratchpadSection = "ideas"
    filename: str
    slug: str
    path: str
    title: str
    sha: str
    content: str
    size: int = 0
    html_url: str | None = None
    config_repo: str


def _resolve_context() -> tuple[str, str]:
    ctx_fn = _CONTEXT_FN or resolve_config_repo_context
    return ctx_fn()


def _get_store():
    return _STORE_FN() if _STORE_FN is not None else get_default_store()


def _to_summary_view(item: CachedScratchpadNote) -> ScratchpadNoteSummaryView:
    return ScratchpadNoteSummaryView(
        section=item.section,
        filename=item.filename,
        slug=item.slug,
        path=item.path,
        title=item.title,
        sha=item.sha,
        size=item.size,
        html_url=item.html_url,
    )


def _to_cached_note(item: Any, section: ScratchpadSection) -> CachedScratchpadNote:
    return CachedScratchpadNote(
        section=getattr(item, "section", section) or section,
        filename=item.filename,
        slug=item.slug,
        path=item.path,
        title=item.title,
        sha=item.sha,
        size=int(getattr(item, "size", 0) or 0),
        html_url=getattr(item, "html_url", None),
    )


def _catalog_to_response(catalog: ScratchpadCatalogCache, fallback_repo: str = "") -> ScratchpadCatalogResponse:
    return ScratchpadCatalogResponse(
        config_repo=catalog.config_repo or fallback_repo,
        refreshed_at=catalog.refreshed_at,
        ideas=[_to_summary_view(item) for item in catalog.ideas],
        raw=[_to_summary_view(item) for item in catalog.raw],
    )


def _configured_repo_label() -> str:
    try:
        owner, _ = _resolve_context()
        return f"{owner}/{DEFAULT_CONFIG_REPO}"
    except ValueError:
        return ""


@scratchpad_router.get("/notes", response_model=ScratchpadCatalogResponse)
def get_scratchpad_notes(response: Response) -> ScratchpadCatalogResponse:
    """Returns cached Ideas and Raw lists from factory-state-v1 without querying GitHub."""
    response.headers["Cache-Control"] = "no-store"
    catalog = _get_store().get_scratchpad_catalog()
    fallback_repo = "" if catalog.config_repo else _configured_repo_label()
    return _catalog_to_response(catalog, fallback_repo=fallback_repo)


@scratchpad_router.post("/notes/refresh", response_model=ScratchpadCatalogResponse)
def refresh_scratchpad_notes(response: Response) -> ScratchpadCatalogResponse:
    """Refreshes cached Ideas (config/scratchpad/) and Raw (config/raw/) lists from GitHub."""
    response.headers["Cache-Control"] = "no-store"
    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    list_fn = _LIST_NOTES_FN or list_scratchpad_notes
    try:
        ideas_items = list_fn(owner, token, section="ideas")
        raw_items = list_fn(owner, token, section="raw")
    except Exception as exc:
        logger.error("Failed refreshing scratchpad notes: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    config_repo = f"{owner}/{DEFAULT_CONFIG_REPO}"
    catalog = _get_store().save_scratchpad_catalog(
        config_repo,
        utc_now_iso(),
        [_to_cached_note(item, "ideas") for item in ideas_items],
        [_to_cached_note(item, "raw") for item in raw_items],
    )
    return _catalog_to_response(catalog)


@scratchpad_router.get("/notes/{filename}", response_model=ScratchpadNoteDetailView)
def get_scratchpad_note(
    filename: str,
    section: ScratchpadSection = Query("ideas", description="Scratchpad section ('ideas' or 'raw')"),
) -> ScratchpadNoteDetailView:
    """Reads an Idea Note or Raw Note from cache when fresh, else lazily fetches from GitHub."""
    try:
        clean_section, directory = resolve_section_dir(section)
        clean_filename = validate_note_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    store = _get_store()
    catalog = store.get_scratchpad_catalog()
    summary = catalog.find_note(clean_section, clean_filename)
    rel_path = f"{directory}/{clean_filename}"
    cached_body = catalog.bodies.get(rel_path)

    if summary is not None and cached_body is not None and cached_body.sha == summary.sha:
        return ScratchpadNoteDetailView(
            section=clean_section,
            filename=summary.filename,
            slug=summary.slug,
            path=summary.path,
            title=cached_body.title or summary.title,
            content=cached_body.content,
            sha=summary.sha,
            html_url=cached_body.html_url or summary.html_url,
        )

    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    read_fn = _READ_NOTE_FN or read_scratchpad_note
    try:
        note = read_fn(owner, clean_filename, token, section=clean_section)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed reading %s note %s: %s", clean_section, filename, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    config_repo = f"{owner}/{DEFAULT_CONFIG_REPO}"
    encoded_size = len(note.content.encode("utf-8"))
    cached_note = CachedScratchpadNote(
        section=clean_section,
        filename=note.filename,
        slug=note.slug,
        path=note.path,
        title=note.title,
        sha=note.sha,
        size=summary.size if summary and summary.size else encoded_size,
        html_url=note.html_url,
    )
    store.cache_scratchpad_body(config_repo, cached_note, note.content)
    return ScratchpadNoteDetailView(
        section=clean_section,
        filename=note.filename,
        slug=note.slug,
        path=note.path,
        title=note.title,
        content=note.content,
        sha=note.sha,
        html_url=note.html_url,
    )


@scratchpad_router.post("/suggest", response_model=ScratchpadSuggestResponse)
def post_scratchpad_suggest(payload: ScratchpadSuggestRequest) -> ScratchpadSuggestResponse:
    """Generates a structured title and Markdown suggestion via free OpenCode CLI models (Ideas only)."""
    raw = (payload.raw_text or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please enter an idea or note before submitting.")
    if len(raw) > MAX_RAW_NOTE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Note exceeds maximum length of {MAX_RAW_NOTE_CHARS} characters.",
        )

    suggest_fn = _SUGGEST_FN or suggest_scratchpad_note
    try:
        models = (payload.model,) if payload.model and payload.model.strip() else None
        suggestion = suggest_fn(raw, title_hint=payload.title_hint, models=models)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Scratchpad AI suggestion failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    existing_filenames: list[str] = []
    if _LIST_NOTES_FN is not None:
        try:
            owner, token = _resolve_context()
            existing_filenames = [item.filename for item in _LIST_NOTES_FN(owner, token, section="ideas")]
        except Exception:
            existing_filenames = []
    else:
        try:
            existing_filenames = [item.filename for item in _get_store().get_scratchpad_catalog().ideas]
        except Exception:
            existing_filenames = []

    slug, filename = resolve_unique_slug(suggestion.title, existing_filenames)
    return ScratchpadSuggestResponse(
        title=suggestion.title,
        slug=slug,
        filename=filename,
        target_path=f"{SCRATCHPAD_DIR}/{filename}",
        content=suggestion.content,
        model=suggestion.model,
    )


@scratchpad_router.post("/notes", response_model=ScratchpadSaveResponse, status_code=status.HTTP_201_CREATED)
def post_scratchpad_note(payload: ScratchpadSaveRequest) -> ScratchpadSaveResponse:
    """Commits an Idea Note (config/scratchpad/) or verbatim Raw Note (config/raw/) and updates cache."""
    clean_section, _ = resolve_section_dir(payload.section)
    raw_content = payload.content or ""
    if not raw_content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Note content cannot be empty.")

    body = raw_content.strip() if clean_section == "ideas" else raw_content
    raw_title = " ".join((payload.title or "").strip().splitlines()).strip()
    if not raw_title:
        raw_title = derive_title_from_body(body)

    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    commit_fn = _COMMIT_NOTE_FN or commit_scratchpad_note
    try:
        saved = commit_fn(owner, title=raw_title, content=body, token=token, section=clean_section)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed saving %s note: %s", clean_section, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    config_repo = f"{owner}/{DEFAULT_CONFIG_REPO}"
    note_size = saved.size or len(saved.content.encode("utf-8"))
    cached_note = CachedScratchpadNote(
        section=clean_section,
        filename=saved.filename,
        slug=saved.slug,
        path=saved.path,
        title=saved.title,
        sha=saved.sha,
        size=note_size,
        html_url=saved.html_url,
    )
    _get_store().record_scratchpad_commit(config_repo, cached_note, saved.content)

    return ScratchpadSaveResponse(
        section=clean_section,
        filename=saved.filename,
        slug=saved.slug,
        path=saved.path,
        title=saved.title,
        sha=saved.sha,
        content=saved.content,
        size=note_size,
        html_url=saved.html_url,
        config_repo=config_repo,
    )
