"""Prompt archetype classification, domain context extraction, and codebase grounding."""

from pathlib import Path
import re
from typing import Any
from factory.ui.scaffold import CONTEXT_TEMPLATE
from factory.ui.grill._models import (
    GrillQuestion,
    PromptArchetype,
)

FALLBACK_REPO_TREE = [
    "app/routes/__root.tsx",
    "app/routes/index.tsx",
    "app/components/Header.tsx",
    "app/components/Footer.tsx",
    "app/router.tsx",
    "package.json",
    "CONTEXT.md",
]

FALLBACK_FILE_CONTENTS: dict[str, str] = {
    "app/components/Footer.tsx": """import React from "react";

export function Footer() {
  return (
    <footer className="border-t py-6 text-center text-sm text-gray-500">
      <div className="flex justify-center space-x-6 mb-4">
        <a href="https://github.com" className="hover:text-gray-900">GitHub</a>
        <a href="https://x.com" className="hover:text-gray-900">X (Twitter)</a>
        <a href="https://discord.com" className="hover:text-gray-900">Discord</a>
      </div>
      <p>© 2026 Software Factory. All rights reserved.</p>
    </footer>
  );
}
""",
    "app/components/Header.tsx": """import React from "react";

export function Header() {
  return (
    <header className="border-b px-6 py-4 flex items-center justify-between">
      <div className="font-bold text-xl">App</div>
      <nav className="flex space-x-4">
        <a href="/" className="hover:underline">Home</a>
      </nav>
    </header>
  );
}
""",
}

PROMPT_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "through", "after", "before", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "can",
    "could", "should", "would", "will", "shall", "may", "might", "must", "it", "its",
    "this", "that", "these", "those", "i", "we", "you", "they", "he", "she", "me", "us",
    "him", "her", "my", "our", "your", "their", "what", "which", "who", "whom", "whose",
    "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "build", "make", "create", "add", "remove", "delete", "update", "modify", "change",
    "like", "etc", "please", "want", "need", "app", "application", "file", "code",
}

KEYWORD_EXPANSIONS: dict[str, dict[str, int]] = {
    "social": {"footer": 8, "social": 10, "icons": 6, "links": 8, "header": 2},
    "link": {"links": 8, "nav": 6, "menu": 6, "footer": 5, "header": 4, "sidebar": 4},
    "links": {"links": 8, "nav": 6, "menu": 6, "footer": 5, "header": 4, "sidebar": 4},
    "media": {"footer": 4, "social": 6, "media": 8},
    "footer": {"footer": 10, "bottom": 6},
    "header": {"header": 10, "topbar": 8, "nav": 6, "navbar": 6},
    "nav": {"nav": 10, "navbar": 10, "header": 8, "menu": 6, "sidebar": 6},
    "navigation": {"nav": 10, "navbar": 10, "header": 8, "menu": 6, "sidebar": 6},
    "navbar": {"navbar": 10, "nav": 10, "header": 8},
    "sidebar": {"sidebar": 10, "aside": 8, "nav": 6, "menu": 6},
    "menu": {"menu": 10, "nav": 8, "header": 6, "sidebar": 6},
    "theme": {"theme": 10, "toggle": 8, "header": 6, "navbar": 6},
    "dark": {"theme": 8, "toggle": 8, "header": 6, "navbar": 6},
    "auth": {"auth": 10, "login": 8, "user": 6},
    "login": {"login": 10, "auth": 8, "user": 6},
}


def parse_context_terms(context_content: str) -> list[dict[str, Any]]:
    """Extracts defined terms, descriptions, and avoided terms from CONTEXT.md content."""
    terms: list[dict[str, Any]] = []
    term_blocks = re.findall(
        r"\*\*([^*]+)\*\*:\s*\n(.*?)(?=\n\*\*[^*]+\*\*:|\Z)",
        context_content,
        re.DOTALL,
    )
    for name, body in term_blocks:
        name_clean = name.strip()
        body_clean = body.strip()
        avoid_matches = re.search(r"_Avoid_:\s*(.+)", body_clean)
        avoid_list = [a.strip() for a in avoid_matches.group(1).split(",") if a.strip()] if avoid_matches else []
        terms.append({
            "term": name_clean,
            "description": body_clean,
            "avoid": avoid_list,
        })
    return terms


def sharpen_domain_terms(text: str, context_content: str | None = None) -> list[dict[str, str]]:
    """Identifies fuzzy or conflicting terms in text and maps them to canonical CONTEXT.md terms."""
    content = context_content or CONTEXT_TEMPLATE
    terms = parse_context_terms(content)
    sharpened: list[dict[str, str]] = []
    text_lower = text.lower()

    for item in terms:
        canonical = item["term"]
        for avoid in item["avoid"]:
            avoid_clean = avoid.strip()
            if not avoid_clean:
                continue
            pattern = r"\b" + re.escape(avoid_clean.lower()) + r"\b"
            if re.search(pattern, text_lower):
                sharpened.append({
                    "fuzzy_term": avoid_clean,
                    "canonical_term": canonical,
                    "explanation": f"Your glossary in CONTEXT.md defines '{canonical}' ({item['description'].splitlines()[0]}). Avoid '{avoid_clean}'.",
                })

    if ("redux" in text_lower or "mobx" in text_lower) and not any(s["canonical_term"] == "Client State" for s in sharpened):
        sharpened.append({
            "fuzzy_term": "Redux / external store",
            "canonical_term": "Client State",
            "explanation": "CONTEXT.md defines Client State using React primitives and TanStack Query cache; avoids Redux store.",
        })

    if ("next.js" in text_lower or "vue" in text_lower or "remix" in text_lower) and not any(s["canonical_term"] == "TanStack Start SPA" for s in sharpened):
        sharpened.append({
            "fuzzy_term": "Next.js / Vue / Remix",
            "canonical_term": "TanStack Start SPA",
            "explanation": "Target applications are single-page frontend apps built on TanStack Start with Vite.",
        })

    return sharpened


def classify_prompt_archetype(prompt: str) -> PromptArchetype:
    """Classifies user prompt into archetypes to govern grilling frontier and architectural impact."""
    text = prompt.lower().strip()
    if not text:
        return "new_feature"
    if re.search(r"\b(remove|delete|drop|strip|clean\s*up|clear|prune|eliminate|omit|retire|cut\s*out)\b", text):
        return "deletion"
    if re.search(r"\b(style|styling|theme|dark\s*mode|color|colors|font|fonts|tailwind|padding|margin|spacing|responsive|layout)\b", text):
        return "styling"
    if re.search(r"\b(modify|update|edit|tweak|replace|fix|refactor|change|adjust|patch|revise|rename)\b", text):
        return "component_modification"
    return "new_feature"


def extract_path_tokens(path: str) -> set[str]:
    p = Path(path)
    stem_tokens = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)", p.stem)
    parts = re.split(r"[/\\._-]+", path.lower())
    return set(t.lower() for t in stem_tokens + parts if len(t) > 1)


def score_path_against_keywords(
    path: str,
    direct_keywords: set[str],
    keyword_weights: dict[str, int],
) -> int:
    path_lower = path.lower()
    valid_exts = {".tsx", ".ts", ".jsx", ".js", ".css"}
    if not any(path_lower.endswith(ext) for ext in valid_exts):
        return 0

    tokens = extract_path_tokens(path)
    score = 0
    for kw in direct_keywords:
        if kw in tokens:
            score += 10
        elif any(kw in t or t in kw for t in tokens if len(kw) >= 3 and len(t) >= 3):
            score += 4

    for term, weight in keyword_weights.items():
        if term in tokens:
            score += weight
        elif any(term in t or t in term for t in tokens if len(term) >= 3 and len(t) >= 3):
            score += max(1, weight // 2)

    if score > 0:
        if "components/" in path_lower:
            score += 3
        elif "routes/" in path_lower:
            score += 1
    return score


def format_repo_structure_summary(file_paths: list[str], branch: str) -> str:
    routes = [p for p in file_paths if "routes/" in p.lower()]
    components = [p for p in file_paths if "components/" in p.lower()]
    others = [p for p in file_paths if p not in routes and p not in components]

    lines = [f"Branch: {branch}"]
    if routes:
        lines.append("Routes:")
        lines.extend(f"  - {r}" for r in sorted(routes))
    if components:
        lines.append("Components:")
        lines.extend(f"  - {c}" for c in sorted(components))
    if others:
        lines.append("Other Files:")
        lines.extend(f"  - {o}" for o in sorted(others)[:10])
    return "\n".join(lines)


def format_candidate_sources(candidate_contents: dict[str, str]) -> str:
    if not candidate_contents:
        return "(No candidate component source files matched the prompt keywords)"
    chunks = [
        f"#### File: `{path}`\n```{Path(path).suffix.lstrip('.') or 'tsx'}\n{content}\n```"
        for path, content in candidate_contents.items()
    ]
    return "\n\n".join(chunks)


def get_mock_frontier_questions(
    archetype: PromptArchetype,
    effective_prompt: str,
) -> tuple[list[GrillQuestion], str]:
    """Generates deterministic mock grilling questions and summary for Round 1."""
    from factory.ui.grill._adr_drafting import slugify

    if archetype == "deletion":
        questions = [
            GrillQuestion(
                id="Q1",
                title="Component Scope",
                question="Which component contains the elements to be removed?",
                recommended="Target existing component (e.g. `app/components/Footer.tsx` or `Header.tsx`) where the elements reside.",
                options=["Existing component in app/components/ (Recommended)", "All navigation and footer components", "Global layout component"],
            ),
            GrillQuestion(
                id="Q2",
                title="Layout & Spacing Reflow",
                question="How should surrounding layout and spacing adjust after removing these elements?",
                recommended="Reflow the container cleanly without leaving residual gaps, empty wrappers, or awkward whitespace.",
                options=["Clean reflow without residual whitespace (Recommended)", "Retain layout bounds with centered copyright text", "Collapse container height"],
            ),
            GrillQuestion(
                id="Q3",
                title="Asset & Dependency Pruning",
                question="Should unused icons, external assets, or link definitions be pruned?",
                recommended="Remove unused icon imports and dead link configurations to keep component code clean.",
                options=["Prune unused imports and assets (Recommended)", "Retain imports for future re-use"],
            ),
        ]
        summary = "Identified component scope and layout reflow decisions for deletion. Please review recommended defaults."

    elif archetype == "component_modification":
        questions = [
            GrillQuestion(
                id="Q1",
                title="Component Scope",
                question="Which existing component should be modified?",
                recommended="Update the relevant component in `app/components/` in place without creating new routes.",
                options=["Update existing component in app/components/ (Recommended)", "Extract to a new sub-component"],
            ),
            GrillQuestion(
                id="Q2",
                title="State & Props Behavior",
                question="How should component props or state react to this change?",
                recommended="Keep state updates localized to the component or existing TanStack Query cache.",
                options=["Localized component state (Recommended)", "Lift state to parent component"],
            ),
            GrillQuestion(
                id="Q3",
                title="Component Interface",
                question="Should existing component props and usages remain backward compatible?",
                recommended="Maintain backward compatibility for existing callers while adding the requested adjustments.",
                options=["Maintain backward compatible props (Recommended)", "Refactor callers immediately"],
            ),
        ]
        summary = "Clarified component modification scope and state behavior. Please review recommended defaults."

    elif archetype == "styling":
        questions = [
            GrillQuestion(
                id="Q1",
                title="Design Tokens & Styling",
                question="Which styling approach and tokens should be applied?",
                recommended="Use responsive Tailwind CSS utility classes matching existing design tokens.",
                options=["Responsive Tailwind CSS utility classes (Recommended)", "Custom CSS class overrides"],
            ),
            GrillQuestion(
                id="Q2",
                title="Responsive & Theme Support",
                question="How should theme adjustments and responsive breakpoints be handled?",
                recommended="Ensure consistent contrast in light/dark themes and responsive behavior across mobile and desktop.",
                options=["Consistent contrast across themes and mobile/desktop (Recommended)", "Desktop-only layout adjustment"],
            ),
            GrillQuestion(
                id="Q3",
                title="Component Styling Scope",
                question="Are styling adjustments localized to specific components or global?",
                recommended="Apply styling adjustments directly to the target component without modifying global base stylesheets.",
                options=["Target component only (Recommended)", "Global theme variables in CSS"],
            ),
        ]
        summary = "Aligned styling requirements and design tokens. Please review recommended defaults."

    else:
        feature_slug = slugify(effective_prompt)
        questions = [
            GrillQuestion(
                id="Q1",
                title="Route Placement",
                question="Where in the application Route Tree should this feature be mounted?",
                recommended=f"Add a dedicated typed route under `app/routes/{feature_slug}.tsx` adhering to TanStack Start conventions.",
                options=[f"Dedicated route at app/routes/{feature_slug}.tsx (Recommended)", "Sub-route nested within existing view", "Modal overlay on root dashboard"],
            ),
            GrillQuestion(
                id="Q2",
                title="State Management & Persistence",
                question="How should application state and filters for this feature be managed?",
                recommended="Manage state using React primitives and TanStack Query in-memory cache, keeping the application a clean stateless client SPA.",
                options=["TanStack Query in-memory cache and React state (Recommended)", "Browser localStorage persistence", "Session storage"],
            ),
            GrillQuestion(
                id="Q3",
                title="Visual Design & Layout",
                question="What layout structure and styling system should be applied?",
                recommended="Construct responsive components styled with Tailwind CSS utility classes matching existing design tokens.",
                options=["Responsive Tailwind CSS utility classes (Recommended)", "Full-bleed data dashboard with dark mode accents"],
            ),
        ]
        summary = "Identified unsettled decisions on the requirement frontier. Please review the recommended defaults or provide custom specifications."

    return questions, summary
