"""OpenCode Go inference client, API key resolution, prompt construction, and execution."""

import json
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import httpx

from factory.ui.github import resolve_repo_root
from factory.ui.grill._models import (
    CodebaseGroundingContext,
    DraftADR,
    DomainTermSharpening,
    GrillQuestion,
    GrillTurnResult,
)
from factory.ui.grill._prompts import render_prompt_template

logger = logging.getLogger(__name__)


def resolve_opencode_go_api_key(
    options: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Resolves OpenCode Go API key from options, environment, config file, or SOPS secrets."""
    if options and options.get("api_key"):
        val = str(options["api_key"]).strip()
        if val:
            return val

    if os.environ.get("OPENCODE_GO_API_KEY") and os.environ["OPENCODE_GO_API_KEY"].strip():
        return os.environ["OPENCODE_GO_API_KEY"].strip()

    if os.environ.get("OPENCODE_API_KEY") and os.environ["OPENCODE_API_KEY"].strip():
        return os.environ["OPENCODE_API_KEY"].strip()

    target_env_path = Path(options["env_path"]) if (options and options.get("env_path")) else (Path.home() / ".config" / "opencode" / "opencode.env")
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
        return False, "Invalid OpenCode Credentials format. Token must be at least 8 characters with no whitespace."
    return True, None


def build_system_instruction(
    repo: str,
    context_content: str,
    existing_adrs: list[str],
    formatted_structure: str,
    formatted_sources: str,
) -> str:
    """Builds the comprehensive LLM system prompt following Matt Pocock's grilling protocols."""
    return render_prompt_template(
        "grilling_assistant",
        {
            "repo": repo,
            "context_content": context_content,
            "existing_adrs": json.dumps(existing_adrs),
            "formatted_structure": formatted_structure,
            "formatted_sources": formatted_sources,
        },
    )


async def execute_live_inference(
    base_url: str,
    api_key: str,
    repo: str,
    prompt: str,
    history: list[dict[str, Any]],
    system_instruction: str,
    model: str,
    sharpened_terms: list[DomainTermSharpening],
) -> GrillTurnResult:
    """Dispatches chat completions request to inference API and parses the response."""
    from factory.ui.grill._adr_drafting import format_questions_markdown

    messages: list[dict[str, str]] = [{"role": "system", "content": system_instruction}]
    for msg in history:
        role = msg.get("role")
        text = msg.get("text") or msg.get("content") or ""
        if role in ("user", "assistant") and text and not text.startswith("⚠️ **Inference"):
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
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
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw_content = data["choices"][0]["message"]["content"]

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
            if isinstance(draft_adr_data, dict) and draft_adr_data.get("filename") and draft_adr_data.get("content"):
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
        questions = [
            GrillQuestion(
                id=q.get("id", f"Q{i + 1}"),
                title=q.get("title", "Question"),
                question=q.get("question", ""),
                recommended=q.get("recommended", ""),
                options=q.get("options", []),
            )
            for i, q in enumerate(questions_data)
        ]
        return GrillTurnResult(
            type="grill_round",
            round=turn_round,
            questions=questions,
            formatted_text=format_questions_markdown(questions),
            summary=summary,
            plan=None,
            draft_adr=None,
            sharpened_terms=sharpened_terms,
        )
