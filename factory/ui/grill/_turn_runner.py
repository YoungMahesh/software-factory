"""Conversational interview runner, frontier extraction, round management, and turn orchestration."""

import logging
from pathlib import Path
import sys
from typing import Any
import httpx

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, resolve_repo_root, strip_repo_owner
from factory.ui.scaffold import CONTEXT_TEMPLATE
from factory.ui.grill._adr_drafting import format_questions_markdown, synthesize_mock_plan_and_adr
from factory.ui.grill._archetypes import (
    FALLBACK_FILE_CONTENTS,
    FALLBACK_REPO_TREE,
    KEYWORD_EXPANSIONS,
    PROMPT_STOPWORDS,
    classify_prompt_archetype,
    format_candidate_sources,
    format_repo_structure_summary,
    get_mock_frontier_questions,
    score_path_against_keywords,
    sharpen_domain_terms,
)
from factory.ui.grill._inference import (
    build_system_instruction,
    execute_live_inference,
    resolve_opencode_go_api_key,
    validate_opencode_go_api_key,
)
from factory.ui.grill._models import (
    OPENCODE_GO_DEFAULT_MODEL,
    OPENCODE_GO_DEFAULT_URL,
    CodebaseGroundingContext,
    DomainTermSharpening,
    GrillTurnResult,
)

logger = logging.getLogger(__name__)


def _get_pkg():
    return sys.modules.get("factory.ui.grill")


class GrillingAssistant:
    """Conversational reasoning assistant for Factory Studio developer interviewing."""

    def __init__(
        self,
        api_key: str | None = None,
        mock: bool = False,
        repo_root: Path | None = None,
        base_url: str = OPENCODE_GO_DEFAULT_URL,
    ):
        pkg = _get_pkg()
        resolve_key_fn = getattr(pkg, "resolve_opencode_go_api_key", resolve_opencode_go_api_key) if pkg else resolve_opencode_go_api_key

        self.repo_root = resolve_repo_root(repo_root)
        self.explicit_mock = bool(mock)
        self.api_key = resolve_key_fn(options={"api_key": api_key}, repo_root=self.repo_root)
        self.base_url = base_url.rstrip("/")

    @property
    def is_mock_mode(self) -> bool:
        return bool(self.explicit_mock)

    def _resolve_repo_coords(self, repo: str) -> tuple[str, str]:
        trimmed = repo.strip()
        if "/" in trimmed:
            parts = trimmed.split("/", 1)
            return parts[0], parts[1]
        return DEFAULT_TEST_ORG, strip_repo_owner(trimmed)

    def _github_headers(self, token: str, raw: bool = False) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SoftwareFactory-Studio/1.0",
        }

    async def get_repo_context(self, repo: str) -> str:
        """Loads target repository CONTEXT.md content via GitHub or fallback template."""
        pkg = _get_pkg()
        token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
        token = token_fn(repo_root=self.repo_root)
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
        pkg = _get_pkg()
        token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
        token = token_fn(repo_root=self.repo_root)
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
        pkg = _get_pkg()
        token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
        token = token_fn(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if not token:
            return "main"

        url = f"https://api.github.com/repos/{owner}/{clean_repo}/branches?per_page=100"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self._github_headers(token))
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
        pkg = _get_pkg()
        token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
        token = token_fn(repo_root=self.repo_root)
        owner, clean_repo = self._resolve_repo_coords(repo)
        if not token:
            return FALLBACK_REPO_TREE.copy()

        url = f"https://api.github.com/repos/{owner}/{clean_repo}/git/trees/{branch}?recursive=1"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=self._github_headers(token))
                if resp.status_code == 200:
                    tree_items = resp.json().get("tree", [])
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
        import re
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
            score = score_path_against_keywords(path, direct_keywords=direct_keywords, keyword_weights=keyword_weights)
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
        pkg = _get_pkg()
        token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
        token = token_fn(repo_root=self.repo_root)
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
                                results[path] = f"{truncated_slice}\n\n// ... [truncated to fit 25KB budget]"
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
        chat_history = history or []
        clean_prompt = prompt.strip()

        if self.is_mock_mode:
            sharpened = [
                DomainTermSharpening(fuzzy_term=s["fuzzy_term"], canonical_term=s["canonical_term"], explanation=s["explanation"])
                for s in sharpen_domain_terms(clean_prompt, CONTEXT_TEMPLATE)
            ]
            return self._handle_mock_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=CONTEXT_TEMPLATE,
                existing_adrs=["0001-tanstack-start-spa-architecture.md"],
                sharpened_terms=sharpened,
            )

        context_content = await self.get_repo_context(repo)
        existing_adrs = await self.get_repo_existing_adrs(repo)
        sharpened = [
            DomainTermSharpening(fuzzy_term=s["fuzzy_term"], canonical_term=s["canonical_term"], explanation=s["explanation"])
            for s in sharpen_domain_terms(clean_prompt, context_content)
        ]

        history_user_text = " ".join(
            m.get("text") or m.get("content") or ""
            for m in chat_history
            if m.get("role") == "user"
        )
        scoring_prompt = f"{history_user_text} {clean_prompt}".strip() if history_user_text else clean_prompt
        target_branch = branch or await self.resolve_active_branch(repo, milestone_slug=milestone_slug)
        file_tree = await self.get_repo_file_tree(repo, branch=target_branch)
        candidate_paths = self.score_candidate_files(file_tree, prompt=scoring_prompt)
        candidate_contents = await self.fetch_candidate_file_contents(repo, file_paths=candidate_paths, branch=target_branch)
        grounding = CodebaseGroundingContext(
            branch=target_branch,
            file_tree=file_tree,
            candidate_contents=candidate_contents,
        )

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

        try:
            return await self._handle_live_turn(
                repo=repo,
                prompt=clean_prompt,
                history=chat_history,
                context_content=context_content,
                existing_adrs=existing_adrs,
                sharpened_terms=sharpened,
                model=model,
                grounding=grounding,
            )
        except Exception as exc:
            error_details = f"Provider: OpenCode Go ({self.base_url})\nError: {type(exc).__name__}: {str(exc)}"
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                resp_body = exc.response.text if hasattr(exc.response, "text") else ""
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
        assistant_turns = [m for m in history if m.get("role") == "assistant"]
        current_round = len(assistant_turns) + 1
        is_shortcut = prompt.lower() in {"/proceed", "proceed", "approve", "/approve", "yes", "accept defaults"}

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

        if is_shortcut or current_round >= 2:
            plan, summary, formatted_text, draft_adr = synthesize_mock_plan_and_adr(
                repo=repo,
                clean_title=clean_title,
                effective_prompt=effective_prompt,
                archetype=archetype,
                existing_adrs=existing_adrs,
            )
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

        questions, summary = get_mock_frontier_questions(archetype, effective_prompt)
        return GrillTurnResult(
            type="grill_round",
            round=1,
            questions=questions,
            formatted_text=format_questions_markdown(questions),
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

        system_instruction = build_system_instruction(
            repo=repo,
            context_content=context_content,
            existing_adrs=existing_adrs,
            formatted_structure=formatted_structure,
            formatted_sources=formatted_sources,
        )

        return await execute_live_inference(
            base_url=self.base_url,
            api_key=self.api_key,
            repo=repo,
            prompt=prompt,
            history=history,
            system_instruction=system_instruction,
            model=model,
            sharpened_terms=sharpened_terms,
        )
