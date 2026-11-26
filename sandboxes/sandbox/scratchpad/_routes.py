"""FastAPI REST router for Dashboard Scratchpad notes and AI suggestions."""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from sandbox.env_store import DEFAULT_CONFIG_REPO

from ._ai import MAX_RAW_NOTE_CHARS, suggest_scratchpad_note
from ._github import (
    commit_scratchpad_note,
    list_scratchpad_notes,
    read_scratchpad_note,
    resolve_config_repo_context,
)
from ._slug import SCRATCHPAD_DIR, resolve_unique_slug, validate_note_filename

logger = logging.getLogger(__name__)

scratchpad_router = APIRouter(prefix="/api/scratchpad", tags=["scratchpad"])

_SUGGEST_FN: Callable[..., Any] | None = None
_LIST_NOTES_FN: Callable[..., Any] | None = None
_READ_NOTE_FN: Callable[..., Any] | None = None
_COMMIT_NOTE_FN: Callable[..., Any] | None = None
_CONTEXT_FN: Callable[..., tuple[str, str]] | None = None


def set_scratchpad_overrides(
    *,
    suggest_fn: Callable[..., Any] | None = None,
    list_notes_fn: Callable[..., Any] | None = None,
    read_note_fn: Callable[..., Any] | None = None,
    commit_note_fn: Callable[..., Any] | None = None,
    context_fn: Callable[..., tuple[str, str]] | None = None,
) -> None:
    """Overrides backend collaborators for unit testing."""
    global _SUGGEST_FN, _LIST_NOTES_FN, _READ_NOTE_FN, _COMMIT_NOTE_FN, _CONTEXT_FN
    _SUGGEST_FN = suggest_fn
    _LIST_NOTES_FN = list_notes_fn
    _READ_NOTE_FN = read_note_fn
    _COMMIT_NOTE_FN = commit_note_fn
    _CONTEXT_FN = context_fn


class ScratchpadSuggestRequest(BaseModel):
    """Request body for AI structuring/refinement of raw Scratchpad text."""

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
    """Request body for committing an accepted or raw Scratchpad note."""

    title: str
    content: str
    mode: Literal["ai", "raw"] = "ai"


class ScratchpadNoteSummaryView(BaseModel):
    """Serializable note summary entry for the Scratchpad browser list."""

    filename: str
    slug: str
    path: str
    title: str
    sha: str
    size: int
    html_url: str | None = None


class ScratchpadNotesListResponse(BaseModel):
    """List response for notes stored in config/scratchpad/."""

    config_repo: str
    directory: str = SCRATCHPAD_DIR
    notes: list[ScratchpadNoteSummaryView]


class ScratchpadNoteDetailView(BaseModel):
    """Full Markdown note payload."""

    filename: str
    slug: str
    path: str
    title: str
    content: str
    sha: str
    html_url: str | None = None


class ScratchpadSaveResponse(BaseModel):
    """Response payload returned after committing a note to config/scratchpad/."""

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


@scratchpad_router.get("/notes", response_model=ScratchpadNotesListResponse)
def get_scratchpad_notes(response: Response) -> ScratchpadNotesListResponse:
    """Lists existing Markdown notes in github.com/${GH_ORG_NAME}/config/scratchpad/."""
    response.headers["Cache-Control"] = "no-store"
    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    list_fn = _LIST_NOTES_FN or list_scratchpad_notes
    try:
        items = list_fn(owner, token)
    except Exception as exc:
        logger.error("Failed listing scratchpad notes: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ScratchpadNotesListResponse(
        config_repo=f"{owner}/{DEFAULT_CONFIG_REPO}",
        notes=[
            ScratchpadNoteSummaryView(
                filename=item.filename,
                slug=item.slug,
                path=item.path,
                title=item.title,
                sha=item.sha,
                size=item.size,
                html_url=item.html_url,
            )
            for item in items
        ],
    )


@scratchpad_router.get("/notes/{filename}", response_model=ScratchpadNoteDetailView)
def get_scratchpad_note(filename: str) -> ScratchpadNoteDetailView:
    """Reads a single Markdown note from github.com/${GH_ORG_NAME}/config/scratchpad/."""
    try:
        clean_filename = validate_note_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    read_fn = _READ_NOTE_FN or read_scratchpad_note
    try:
        note = read_fn(owner, clean_filename, token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed reading scratchpad note %s: %s", filename, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ScratchpadNoteDetailView(
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
    """Generates a structured title and Markdown suggestion via free OpenCode CLI models."""
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
    try:
        owner, token = _resolve_context()
        list_fn = _LIST_NOTES_FN or list_scratchpad_notes
        existing_filenames = [item.filename for item in list_fn(owner, token)]
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
    """Commits an accepted or raw Scratchpad note to github.com/${GH_ORG_NAME}/config/scratchpad/."""
    body = (payload.content or "").strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Note content cannot be empty.")

    raw_title = (payload.title or "").strip()
    if not raw_title:
        first_line = next((ln.strip().lstrip("#").strip() for ln in body.splitlines() if ln.strip()), "")
        words = first_line.split()[:7]
        raw_title = " ".join(words) if words else "Untitled Note"

    try:
        owner, token = _resolve_context()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    commit_fn = _COMMIT_NOTE_FN or commit_scratchpad_note
    try:
        saved = commit_fn(owner, title=raw_title, content=body, token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed saving scratchpad note: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ScratchpadSaveResponse(
        filename=saved.filename,
        slug=saved.slug,
        path=saved.path,
        title=saved.title,
        sha=saved.sha,
        content=saved.content,
        size=saved.size,
        html_url=saved.html_url,
        config_repo=f"{owner}/{DEFAULT_CONFIG_REPO}",
    )
