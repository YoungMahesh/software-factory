"""Prompt template loader and double-curly brace substitution engine."""

from pathlib import Path
import re
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def load_prompt_template(name: str, reload: bool = False) -> str:
    """Loads a markdown prompt template by name, caching it in memory.

    Args:
        name: The base name or file name of the prompt template (e.g. "grilling_assistant").
        reload: If True, bypasses and refreshes the in-memory cache from disk.

    Returns:
        The raw markdown template string.

    Raises:
        FileNotFoundError: If the specified prompt template does not exist on disk.
    """
    clean_name = name.removesuffix(".md")
    if not reload and clean_name in _PROMPT_CACHE:
        return _PROMPT_CACHE[clean_name]

    template_path = PROMPTS_DIR / f"{clean_name}.md"
    if not template_path.is_file():
        raise FileNotFoundError(
            f"Prompt template '{clean_name}' not found at {template_path}"
        )

    content = template_path.read_text(encoding="utf-8")
    _PROMPT_CACHE[clean_name] = content
    return content


def render_prompt_template(
    name: str,
    variables: dict[str, Any] | None = None,
    reload: bool = False,
) -> str:
    """Loads and renders a prompt template with {{variable}} substitution.

    Args:
        name: The prompt template name.
        variables: Key-value mapping of replacement variables. Single braces
            in the template (e.g. JSON schemas) remain untouched.
        reload: If True, reloads the template from disk before rendering.

    Returns:
        The rendered prompt string with all variables substituted.
    """
    template = load_prompt_template(name, reload=reload)
    if not variables:
        return template

    def _replace_token(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in variables:
            val = variables[var_name]
            return "" if val is None else str(val)
        return match.group(0)

    return re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", _replace_token, template)
