"""Conversational Grilling Assistant and Turn Protocol Package.

Re-exports all public symbols, dataclasses, helper functions, and classes for 100% backward compatibility.
"""

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, resolve_repo_root, strip_repo_owner
from factory.ui.grill._adr_drafting import (
    compute_next_adr_metadata,
    format_questions_markdown,
    slugify,
)
from factory.ui.grill._archetypes import (
    FALLBACK_FILE_CONTENTS,
    FALLBACK_REPO_TREE,
    KEYWORD_EXPANSIONS,
    PROMPT_STOPWORDS,
    classify_prompt_archetype,
    extract_path_tokens,
    format_candidate_sources,
    format_repo_structure_summary,
    parse_context_terms,
    score_path_against_keywords,
    sharpen_domain_terms,
)
from factory.ui.grill._inference import (
    resolve_opencode_go_api_key,
    validate_opencode_go_api_key,
)
from factory.ui.grill._models import (
    OPENCODE_GO_DEFAULT_MODEL,
    OPENCODE_GO_DEFAULT_URL,
    CodebaseGroundingContext,
    DomainTermSharpening,
    DraftADR,
    GrillQuestion,
    GrillTurnResult,
    PromptArchetype,
)
from factory.ui.grill._turn_runner import GrillingAssistant

__all__ = [
    "CodebaseGroundingContext",
    "DEFAULT_TEST_ORG",
    "DomainTermSharpening",
    "DraftADR",
    "FALLBACK_FILE_CONTENTS",
    "FALLBACK_REPO_TREE",
    "GrillQuestion",
    "GrillTurnResult",
    "GrillingAssistant",
    "KEYWORD_EXPANSIONS",
    "OPENCODE_GO_DEFAULT_MODEL",
    "OPENCODE_GO_DEFAULT_URL",
    "PROMPT_STOPWORDS",
    "PromptArchetype",
    "classify_prompt_archetype",
    "compute_next_adr_metadata",
    "extract_path_tokens",
    "format_candidate_sources",
    "format_questions_markdown",
    "format_repo_structure_summary",
    "get_test_org_token",
    "parse_context_terms",
    "resolve_opencode_go_api_key",
    "resolve_repo_root",
    "score_path_against_keywords",
    "sharpen_domain_terms",
    "slugify",
    "strip_repo_owner",
    "validate_opencode_go_api_key",
]
