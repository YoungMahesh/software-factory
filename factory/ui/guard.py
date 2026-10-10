"""Fast Intent Classification Guard for Factory Studio.

Evaluates user prompts before sandbox provisioning to enforce the strict
frontend-only boundary (TanStack Start client-side applications), refusing
requests requiring databases, backend servers/APIs, or external storage.
"""

from dataclasses import dataclass
import re
from typing import Any


@dataclass
class IntentGuardResult:
    """Result of intent classification evaluation."""

    allowed: bool
    reason: str | None = None
    refusal_message: str | None = None
    category: str | None = None


# Patterns indicating database requirements
DATABASE_PATTERNS = [
    re.compile(r"\b(?:postgres(?:ql)?|psql)\b", re.IGNORECASE),
    re.compile(r"\bmongodb?\b", re.IGNORECASE),
    re.compile(r"\bmysql\b", re.IGNORECASE),
    re.compile(r"\bsqlite\b", re.IGNORECASE),
    re.compile(r"\bredis\b", re.IGNORECASE),
    re.compile(r"\bsupabase\b", re.IGNORECASE),
    re.compile(r"\bdynamodb\b", re.IGNORECASE),
    re.compile(r"\bmariadb\b", re.IGNORECASE),
    re.compile(r"\bcassandra\b", re.IGNORECASE),
    re.compile(r"\bprisma(?:\s+schema|\s+migrations?)?\b", re.IGNORECASE),
    re.compile(r"\bdatabase\b", re.IGNORECASE),
    re.compile(r"\bsql\s+(?:query|queries|tables?)\b", re.IGNORECASE),
    re.compile(r"\b(?:db|schema)\s+migrations?\b", re.IGNORECASE),
    re.compile(r"\bforeign\s+keys?\b", re.IGNORECASE),
    re.compile(r"\bmongoose\b", re.IGNORECASE),
]

# Patterns indicating backend server or backend API requirements
BACKEND_API_PATTERNS = [
    re.compile(r"\b(?:node(?:\.js)?|express)\s+(?:server|backend|endpoints?)\b", re.IGNORECASE),
    re.compile(r"\b(?:fastapi|flask|django|spring\s+boot|ruby\s+on\s+rails|rails)\b", re.IGNORECASE),
    re.compile(r"\b(?:backend|back-end)\s+(?:api|server|service|endpoints?|routes?)\b", re.IGNORECASE),
    re.compile(r"\bserver-side\s+(?:routes?|endpoints?|auth|sessions?|logic)\b", re.IGNORECASE),
    re.compile(r"\bwebsocket\s+server\b", re.IGNORECASE),
    re.compile(r"\bmicroservices?\b", re.IGNORECASE),
    re.compile(r"\bserver\s+daemon\b", re.IGNORECASE),
    re.compile(r"\bbackend\b", re.IGNORECASE),
]

# Patterns indicating external or server-side persistent storage
SERVER_STORAGE_PATTERNS = [
    re.compile(r"\b(?:aws\s+)?s3\s+bucket\b", re.IGNORECASE),
    re.compile(r"\bgoogle\s+cloud\s+storage\b", re.IGNORECASE),
    re.compile(r"\b(?:azure\s+)?blob\s+storage\b", re.IGNORECASE),
    re.compile(r"\bcloud\s+storage\s+bucket\b", re.IGNORECASE),
    re.compile(r"\bserver(?:\s+filesystem|\s+storage|\s+disk)\b", re.IGNORECASE),
    re.compile(r"\bfilesystem\s+persistence\s+(?:on\s+the\s+server|on\s+server)\b", re.IGNORECASE),
    re.compile(r"\b/var/\w+", re.IGNORECASE),
]

# Safe client-side storage expressions that should NOT trigger storage rejection
SAFE_CLIENT_STORAGE_REGEX = re.compile(
    r"\b(?:localstorage|sessionstorage|indexeddb|browser\s+storage|client-side\s+storage|in-memory\s+storage)\b",
    re.IGNORECASE,
)


def format_refusal_message(category: str, detail: str) -> str:
    """Constructs a strict refusal message detailing the frontend-only boundary."""
    category_labels = {
        "database": "databases, schemas, and persistence engines",
        "backend_api": "backend servers, server APIs, and microservices",
        "server_storage": "external cloud buckets and server filesystem storage",
    }
    cat_desc = category_labels.get(category, category)
    return (
        f"Request rejected: Factory Studio is strictly scoped to frontend client-side web applications "
        f"built with TanStack Start. Requests requiring {cat_desc} ({detail}) are not supported. "
        f"Please refine your prompt to focus purely on client-side UI, components, mock data, or browser-based state."
    )


def evaluate_prompt_intent(prompt: str) -> IntentGuardResult:
    """Evaluates a user prompt against client-side constraints.

    Returns an IntentGuardResult indicating whether the request is allowed
    or strictly refused with an explanation of the frontend boundary.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return IntentGuardResult(
            allowed=False,
            reason="Prompt cannot be empty.",
            refusal_message="Prompt cannot be empty.",
            category=None,
        )

    clean_prompt = prompt.strip()

    storage_masked_prompt = SAFE_CLIENT_STORAGE_REGEX.sub("SAFE_CLIENT_STORAGE", clean_prompt)

    pattern_categories = [
        ("database", DATABASE_PATTERNS, clean_prompt),
        ("backend_api", BACKEND_API_PATTERNS, clean_prompt),
        ("server_storage", SERVER_STORAGE_PATTERNS, storage_masked_prompt),
    ]

    for category, patterns, text_to_check in pattern_categories:
        for pattern in patterns:
            match = pattern.search(text_to_check)
            if match:
                matched_text = match.group(0)
                return IntentGuardResult(
                    allowed=False,
                    reason=f"Detected {category.replace('_', ' ')} requirement: '{matched_text}'",
                    refusal_message=format_refusal_message(category, matched_text),
                    category=category,
                )

    return IntentGuardResult(allowed=True)
