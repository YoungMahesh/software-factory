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

OPENCODE_GO_DEFAULT_URL = "https://api.opencode.net/v1"
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
class GrillTurnResult:
    """Structured response for a conversational grilling turn."""
    type: Literal["grill_round", "ready_for_approval"]
    round: int = 1
    questions: list[GrillQuestion] = field(default_factory=list)
    formatted_text: str = ""
    summary: str = ""
    plan: str | None = None
    draft_adr: DraftADR | None = None
    sharpened_terms: list[DomainTermSharpening] = field(default_factory=list)
    context_update: str | None = None

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
        self.explicit_mock = mock
        self.api_key = resolve_opencode_go_api_key(options={"api_key": api_key}, repo_root=self.repo_root)
        self.base_url = base_url.rstrip("/")

    @property
    def is_mock_mode(self) -> bool:
        return self.explicit_mock or not self.api_key

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

    async def get_repo_existing_adrs(self, repo: str) -> list[str]:
        """Discovers existing ADRs in the repository."""
        token = get_test_org_token(repo_root=self.repo_root)
        clean_repo = strip_repo_owner(repo)
        if token:
            url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{clean_repo}/contents/docs/adr"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
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

    async def handle_turn(
        self,
        repo: str,
        prompt: str,
        history: list[dict[str, Any]] | None = None,
        model: str = OPENCODE_GO_DEFAULT_MODEL,
    ) -> GrillTurnResult:
        """Processes a chat turn against the requirement frontier."""
        chat_history = history or []
        clean_prompt = prompt.strip()
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

        if self.is_mock_mode:
            return self._handle_mock_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=context_content,
                existing_adrs=existing_adrs,
                sharpened_terms=sharpened_terms,
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
            )
        except Exception:
            # Resilient fallback to deterministic mock mode on remote errors
            return self._handle_mock_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=context_content,
                existing_adrs=existing_adrs,
                sharpened_terms=sharpened_terms,
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
        # Calculate interview depth from history
        assistant_turns = [m for m in history if m.get("role") == "assistant"]
        current_round = len(assistant_turns) + 1

        is_shortcut = prompt.lower() in {"/proceed", "proceed", "approve", "/approve", "yes", "accept defaults"}

        # If user explicitly approves or we are in round 2+, settle the frontier and finalize draft ADR
        if is_shortcut or current_round >= 2:
            num, title, filename = compute_next_adr_metadata(repo, prompt, existing_adrs)
            feature_slug = slugify(prompt)

            content = f"""# {title}

**Status**: Proposed

To implement {prompt} within {repo}, we decided to adopt type-safe file routing and client state caching conforming to the target application domain context.

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

        # Round 1: Generate frontier questions with recommended answers
        feature_slug = slugify(prompt)
        q1 = GrillQuestion(
            id="Q1",
            title="Route Placement",
            question="Where in the application Route Tree should this feature be mounted?",
            recommended=f"Add a dedicated typed route under `app/routes/{feature_slug}.tsx` adhering to TanStack Start conventions.",
            options=[
                f"Dedicated route at app/routes/{feature_slug}.tsx (Recommended)",
                "Sub-route nested within existing view",
                "Modal overlay on root dashboard",
            ],
        )

        q2 = GrillQuestion(
            id="Q2",
            title="State Management & Persistence",
            question="How should application state and filters for this feature be managed?",
            recommended="Manage state using React primitives and TanStack Query in-memory cache, keeping the application a clean stateless client SPA.",
            options=[
                "TanStack Query in-memory cache and React state (Recommended)",
                "Browser localStorage persistence",
                "Session storage",
            ],
        )

        q3 = GrillQuestion(
            id="Q3",
            title="Visual Design & Layout",
            question="What layout structure and styling system should be applied?",
            recommended="Construct responsive components styled with Tailwind CSS utility classes matching existing design tokens.",
            options=[
                "Responsive Tailwind CSS utility classes (Recommended)",
                "Full-bleed data dashboard with dark mode accents",
            ],
        )

        questions = [q1, q2, q3]
        formatted_text = format_questions_markdown(questions)
        summary = "Identified unsettled decisions on the requirement frontier. Please review the recommended defaults or provide custom specifications."

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
    ) -> GrillTurnResult:
        """Executes conversational turn against OpenCode Go inference API."""
        system_instruction = f"""You are the Factory Studio Grilling Assistant for the repository '{repo}'.
You follow Matt Pocock's grilling and domain-modeling protocols.

Target Application CONTEXT.md:
\"\"\"
{context_content}
\"\"\"

Existing ADRs in docs/adr/:
{json.dumps(existing_adrs)}

Rules:
1. Interview the developer relentlessly in rounds using the design tree.
2. Identify unsettled prerequisites on the requirement frontier.
3. Every question MUST have an id ('Q1', 'Q2', etc.), title, question body, and RECOMMENDED answer:
   Format each question as:
   ❓ **Q1** - **<title>**: <question>
   ➡️ <recommended answer>
4. Sharpen domain terms against CONTEXT.md glossary. Never silently violate glossary language.
5. When the frontier is resolved (or when user accepts defaults/replies to questions), transition to 'ready_for_approval':
   - Synthesize a concise implementation plan
   - Draft an Architectural Decision Record in markdown (Status: Proposed) with title, filename (docs/adr/NNNN-<slug>.md), and content.
6. Output MUST be valid JSON adhering strictly to one of these two structures:

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
  }}
}}
"""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_instruction}]

        for msg in history:
            role = msg.get("role")
            text = msg.get("text") or ""
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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
                draft_adr_data = parsed.get("draft_adr") or {}
                draft_adr = DraftADR(
                    title=draft_adr_data.get("title", "Proposed ADR"),
                    filename=draft_adr_data.get("filename", "docs/adr/0002-feature.md"),
                    content=draft_adr_data.get("content", ""),
                )
                plan = parsed.get("plan", "")
                return GrillTurnResult(
                    type="ready_for_approval",
                    round=turn_round,
                    questions=[],
                    formatted_text=f"### Finalized Implementation Plan\n\n{plan}",
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
