"""Dashboard Scratchpad deep module interface."""

from ._ai import (
    FREE_SCRATCHPAD_MODELS,
    MAX_RAW_NOTE_CHARS,
    ScratchpadSuggestion,
    resolve_opencode_binary,
    suggest_scratchpad_note,
)
from ._github import (
    ScratchpadNoteDetail,
    ScratchpadNoteSummary,
    ScratchpadSaveResult,
    commit_scratchpad_note,
    list_scratchpad_notes,
    read_scratchpad_note,
    resolve_config_repo_context,
)
from ._routes import scratchpad_router, set_scratchpad_overrides
from ._slug import (
    SCRATCHPAD_DIR,
    extract_title_from_markdown,
    normalize_note_markdown,
    resolve_unique_slug,
    slugify_title,
    strip_leading_h1,
    validate_note_filename,
)

__all__ = [
    "FREE_SCRATCHPAD_MODELS",
    "MAX_RAW_NOTE_CHARS",
    "SCRATCHPAD_DIR",
    "ScratchpadNoteDetail",
    "ScratchpadNoteSummary",
    "ScratchpadSaveResult",
    "ScratchpadSuggestion",
    "commit_scratchpad_note",
    "extract_title_from_markdown",
    "list_scratchpad_notes",
    "normalize_note_markdown",
    "read_scratchpad_note",
    "resolve_config_repo_context",
    "resolve_opencode_binary",
    "resolve_unique_slug",
    "scratchpad_router",
    "set_scratchpad_overrides",
    "slugify_title",
    "strip_leading_h1",
    "suggest_scratchpad_note",
    "validate_note_filename",
]
