"""Conversational Grilling Assistant and Turn Protocol Service.

Intercepts developer prompts in Factory Studio to conduct interactive grilling interviews,
stress-testing requirements and sharpening domain terminology against CONTEXT.md using
Matt Pocock's grilling and domain-modeling protocols before cloud sandboxes or jobs are dispatched.
"""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Literal
import httpx

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, resolve_repo_root, strip_repo_owner
from factory.ui.scaffold import CONTEXT_TEMPLATE

OPENCODE_GO_DEFAULT_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_DEFAULT_MODEL = "deepseek-v4.1-flash"


@dataclass
class GrillQuestion:
    """Represents a structured grilling question on the requirement frontier."""
    id: str  # e.g. "Q1"
    title: str  # e.g. "Route Placement"
    question: str  # The question body / choices
    recommended: str  # The recommended answer
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_markdown(self) -> str:
        options_text = ""
        if self.options:
            options_text = "\n" + "\n".join(f"- {opt}" for opt in self.options)
        return f"❓ **{self.id}** - **{self.title}**: {self.question}{options_text}\n\n➡️ {self.recommended}"


@dataclass
class DraftADR:
    """Represents an Architectural Decision Record drafted during grilling."""
    title: str
    filename: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DomainTermSharpening:
    """Represents a term clarified against CONTEXT.md."""
    fuzzy_term: str
    canonical_term: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodebaseGroundingContext:
    """Encapsulates autonomous codebase facts discovered for grilling."""
    branch: str = "main"
    file_tree: list[str] = field(default_factory=list)
    candidate_contents: dict[str, str] = field(default_factory=dict)


@dataclass
class GrillTurnResult:
    """Structured response for a conversational grilling turn."""
    type: Literal["grill_round", "ready_for_approval", "error"]
    round: int = 1
    questions: list[GrillQuestion] = field(default_factory=list)
    formatted_text: str = ""
    summary: str = ""
    plan: str | None = None
    draft_adr: DraftADR | None = None
    sharpened_terms: list[DomainTermSharpening] = field(default_factory=list)
    context_update: str | None = None
    error_message: str | None = None
    error_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "round": self.round,
            "questions": [q.to_dict() if isinstance(q, GrillQuestion) else q for q in self.questions],
            "formatted_text": self.formatted_text,
            "summary": self.summary,
            "plan": self.plan,
            "draft_adr": self.draft_adr.to_dict() if isinstance(self.draft_adr, DraftADR) else self.draft_adr,
            "sharpened_terms": [t.to_dict() if isinstance(t, DomainTermSharpening) else t for t in self.sharpened_terms],
            "context_update": self.context_update,
            "error_message": self.error_message,
            "error_details": self.error_details,
        }


def resolve_opencode_go_api_key(
    options: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Resolves OpenCode Go API key from options, environment, config file, or SOPS secrets."""
    if options and options.get("api_key"):
        val = str(options["api_key"]).strip()
        if val:
            return val

    # Environment variables
    if os.environ.get("OPENCODE_GO_API_KEY") and os.environ["OPENCODE_GO_API_KEY"].strip():
        return os.environ["OPENCODE_GO_API_KEY"].strip()

    if os.environ.get("OPENCODE_API_KEY") and os.environ["OPENCODE_API_KEY"].strip():
        return os.environ["OPENCODE_API_KEY"].strip()

    # User config file (~/.config/opencode/opencode.env)
    target_env_path = None
    if options and options.get("env_path"):
        target_env_path = Path(options["env_path"])
    else:
        target_env_path = Path.home() / ".config" / "opencode" / "opencode.env"

    if target_env_path and target_env_path.is_file():
        try:
            content = target_env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match_go = re.match(r"^OPENCODE_GO_API_KEY=(.+)$", line)
                if match_go:
                    return match_go.group(1).strip().strip("'\"")
                match_default = re.match(r"^OPENCODE_API_KEY=(.+)$", line)
                if match_default:
                    return match_default.group(1).strip().strip("'\"")
        except Exception:
            pass

    # SOPS encrypted secret in repository root
    try:
        root = resolve_repo_root(repo_root)
        secrets_file = root / "secrets" / "opencode.env"
        if secrets_file.is_file():
            age_key_path = Path.home() / ".config" / "sops" / "age" / "keys.txt"
            env = os.environ.copy()
            if age_key_path.is_file() and "SOPS_AGE_KEY_FILE" not in env:
                env["SOPS_AGE_KEY_FILE"] = str(age_key_path)

            res = subprocess.run(
                ["sops", "-d", str(secrets_file)],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match_go = re.match(r"^OPENCODE_GO_API_KEY=(.+)$", line)
                if match_go:
                    return match_go.group(1).strip().strip("'\"")
    except Exception:
        pass

    return None


def validate_opencode_go_api_key(key: str | None) -> tuple[bool, str | None]:
    """Validates OpenCode Credentials format."""
    if not key or not key.strip():
        return False, "OpenCode Credentials are missing or not configured."
    clean = key.strip()
    if len(clean) < 8 or any(c.isspace() for c in clean):
        return False, f"Invalid OpenCode Credentials format. Token must be at least 8 characters with no whitespace."
    return True, None


def parse_context_terms(context_content: str) -> list[dict[str, Any]]:
    """Extracts defined terms, descriptions, and avoided terms from CONTEXT.md content."""
    terms: list[dict[str, Any]] = []
    # Pattern looks for **Term**: followed by description and optional _Avoid_:
    term_blocks = re.findall(
        r"\*\*([^*]+)\*\*:\s*\n(.*?)(?=\n\*\*[^*]+\*\*:|\Z)",
        context_content,
        re.DOTALL,
    )
    for name, body in term_blocks:
        name_clean = name.strip()
        body_clean = body.strip()
        avoid_matches = re.search(r"_Avoid_:\s*(.+)", body_clean)
        avoid_list = []
        if avoid_matches:
            avoid_list = [a.strip() for a in avoid_matches.group(1).split(",") if a.strip()]
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
            # Check if avoid phrase or token appears in input
            pattern = r"\b" + re.escape(avoid_clean.lower()) + r"\b"
            if re.search(pattern, text_lower):
                sharpened.append({
                    "fuzzy_term": avoid_clean,
                    "canonical_term": canonical,
                    "explanation": f"Your glossary in CONTEXT.md defines '{canonical}' ({item['description'].splitlines()[0]}). Avoid '{avoid_clean}'.",
                })

    # Common domain heuristics for TanStack Start SPA
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


def format_questions_markdown(questions: list[GrillQuestion]) -> str:
    """Formats a list of GrillQuestion instances into canonical grilling markdown."""
    return "\n\n---\n\n".join(q.format_markdown() for q in questions)


PromptArchetype = Literal["deletion", "component_modification", "styling", "new_feature"]


def classify_prompt_archetype(prompt: str) -> PromptArchetype:
    """Classifies user prompt into archetypes to govern grilling frontier and architectural impact."""
    text = prompt.lower().strip()
    if not text:
        return "new_feature"

    # 1. Deletion patterns
    if re.search(r"\b(remove|delete|drop|strip|clean\s*up|clear|prune|eliminate|omit|retire|cut\s*out)\b", text):
        return "deletion"

    # 2. Styling patterns
    if re.search(r"\b(style|styling|theme|dark\s*mode|color|colors|font|fonts|tailwind|padding|margin|spacing|responsive|layout)\b", text):
        return "styling"

    # 3. Component modification patterns
    if re.search(r"\b(modify|update|edit|tweak|replace|fix|refactor|change|adjust|patch|revise|rename)\b", text):
        return "component_modification"

    # 4. Default to new feature
    return "new_feature"


def slugify(text: str) -> str:
    """Converts a phrase into a clean URL-friendly kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "feature-decision"


def compute_next_adr_metadata(repo: str, prompt: str, existing_adrs: list[str] | None = None) -> tuple[int, str, str]:
    """Computes next sequential ADR number, slug, and filename."""
    highest_num = 1
    if existing_adrs:
        for adr in existing_adrs:
            m = re.match(r"^(\d{4})-", Path(adr).name)
            if m:
                highest_num = max(highest_num, int(m.group(1)))

    next_num = highest_num + 1
    # Extract short title from prompt
    words = [w for w in prompt.split() if w.lower() not in {"build", "add", "create", "make", "an", "a", "the", "with"}]
    core_title = " ".join(words[:4]).title() or "Architectural Specification"
    slug = slugify(core_title)
    filename = f"docs/adr/{next_num:04d}-{slug}.md"
    title = f"{next_num:04d}: {core_title}"
    return next_num, title, filename


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


def extract_path_tokens(path: str) -> set[str]:
    """Extracts searchable tokens from a file path."""
    p = Path(path)
    stem = p.stem
    stem_tokens = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)", stem)
    parts = re.split(r"[/\\._-]+", path.lower())
    return set(t.lower() for t in stem_tokens + parts if len(t) > 1)


def score_path_against_keywords(
    path: str,
    direct_keywords: set[str],
    keyword_weights: dict[str, int],
) -> int:
    """Scores a file path based on overlap with prompt keywords and domain associations."""
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
    """Formats file paths into routes, components, and other files summary."""
    routes = [p for p in file_paths if "routes/" in p.lower()]
    components = [p for p in file_paths if "components/" in p.lower()]
    others = [p for p in file_paths if p not in routes and p not in components]

    lines = [f"Branch: {branch}"]
    if routes:
        lines.append("Routes:")
        for route_path in sorted(routes):
            lines.append(f"  - {route_path}")
    if components:
        lines.append("Components:")
        for component_path in sorted(components):
            lines.append(f"  - {component_path}")
    if others:
        lines.append("Other Files:")
        for other_path in sorted(others)[:10]:
            lines.append(f"  - {other_path}")
    return "\n".join(lines)


def format_candidate_sources(candidate_contents: dict[str, str]) -> str:
    """Formats candidate source code bodies for LLM system prompt."""
    if not candidate_contents:
        return "(No candidate component source files matched the prompt keywords)"

    chunks = []
    for path, content in candidate_contents.items():
        ext = Path(path).suffix.lstrip(".") or "tsx"
        chunks.append(f"#### File: `{path}`\n```{ext}\n{content}\n```")
    return "\n\n".join(chunks)


class GrillingAssistant:
    """Conversational reasoning assistant for Factory Studio developer interviewing."""

    def __init__(
        self,
        api_key: str | None = None,
        mock: bool = False,
        repo_root: Path | None = None,
        base_url: str = OPENCODE_GO_DEFAULT_URL,
    ):
        self.repo_root = resolve_repo_root(repo_root)
        self.explicit_mock = bool(mock)
        self.api_key = resolve_opencode_go_api_key(options={"api_key": api_key}, repo_root=self.repo_root)
        self.base_url = base_url.rstrip("/")

    @property
    def is_mock_mode(self) -> bool:
        return bool(self.explicit_mock)

    async def get_repo_context(self, repo: str) -> str:
        """Loads target repository CONTEXT.md content via GitHub or fallback template."""
        token = get_test_org_token(repo_root=self.repo_root)
        clean_repo = strip_repo_owner(repo)
        if token:
            url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{clean_repo}/contents/CONTEXT.md"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.raw+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return resp.text
            except Exception:
                pass
        return CONTEXT_TEMPLATE

    def _resolve_repo_coords(self, repo: str) -> tuple[str, str]:
        """Resolves GitHub owner and clean repo slug, supporting both <repo> and <owner>/<repo>."""
        trimmed = repo.strip()
        if "/" in trimmed:
            parts = trimmed.split("/", 1)
            return parts[0], parts[1]
        return DEFAULT_TEST_ORG, strip_repo_owner(trimmed)

    def _github_headers(self, token: str, raw: bool = False) -> dict[str, str]:
        accept = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SoftwareFactory-Studio/1.0",
        }

    async def get_repo_context(self, repo: str) -> str:
        """Loads target repository CONTEXT.md content via GitHub or fallback template."""
        token = get_test_org_token(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if token:
            url = f"https://api.github.com/repos/{owner}/{clean_repo}/contents/CONTEXT.md"
            headers = self._github_headers(token, raw=True)
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return resp.text
            except Exception:
                pass
        return CONTEXT_TEMPLATE

    async def get_repo_existing_adrs(self, repo: str) -> list[str]:
        """Discovers existing ADRs in the repository."""
        token = get_test_org_token(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if token:
            url = f"https://api.github.com/repos/{owner}/{clean_repo}/contents/docs/adr"
            headers = self._github_headers(token)
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        items = resp.json()
                        if isinstance(items, list):
                            return [item["name"] for item in items if isinstance(item, dict) and item.get("name", "").endswith(".md")]
            except Exception:
                pass
        return ["0001-tanstack-start-spa-architecture.md"]

    async def resolve_active_branch(
        self,
        repo: str,
        milestone_slug: str | None = None,
    ) -> str:
        """Determines target branch, checking for active milestone branches (factory/<milestone>) on GitHub before falling back to main."""
        token = get_test_org_token(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if not token:
            return "main"

        headers = self._github_headers(token)
        url = f"https://api.github.com/repos/{owner}/{clean_repo}/branches?per_page=100"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    branch_items = resp.json()
                    if isinstance(branch_items, list):
                        branch_names = [b.get("name") for b in branch_items if isinstance(b, dict) and b.get("name")]
                        if milestone_slug:
                            target = f"factory/{milestone_slug}"
                            if target in branch_names:
                                return target
                            return "main" if "main" in branch_names else ("master" if "master" in branch_names else "main")
                        factory_branches = [b for b in branch_names if b.startswith("factory/")]
                        if factory_branches:
                            return factory_branches[0]
                        if "main" in branch_names:
                            return "main"
                        if "master" in branch_names:
                            return "master"
        except Exception:
            pass
        return "main"

    async def get_repo_file_tree(
        self,
        repo: str,
        branch: str = "main",
    ) -> list[str]:
        """Queries the recursive Git Tree via GitHub API and returns all blob file paths."""
        token = get_test_org_token(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if not token:
            return FALLBACK_REPO_TREE.copy()

        headers = self._github_headers(token)
        url = f"https://api.github.com/repos/{owner}/{clean_repo}/git/trees/{branch}?recursive=1"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    tree_items = data.get("tree", [])
                    paths = [
                        item["path"]
                        for item in tree_items
                        if isinstance(item, dict) and item.get("type") == "blob" and "path" in item
                    ]
                    if paths:
                        return paths
        except Exception:
            pass
        return FALLBACK_REPO_TREE.copy()

    def score_candidate_files(
        self,
        file_paths: list[str],
        prompt: str,
    ) -> list[str]:
        """Scores repository file paths against keywords and associations extracted from the developer's prompt."""
        clean = prompt.strip().lower()
        raw_tokens = set(re.findall(r"[a-z0-9]+", clean))
        direct_keywords = {k for k in raw_tokens if k not in PROMPT_STOPWORDS and len(k) > 1}

        keyword_weights: dict[str, int] = {}
        for k in direct_keywords:
            if k in KEYWORD_EXPANSIONS:
                for term, weight in KEYWORD_EXPANSIONS[k].items():
                    keyword_weights[term] = keyword_weights.get(term, 0) + weight

        scored: list[tuple[int, str]] = []
        for path in file_paths:
            score = score_path_against_keywords(
                path,
                direct_keywords=direct_keywords,
                keyword_weights=keyword_weights,
            )
            if score > 0:
                scored.append((score, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [path for _, path in scored]

    async def fetch_candidate_file_contents(
        self,
        repo: str,
        file_paths: list[str],
        branch: str = "main",
        max_total_bytes: int = 25000,
    ) -> dict[str, str]:
        """Retrieves raw source code for candidate files from GitHub, respecting count (max 3) and total size budget."""
        token = get_test_org_token(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        results: dict[str, str] = {}
        current_bytes = 0

        candidates = file_paths[:3]

        if not token:
            for path in candidates:
                if current_bytes >= max_total_bytes:
                    break
                content = FALLBACK_FILE_CONTENTS.get(path)
                if content is not None:
                    encoded_len = len(content.encode("utf-8"))
                    if current_bytes + encoded_len <= max_total_bytes:
                        results[path] = content
                        current_bytes += encoded_len
            return results

        headers = self._github_headers(token, raw=True)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for path in candidates:
                if current_bytes >= max_total_bytes:
                    break
                url = f"https://api.github.com/repos/{owner}/{clean_repo}/contents/{path}?ref={branch}"
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        raw_text = resp.text
                        file_bytes = len(raw_text.encode("utf-8"))
                        remaining_budget = max_total_bytes - current_bytes
                        if file_bytes <= remaining_budget:
                            results[path] = raw_text
                            current_bytes += file_bytes
                        else:
                            if remaining_budget > 200:
                                truncated_slice = raw_text[: remaining_budget - 80]
                                truncated_text = f"{truncated_slice}\n\n// ... [truncated to fit 25KB budget]"
                                results[path] = truncated_text
                                current_bytes = max_total_bytes
                            break
                except Exception:
                    pass

        return results

    async def handle_turn(
        self,
        repo: str,
        prompt: str,
        history: list[dict[str, Any]] | None = None,
        model: str = OPENCODE_GO_DEFAULT_MODEL,
        milestone_slug: str | None = None,
        branch: str | None = None,
    ) -> GrillTurnResult:
        """Processes a chat turn against the requirement frontier."""
        chat_history = history or []
        clean_prompt = prompt.strip()

        # In explicit mock mode, proceed immediately without remote network calls
        if self.is_mock_mode:
            sharpened_terms_raw = sharpen_domain_terms(clean_prompt, CONTEXT_TEMPLATE)
            sharpened_terms = [
                DomainTermSharpening(
                    fuzzy_term=s["fuzzy_term"],
                    canonical_term=s["canonical_term"],
                    explanation=s["explanation"],
                )
                for s in sharpened_terms_raw
            ]
            return self._handle_mock_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=CONTEXT_TEMPLATE,
                existing_adrs=["0001-tanstack-start-spa-architecture.md"],
                sharpened_terms=sharpened_terms,
            )

        context_content = await self.get_repo_context(repo)
        existing_adrs = await self.get_repo_existing_adrs(repo)

        sharpened_terms_raw = sharpen_domain_terms(clean_prompt, context_content)
        sharpened_terms = [
            DomainTermSharpening(
                fuzzy_term=s["fuzzy_term"],
                canonical_term=s["canonical_term"],
                explanation=s["explanation"],
            )
            for s in sharpened_terms_raw
        ]

        # Autonomous codebase grounding and fact-finding for live turns
        history_user_text = " ".join(
            m.get("text") or m.get("content") or ""
            for m in chat_history
            if m.get("role") == "user"
        )
        scoring_prompt = f"{history_user_text} {clean_prompt}".strip() if history_user_text else clean_prompt

        target_branch = branch or await self.resolve_active_branch(repo, milestone_slug=milestone_slug)
        file_tree = await self.get_repo_file_tree(repo, branch=target_branch)
        candidate_paths = self.score_candidate_files(file_tree, prompt=scoring_prompt)
        candidate_contents = await self.fetch_candidate_file_contents(
            repo, file_paths=candidate_paths, branch=target_branch
        )
        grounding = CodebaseGroundingContext(
            branch=target_branch,
            file_tree=file_tree,
            candidate_contents=candidate_contents,
        )

        # Ignore prior error turns when calculating current interview round
        def _is_error_history(msg: dict[str, Any]) -> bool:
            t = msg.get("text") or msg.get("content") or ""
            return t.startswith("⚠️ **Inference") or msg.get("type") == "error"

        valid_assistant_turns = [m for m in chat_history if m.get("role") == "assistant" and not _is_error_history(m)]
        current_round = len(valid_assistant_turns) + 1

        is_valid_token, token_err = validate_opencode_go_api_key(self.api_key)
        if not is_valid_token:
            err_msg = token_err or "OpenCode Credentials are missing or not configured."
            details = (
                "No valid OpenCode Credentials resolved from options, OPENCODE_GO_API_KEY environment variable, "
                "~/.config/opencode/opencode.env, or Repository Environment Secrets."
            )
            return GrillTurnResult(
                type="error",
                round=current_round,
                summary=err_msg,
                error_message=err_msg,
                error_details=f"Provider: OpenCode Go ({self.base_url})\n{details}",
                formatted_text=f"⚠️ **Inference Configuration Error**: {err_msg}\n\n{details}",
            )

        # Live OpenCode Go execution
        try:
            return await self._handle_live_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=context_content,
                existing_adrs=existing_adrs,
                sharpened_terms=sharpened_terms,
                model=model,
                grounding=grounding,
            )
        except Exception as exc:
            error_details = f"Provider: OpenCode Go ({self.base_url})\nError: {type(exc).__name__}: {str(exc)}"
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                try:
                    resp_body = exc.response.text
                except Exception:
                    resp_body = ""
                error_msg = f"HTTP {status} error from inference provider: {resp_body or exc}"
                error_details = f"Endpoint: {self.base_url}/chat/completions\nStatus: {status}\nResponse: {resp_body}"
            elif isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                error_msg = f"Network connection error to OpenCode Go: {exc}"
            elif isinstance(exc, httpx.TimeoutException):
                error_msg = f"Inference request timed out: {exc}"
            else:
                error_msg = f"Inference error: {exc}"

            return GrillTurnResult(
                type="error",
                round=current_round,
                summary=error_msg,
                error_message=error_msg,
                error_details=error_details,
                formatted_text=f"⚠️ **Inference Error**: {error_msg}\n\n{error_details}",
            )

    def _handle_mock_turn(
        self,
        repo: str,
        prompt: str,
        history: list[dict[str, Any]],
        context_content: str,
        existing_adrs: list[str],
        sharpened_terms: list[DomainTermSharpening],
    ) -> GrillTurnResult:
        """Deterministic mock interview progression for offline and testing execution."""
        assistant_turns = [m for m in history if m.get("role") == "assistant"]
        current_round = len(assistant_turns) + 1

        is_shortcut = prompt.lower() in {"/proceed", "proceed", "approve", "/approve", "yes", "accept defaults"}

        # Identify effective prompt from history if current prompt is shortcut/affirmation/answer
        effective_prompt = prompt
        user_prompts = [
            m.get("text") or m.get("content") or ""
            for m in history
            if m.get("role") == "user" and (m.get("text") or m.get("content"))
        ]
        if user_prompts and (is_shortcut or current_round >= 2):
            effective_prompt = user_prompts[0].strip()

        archetype = classify_prompt_archetype(effective_prompt)
        clean_title = effective_prompt.strip().rstrip(".!?").capitalize()

        # If user explicitly approves or we are in round 2+, settle the frontier
        if is_shortcut or current_round >= 2:
            draft_adr: DraftADR | None = None
            if archetype == "deletion":
                plan = f"""# Implementation Plan: {clean_title}

1. **Target Component**: Locate and remove specified elements in existing component (e.g. `app/components/Footer.tsx`).
2. **Layout Reflow**: Adjust flexbox/grid containers and padding to ensure clean visual flow without residual whitespace.
3. **Asset Pruning**: Remove unused icon imports, attributes, and dead references.
4. **Verification**: Verify component renders cleanly and tests pass.
"""
                summary = "Deletion scope confirmed and layout reflow requirements settled. Ready for build approval."
                formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

            elif archetype == "component_modification":
                plan = f"""# Implementation Plan: {clean_title}

1. **Component Modification**: Update existing component logic and markup in `app/components/`.
2. **Props & State**: Adjust localized component props and state cleanly.
3. **Visual Alignment**: Maintain consistent layout, design tokens, and accessibility.
4. **Verification**: Verify component behavior and test suite pass without regressions.
"""
                summary = "Component modification scope clarified and requirements aligned. Ready for build approval."
                formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

            elif archetype == "styling":
                plan = f"""# Implementation Plan: {clean_title}

1. **Styling Adjustments**: Apply responsive Tailwind CSS utility classes to target elements.
2. **Visual Consistency**: Verify color contrast, padding, and layout across breakpoints.
3. **Accessibility**: Ensure interactive elements maintain accessible focus states and contrast ratios.
4. **Verification**: Verify visual appearance and responsive layout in preview.
"""
                summary = "Styling requirements and design tokens aligned. Ready for build approval."
                formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

            else:  # new_feature
                num, title, filename = compute_next_adr_metadata(repo, effective_prompt, existing_adrs)
                feature_slug = slugify(effective_prompt)

                content = f"""# {title}

**Status**: Proposed

To implement {effective_prompt} within {repo}, we decided to adopt type-safe file routing and client state caching conforming to the target application domain context.

## Considered Options

- **External Serverless Storage / Database**: Rejected because target applications are single-page frontend applications with client-first state.
- **In-Memory Client State with TanStack Query**: Accepted to maintain fast reactivity, offline resilience, and zero backend maintenance.

## Consequences

- Implemented under `app/routes/{feature_slug}.tsx`.
- State managed strictly through Client State primitives without external database dependencies.
- Styled using responsive Tailwind CSS utility tokens.
"""
                draft_adr = DraftADR(
                    title=title,
                    filename=filename,
                    content=content,
                )

                plan = f"""# Implementation Plan: {title}

1. **Route Hierarchy**: Create new route `app/routes/{feature_slug}.tsx` with typed loader and params.
2. **Client State**: Manage UI and domain state using React primitives and TanStack Query cache.
3. **Responsive UI**: Construct clean, accessible components styled with Tailwind CSS tokens.
4. **Architectural Verification**: Ensure code adheres strictly to `{filename}` and `CONTEXT.md`.
"""
                summary = "Requirements clarified, domain terminology aligned with CONTEXT.md, and draft ADR synthesized. Ready for build approval."
                formatted_text = f"### Finalized Implementation Plan\n\n{plan}\n\n**Draft ADR Ready**: [{filename}](#adr-preview)"

            return GrillTurnResult(
                type="ready_for_approval",
                round=current_round,
                questions=[],
                formatted_text=formatted_text,
                summary=summary,
                plan=plan,
                draft_adr=draft_adr,
                sharpened_terms=sharpened_terms,
            )

        # Round 1: Generate frontier questions with recommended answers based on archetype
        if archetype == "deletion":
            questions = [
                GrillQuestion(
                    id="Q1",
                    title="Component Scope",
                    question="Which component contains the elements to be removed?",
                    recommended="Target existing component (e.g. `app/components/Footer.tsx` or `Header.tsx`) where the elements reside.",
                    options=[
                        "Existing component in app/components/ (Recommended)",
                        "All navigation and footer components",
                        "Global layout component",
                    ],
                ),
                GrillQuestion(
                    id="Q2",
                    title="Layout & Spacing Reflow",
                    question="How should surrounding layout and spacing adjust after removing these elements?",
                    recommended="Reflow the container cleanly without leaving residual gaps, empty wrappers, or awkward whitespace.",
                    options=[
                        "Clean reflow without residual whitespace (Recommended)",
                        "Retain layout bounds with centered copyright text",
                        "Collapse container height",
                    ],
                ),
                GrillQuestion(
                    id="Q3",
                    title="Asset & Dependency Pruning",
                    question="Should unused icons, external assets, or link definitions be pruned?",
                    recommended="Remove unused icon imports and dead link configurations to keep component code clean.",
                    options=[
                        "Prune unused imports and assets (Recommended)",
                        "Retain imports for future re-use",
                    ],
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
                    options=[
                        "Update existing component in app/components/ (Recommended)",
                        "Extract to a new sub-component",
                    ],
                ),
                GrillQuestion(
                    id="Q2",
                    title="State & Props Behavior",
                    question="How should component props or state react to this change?",
                    recommended="Keep state updates localized to the component or existing TanStack Query cache.",
                    options=[
                        "Localized component state (Recommended)",
                        "Lift state to parent component",
                    ],
                ),
                GrillQuestion(
                    id="Q3",
                    title="Component Interface",
                    question="Should existing component props and usages remain backward compatible?",
                    recommended="Maintain backward compatibility for existing callers while adding the requested adjustments.",
                    options=[
                        "Maintain backward compatible props (Recommended)",
                        "Refactor callers immediately",
                    ],
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
                    options=[
                        "Responsive Tailwind CSS utility classes (Recommended)",
                        "Custom CSS class overrides",
                    ],
                ),
                GrillQuestion(
                    id="Q2",
                    title="Responsive & Theme Support",
                    question="How should theme adjustments and responsive breakpoints be handled?",
                    recommended="Ensure consistent contrast in light/dark themes and responsive behavior across mobile and desktop.",
                    options=[
                        "Consistent contrast across themes and mobile/desktop (Recommended)",
                        "Desktop-only layout adjustment",
                    ],
                ),
                GrillQuestion(
                    id="Q3",
                    title="Component Styling Scope",
                    question="Are styling adjustments localized to specific components or global?",
                    recommended="Apply styling adjustments directly to the target component without modifying global base stylesheets.",
                    options=[
                        "Target component only (Recommended)",
                        "Global theme variables in CSS",
                    ],
                ),
            ]
            summary = "Aligned styling requirements and design tokens. Please review recommended defaults."

        else:  # new_feature
            feature_slug = slugify(effective_prompt)
            questions = [
                GrillQuestion(
                    id="Q1",
                    title="Route Placement",
                    question="Where in the application Route Tree should this feature be mounted?",
                    recommended=f"Add a dedicated typed route under `app/routes/{feature_slug}.tsx` adhering to TanStack Start conventions.",
                    options=[
                        f"Dedicated route at app/routes/{feature_slug}.tsx (Recommended)",
                        "Sub-route nested within existing view",
                        "Modal overlay on root dashboard",
                    ],
                ),
                GrillQuestion(
                    id="Q2",
                    title="State Management & Persistence",
                    question="How should application state and filters for this feature be managed?",
                    recommended="Manage state using React primitives and TanStack Query in-memory cache, keeping the application a clean stateless client SPA.",
                    options=[
                        "TanStack Query in-memory cache and React state (Recommended)",
                        "Browser localStorage persistence",
                        "Session storage",
                    ],
                ),
                GrillQuestion(
                    id="Q3",
                    title="Visual Design & Layout",
                    question="What layout structure and styling system should be applied?",
                    recommended="Construct responsive components styled with Tailwind CSS utility classes matching existing design tokens.",
                    options=[
                        "Responsive Tailwind CSS utility classes (Recommended)",
                        "Full-bleed data dashboard with dark mode accents",
                    ],
                ),
            ]
            summary = "Identified unsettled decisions on the requirement frontier. Please review the recommended defaults or provide custom specifications."

        formatted_text = format_questions_markdown(questions)
        return GrillTurnResult(
            type="grill_round",
            round=1,
            questions=questions,
            formatted_text=formatted_text,
            summary=summary,
            plan=None,
            draft_adr=None,
            sharpened_terms=sharpened_terms,
        )

    async def _handle_live_turn(
        self,
        repo: str,
        prompt: str,
        history: list[dict[str, Any]],
        context_content: str,
        existing_adrs: list[str],
        sharpened_terms: list[DomainTermSharpening],
        model: str,
        grounding: CodebaseGroundingContext | None = None,
        branch: str | None = None,
        file_tree: list[str] | None = None,
        candidate_contents: dict[str, str] | None = None,
    ) -> GrillTurnResult:
        """Executes conversational turn against OpenCode Go inference API."""
        if grounding is not None:
            active_branch = grounding.branch
            tree_paths = grounding.file_tree
            contents = grounding.candidate_contents
        else:
            active_branch = branch or "main"
            tree_paths = file_tree or []
            contents = candidate_contents or {}

        formatted_structure = format_repo_structure_summary(tree_paths, active_branch)
        formatted_sources = format_candidate_sources(contents)

        system_instruction = f"""You are the Factory Studio Grilling Assistant for the repository '{repo}'.
You follow Matt Pocock's grilling and domain-modeling protocols.

Target Application CONTEXT.md:
\"\"\"
{context_content}
\"\"\"

Existing ADRs in docs/adr/:
{json.dumps(existing_adrs)}

### Repository Codebase Structure:
{formatted_structure}

### Relevant Candidate Component Source Code:
{formatted_sources}

Rules:
1. Codebase Grounding & Fact-Finding: Finding facts is YOUR job as the agent, not the developer's job. Inspect the provided Repository Codebase Structure and Relevant Candidate Component Source Code.
2. Ground all questions directly in existing components and files whenever possible.
3. Component Modifications and Deletions: If the user prompt modifies, styles, refactors, or deletes elements in existing UI components (such as removing social media links, updating headers, changing footer text, or styling cards):
   - You MUST formulate questions focused on the existing components (e.g. `Footer.tsx` or `Header.tsx`).
   - You MUST forbid proposing new route files (e.g. `app/routes/<action-slug>.tsx`) or asking where in the route tree to mount the modification, unless the developer explicitly asks for a new page, screen, or route.
4. Interview the developer relentlessly in rounds using the design tree.
5. Identify unsettled prerequisites on the requirement frontier.
6. Every question MUST have an id ('Q1', 'Q2', etc.), title, question body, and RECOMMENDED answer:
   Format each question as:
   ❓ **Q1** - **<title>**: <question>
   ➡️ <recommended answer>
7. Sharpen domain terms against CONTEXT.md glossary. Never silently violate glossary language.
8. When the frontier is resolved (or when user accepts defaults/replies to questions), transition to 'ready_for_approval':
   - Synthesize a concise implementation plan referencing target components to modify
   - Offer ADRs sparingly: Draft an Architectural Decision Record in markdown (Status: Proposed) ONLY when the change introduces irreversible, fundamental, or significant architectural trade-offs (e.g. introducing new routing paradigms, external storage/databases, state management libraries, third-party service architectures, or structural framework patterns).
   - For localized component modifications, deletions, refactors, bug fixes, or styling changes, set `draft_adr` to null and synthesize only the implementation plan.
9. Output MUST be valid JSON adhering strictly to one of these two structures:

For interview round:
{{
  "type": "grill_round",
  "round": <number>,
  "summary": "<short summary>",
  "questions": [
    {{
      "id": "Q1",
      "title": "<title>",
      "question": "<question>",
      "recommended": "<recommended answer>",
      "options": ["<opt1>", "<opt2>"]
    }}
  ]
}}

For ready for approval:
{{
  "type": "ready_for_approval",
  "round": <number>,
  "summary": "<short summary>",
  "plan": "<implementation plan markdown>",
  "draft_adr": {{
    "title": "<adr title>",
    "filename": "docs/adr/NNNN-<slug>.md",
    "content": "<adr markdown content>"
  }} | null
}}
"""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_instruction}]

        for msg in history:
            role = msg.get("role")
            text = msg.get("text") or msg.get("content") or ""
            if role in ("user", "assistant") and text:
                if text.startswith("⚠️ **Inference"):
                    continue
                messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "x-opencode-session": f"studio-{repo}",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]

            # Parse content (stripping markdown fences if present)
            clean_json = raw_content.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\n", "", clean_json)
                clean_json = re.sub(r"\n```$", "", clean_json)

            parsed = json.loads(clean_json)

            turn_type = parsed.get("type", "grill_round")
            turn_round = int(parsed.get("round", len(history) + 1))
            summary = parsed.get("summary", "")

            if turn_type == "ready_for_approval":
                draft_adr_data = parsed.get("draft_adr")
                draft_adr: DraftADR | None = None
                if (
                    isinstance(draft_adr_data, dict)
                    and draft_adr_data.get("filename")
                    and draft_adr_data.get("content")
                ):
                    draft_adr = DraftADR(
                        title=draft_adr_data.get("title", "Proposed ADR"),
                        filename=draft_adr_data.get("filename", "docs/adr/0002-feature.md"),
                        content=draft_adr_data.get("content", ""),
                    )
                plan = parsed.get("plan", "")
                formatted_text = f"### Finalized Implementation Plan\n\n{plan}"
                if draft_adr:
                    formatted_text += f"\n\n**Draft ADR Ready**: [{draft_adr.filename}](#adr-preview)"
                return GrillTurnResult(
                    type="ready_for_approval",
                    round=turn_round,
                    questions=[],
                    formatted_text=formatted_text,
                    summary=summary,
                    plan=plan,
                    draft_adr=draft_adr,
                    sharpened_terms=sharpened_terms,
                )

            questions_data = parsed.get("questions") or []
            questions: list[GrillQuestion] = []
            for q in questions_data:
                questions.append(
                    GrillQuestion(
                        id=q.get("id", f"Q{len(questions) + 1}"),
                        title=q.get("title", "Question"),
                        question=q.get("question", ""),
                        recommended=q.get("recommended", ""),
                        options=q.get("options", []),
                    )
                )

            formatted_text = format_questions_markdown(questions)
            return GrillTurnResult(
                type="grill_round",
                round=turn_round,
                questions=questions,
                formatted_text=formatted_text,
                summary=summary,
                plan=None,
                draft_adr=None,
                sharpened_terms=sharpened_terms,
            )
