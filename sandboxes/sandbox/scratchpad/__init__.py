"""Dashboard Scratchpad deep module interface."""

from sandbox.apps._scratchpad_cache import (
    CachedScratchpadBody,
    CachedScratchpadNote,
    ScratchpadCatalogCache,
    ScratchpadSection,
)

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
    list_all_scratchpad_notes,
    list_scratchpad_notes,
    read_scratchpad_note,
    resolve_config_repo_context,
)
from ._routes import scratchpad_router, set_scratchpad_overrides
from ._slug import (
    RAW_SCRATCHPAD_DIR,
    SCRATCHPAD_DIR,
    SECTION_DIRS,
    derive_title_from_body,
    extract_title_from_markdown,
    normalize_note_markdown,
    resolve_section_dir,
    resolve_unique_slug,
    slugify_title,
    strip_leading_h1,
    validate_note_filename,
)

__all__ = [
    "CachedScratchpadBody",
    "CachedScratchpadNote",
    "FREE_SCRATCHPAD_MODELS",
    "MAX_RAW_NOTE_CHARS",
    "RAW_SCRATCHPAD_DIR",
    "SCRATCHPAD_DIR",
    "SECTION_DIRS",
    "ScratchpadCatalogCache",
    "ScratchpadNoteDetail",
    "ScratchpadNoteSummary",
    "ScratchpadSaveResult",
    "ScratchpadSection",
    "ScratchpadSuggestion",
    "commit_scratchpad_note",
    "derive_title_from_body",
    "extract_title_from_markdown",
    "list_all_scratchpad_notes",
    "list_scratchpad_notes",
    "normalize_note_markdown",
    "read_scratchpad_note",
    "resolve_config_repo_context",
    "resolve_opencode_binary",
    "resolve_section_dir",
    "resolve_unique_slug",
    "scratchpad_router",
    "set_scratchpad_overrides",
    "slugify_title",
    "strip_leading_h1",
    "suggest_scratchpad_note",
    "validate_note_filename",
]
