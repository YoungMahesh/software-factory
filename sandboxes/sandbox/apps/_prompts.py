"""Slug, title, URL, and prompt construction helpers for Factory Apps."""

from __future__ import annotations

import hashlib
import re
from typing import Literal
from urllib.parse import quote

from sandbox.config import DEFAULT_METRO_PORT, DEFAULT_T3_PORT, DEFAULT_XFCE_PORT
from shared.image import DEFAULT_T3_USAGE_VOLUME

AppTemplateKind = Literal["nextjs", "blank"]

MAX_SLUG_LENGTH = 42
MAX_TITLE_LENGTH = 60
GENERIC_REPO_OPEN_PROMPT = "Repository workspace is ready. Inspect the project briefly and wait for my instructions."


def _sanitize_slug(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not cleaned:
        cleaned = "factory-app"
    if cleaned[0].isdigit():
        cleaned = f"app-{cleaned}"
    return cleaned[:MAX_SLUG_LENGTH].rstrip("-") or "factory-app"


def _bare_repo_name(repo: str | None) -> str:
    if not repo:
        return ""
    clean = repo.strip().rstrip("/")
    if "/" in clean:
        clean = clean.rsplit("/", 1)[-1]
    if clean.lower().endswith(".git"):
        clean = clean[:-4]
    return clean


def derive_app_slug(
    prompt: str,
    explicit_name: str | None = None,
    existing_slugs: set[str] | None = None,
    repo: str | None = None,
) -> str:
    """Derives a unique filesystem/sandbox-safe slug from explicit_name, repo, or prompt."""
    if explicit_name and explicit_name.strip():
        base = _sanitize_slug(explicit_name.strip())
    elif repo and _bare_repo_name(repo):
        base = _sanitize_slug(_bare_repo_name(repo))
    else:
        first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
        words = re.findall(r"[a-zA-Z0-9]+", first_line)[:5]
        base = _sanitize_slug("-".join(words)) if words else "factory-app"

    used = existing_slugs or set()
    if base not in used:
        return base

    suffix_num = 2
    while True:
        suffix = f"-{suffix_num}"
        candidate = f"{base[:MAX_SLUG_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in used:
            return candidate
        suffix_num += 1


def derive_app_title(
    prompt: str,
    explicit_name: str | None = None,
    repo: str | None = None,
) -> str:
    """Derives a concise single-line title from explicit_name, prompt, or repo."""
    raw = explicit_name.strip() if explicit_name and explicit_name.strip() else ""
    if not raw:
        raw = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
    if not raw and repo:
        raw = _bare_repo_name(repo) or repo.strip()
    if not raw:
        raw = "Untitled App"
    raw = re.sub(r"\s+", " ", raw)
    if len(raw) <= MAX_TITLE_LENGTH:
        return raw
    return raw[: MAX_TITLE_LENGTH - 3].rstrip() + "..."


def prime_compatibility_key(
    profile: str | None = None,
    vm: bool = False,
    mobile_app: bool = False,
    *,
    testing: bool = False,
    browser: bool = False,
    react_native: bool = False,
    no_cloudflare: bool = True,
    no_t3_persist: bool = False,
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME,
    t3_port: int = DEFAULT_T3_PORT,
    t3_ssh_host: str | None = None,
    metro_port: int = DEFAULT_METRO_PORT,
    modal: bool = True,
    sops: bool = True,
    memory: int | None = None,
    xfce: bool = False,
    xfce_port: int = DEFAULT_XFCE_PORT,
    xfce_password: str | None = None,
) -> str:
    """Returns a filesystem-safe identifier partitioning Prime Sandboxes by runtime capabilities."""
    clean_profile = (profile or "").strip()
    if not clean_profile:
        prof_part = "default"
    else:
        slug_part = _sanitize_slug(clean_profile)[:16]
        digest = hashlib.sha256(clean_profile.encode("utf-8")).hexdigest()[:8]
        prof_part = f"p-{slug_part}-{digest}"
    effective_vm = bool(vm or xfce)
    effective_mob = bool(mobile_app or react_native)
    base = f"{prof_part}__vm-{1 if effective_vm else 0}__mob-{1 if effective_mob else 0}"
    normalized_memory = (1 if memory is None else memory) if effective_vm else None
    default_tuple = (
        False,
        False,
        True,
        False,
        DEFAULT_T3_USAGE_VOLUME,
        DEFAULT_T3_PORT,
        "",
        DEFAULT_METRO_PORT,
        True,
        True,
        1 if effective_vm else None,
        False,
        DEFAULT_XFCE_PORT,
        "",
    )
    current_tuple = (
        bool(testing),
        bool(browser),
        bool(no_cloudflare),
        bool(no_t3_persist),
        t3_usage_volume or DEFAULT_T3_USAGE_VOLUME,
        int(t3_port),
        (t3_ssh_host or "").strip(),
        int(metro_port),
        bool(modal),
        bool(sops),
        normalized_memory,
        bool(xfce),
        int(xfce_port),
        (xfce_password or "").strip(),
    )
    if current_tuple == default_tuple:
        return base
    cfg_digest = hashlib.sha256(repr(current_tuple).encode("utf-8")).hexdigest()[:8]
    return f"{base}__cfg-{cfg_digest}"


def prime_compatibility_key_for_app(app: Any) -> str:
    """Computes the Prime Sandbox compatibility key from a CreateAppPayload or FactoryAppRecord."""
    return prime_compatibility_key(
        getattr(app, "profile", None),
        getattr(app, "vm", False),
        getattr(app, "mobile_app", False),
        testing=getattr(app, "testing", False),
        browser=getattr(app, "browser", False),
        react_native=getattr(app, "react_native", False),
        no_cloudflare=getattr(app, "no_cloudflare", True),
        no_t3_persist=getattr(app, "no_t3_persist", False),
        t3_usage_volume=getattr(app, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME),
        t3_port=getattr(app, "t3_port", DEFAULT_T3_PORT),
        t3_ssh_host=getattr(app, "t3_ssh_host", None),
        metro_port=getattr(app, "metro_port", DEFAULT_METRO_PORT),
        modal=getattr(app, "modal", True),
        sops=getattr(app, "sops", True),
        memory=getattr(app, "memory", None),
        xfce=getattr(app, "xfce", False),
        xfce_port=getattr(app, "xfce_port", DEFAULT_XFCE_PORT),
        xfce_password=getattr(app, "xfce_password", None),
    )


def prime_sandbox_app_name(*, vm: bool = False, mobile_app: bool = False) -> str:
    """Returns the Modal App name used for a Prime Sandbox variant."""
    parts = ["prime-sandbox"]
    if vm:
        parts.append("vm")
    if mobile_app:
        parts.append("mobile")
    return "-".join(parts)


def derive_worktree_branch(slug: str, app_id: str) -> str:
    """Builds a unique Git branch name for a Factory App worktree inside a shared repo clone."""
    suffix = re.sub(r"[^a-z0-9]+", "", app_id.lower())[-6:] or "wt"
    prefix = _sanitize_slug(slug)[:28].strip("-") or "app"
    return f"sf/{prefix}-{suffix}"


def build_initial_thread_prompt(
    raw_prompt: str,
    *,
    template: AppTemplateKind,
    app_dir: str,
    dev_port: int | None = None,
    web_app: bool = True,
    repo: str | None = None,
) -> str:
    """Builds the T3 starter prompt, appending run-app instructions only when web_app=True."""
    clean_prompt = raw_prompt.strip()
    if not web_app:
        return clean_prompt

    if repo:
        if dev_port is not None:
            instruction = (
                f"use the run-app workflow in {app_dir}: start the web app server "
                f"(using port {dev_port}, e.g. `PORT={dev_port}`) and open "
                f"http://localhost:{dev_port} in the T3 Code browser so the live preview is open."
            )
        else:
            instruction = (
                f"use the run-app workflow in {app_dir}: start the web app server "
                "and open its localhost URL in the T3 Code browser so the live preview is open."
            )
        if not clean_prompt:
            return f"In {app_dir}, {instruction}"
        return f"{clean_prompt}\n\nOnce done, {instruction}"

    if template == "nextjs":
        if dev_port is not None:
            suffix = (
                f"Once built and verified in {app_dir}, use the run-app workflow: "
                f"run `pnpm run dev` (already configured on port {dev_port}) and open "
                f"http://localhost:{dev_port} in the T3 Code browser so the live preview is open."
            )
        else:
            suffix = (
                f"Once built and verified in {app_dir}, use the run-app workflow: "
                "run `pnpm run dev` and open its localhost URL in the T3 Code browser so the live preview is open."
            )
    else:
        if dev_port is not None:
            suffix = (
                f"Workspace is initialized at {app_dir}. Once built, start the local web server "
                f"on port {dev_port} (e.g. `PORT={dev_port}`) and open http://localhost:{dev_port} "
                "in the T3 Code browser so the live preview is open."
            )
        else:
            suffix = (
                f"Workspace is initialized at {app_dir}. Once built, start the local web server "
                "and open its localhost URL in the T3 Code browser so the live preview is open."
            )
    if not clean_prompt:
        return suffix
    return f"{clean_prompt}\n\n{suffix}"


def build_direct_chat_url(
    t3_url: str,
    environment_id: str,
    thread_id: str,
    token: str | None = None,
) -> str:
    """Builds the direct T3 Web chat route, optionally attaching a one-time pairing fragment."""
    base = (
        f"{t3_url.rstrip('/')}/"
        f"{quote(environment_id, safe='')}/"
        f"{quote(thread_id, safe='')}"
    )
    if token:
        return f"{base}#token={quote(token, safe='')}"
    return base
