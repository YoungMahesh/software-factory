"""Free-model OpenCode CLI backend for structuring Scratchpad notes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Sequence

from ._slug import strip_leading_h1

FREE_SCRATCHPAD_MODELS: tuple[str, ...] = (
    "opencode/mimo-v2.6-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/big-pickle",
    "opencode/nemotron-3.5-lightning-free",
)
DEFAULT_OPENCODE_TIMEOUT_SECS = 45
MAX_RAW_NOTE_CHARS = 32_000
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)

_PROMPT_TEMPLATE = """You are a crisp technical product & engineering editor.
Turn the user's raw Scratchpad idea into a clear, well-structured Markdown note while preserving ALL concrete requirements, constraints, file paths, APIs, and details from the input. Do not invent unrelated requirements.

Return ONLY a valid JSON object (no markdown fences, no commentary outside JSON) with exactly two string keys:
- "title": Concise descriptive title (2 to 7 words, Title Case, no leading '#').
- "content": Clean, structured Markdown body starting directly with level-2 headings (e.g. "## Overview", "## Requirements", "## Open Questions" as appropriate). Do NOT repeat the top-level "# Title" heading inside "content".

{title_hint_block}Raw idea:
{raw_text}"""


@dataclass(frozen=True)
class ScratchpadSuggestion:
    """Structured AI suggestion for a Scratchpad note."""

    title: str
    content: str
    model: str


def resolve_opencode_binary(explicit_path: str | None = None) -> str:
    """Locates the OpenCode CLI executable on PATH or standard install paths."""
    candidates = [
        explicit_path,
        os.environ.get("OPENCODE_BIN"),
        shutil.which("opencode"),
        "/root/.opencode/bin/opencode",
        str(Path.home() / ".opencode" / "bin" / "opencode"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError(
        "OpenCode CLI binary not found. Ensure /root/.opencode/bin/opencode is installed in the control-plane image."
    )


def _extract_text_from_opencode_ndjson(stdout: str) -> str:
    """Extracts concatenated assistant text chunks from `opencode run --format json` NDJSON output."""
    chunks: list[str] = []
    for raw_line in (stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "text":
            part = event.get("part")
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "".join(chunks).strip()


def _parse_suggestion_payload(raw_output: str) -> tuple[str, str]:
    """Parses JSON {'title', 'content'} from assistant text, stripping accidental code fences."""
    cleaned = (raw_output or "").strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    parsed = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Model response did not contain a JSON object.")

    title = " ".join(str(parsed.get("title") or "").strip().splitlines()).strip()
    title = title.lstrip("#").strip()
    content = str(parsed.get("content") or "").strip()
    content = strip_leading_h1(content)
    if not title or not content:
        raise ValueError("Model JSON must contain non-empty 'title' and 'content' fields.")
    return title, content


def _run_opencode_free_model(
    opencode_bin: str,
    model: str,
    prompt: str,
    timeout_secs: int,
) -> tuple[str, str]:
    """Invokes `opencode run --format json` in an isolated temporary HOME with free Zen model."""
    with tempfile.TemporaryDirectory(prefix="sf-scratchpad-") as tmp_home:
        home_path = Path(tmp_home)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("OPENCODE_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_CONFIG")
        }
        env.update(
            {
                "HOME": str(home_path),
                "XDG_CONFIG_HOME": str(home_path / ".config"),
                "XDG_DATA_HOME": str(home_path / ".local" / "share"),
                "XDG_STATE_HOME": str(home_path / ".local" / "state"),
                "OPENCODE_CONFIG_CONTENT": '{"mcp":{},"lsp":false}',
                "NO_COLOR": "1",
            }
        )
        res = subprocess.run(
            [opencode_bin, "run", "--format", "json", "-m", model, prompt],
            cwd=str(home_path),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_secs,
            check=False,
        )
        if res.returncode != 0:
            err_detail = (res.stderr or res.stdout or f"exit code {res.returncode}").strip()
            raise RuntimeError(f"OpenCode CLI failed for '{model}': {err_detail[:300]}")
        text = _extract_text_from_opencode_ndjson(res.stdout)
        if not text:
            raise RuntimeError(f"OpenCode CLI returned empty assistant output for '{model}'.")
        title, content = _parse_suggestion_payload(text)
        return title, content


def suggest_scratchpad_note(
    raw_text: str,
    *,
    title_hint: str | None = None,
    models: Sequence[str] | None = None,
    opencode_bin: str | None = None,
    timeout_secs: int = DEFAULT_OPENCODE_TIMEOUT_SECS,
) -> ScratchpadSuggestion:
    """Generates an improved Markdown note and title from raw_text using free OpenCode models."""
    cleaned_input = (raw_text or "").strip()
    if not cleaned_input:
        raise ValueError("Scratchpad text cannot be empty.")
    if len(cleaned_input) > MAX_RAW_NOTE_CHARS:
        raise ValueError(f"Scratchpad text exceeds {MAX_RAW_NOTE_CHARS} characters.")

    binary = resolve_opencode_binary(opencode_bin)
    title_hint_block = (
        f"Preferred title hint (refine only if unclear): {title_hint.strip()}\n\n"
        if title_hint and title_hint.strip()
        else ""
    )
    prompt = _PROMPT_TEMPLATE.format(title_hint_block=title_hint_block, raw_text=cleaned_input)

    candidate_models = tuple(models) if models else FREE_SCRATCHPAD_MODELS
    errors: list[str] = []
    for model in candidate_models:
        try:
            title, content = _run_opencode_free_model(binary, model, prompt, timeout_secs)
            return ScratchpadSuggestion(title=title, content=content, model=model)
        except Exception as exc:
            errors.append(f"{model}: {exc}")

    raise RuntimeError("All free OpenCode models failed: " + " | ".join(errors))
