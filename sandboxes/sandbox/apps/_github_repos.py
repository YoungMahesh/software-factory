"""GitHub repository catalog normalization, REST fetching, and cache schema."""

from __future__ import annotations

import json
import re
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, Field

EXCLUDED_INFRA_REPOS: frozenset[str] = frozenset({"env-store", "caddy-store"})
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/?#\s]+)/([^/?#\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


class CachedGitHubRepo(BaseModel):
    """Cached metadata for a GitHub repository selectable in the Builder."""

    full_name: str
    name: str
    owner: str
    private: bool = False
    default_branch: str = "main"
    description: str | None = None
    updated_at: str | None = None
    html_url: str | None = None


class RepositoryCatalogCache(BaseModel):
    """Persisted Repository Catalog Cache stored in factory-state-v1."""

    org: str | None = None
    refreshed_at: str | None = None
    repos: list[CachedGitHubRepo] = Field(default_factory=list)


def normalize_repo_spec(raw_repo: str, default_org: str | None = None) -> tuple[str, str, str]:
    """Normalizes a repo name, owner/repo slug, or GitHub URL to (full_name, owner, name)."""
    cleaned = raw_repo.strip().rstrip("/")
    if not cleaned:
        raise ValueError("Repository specifier must not be empty.")

    url_match = _GITHUB_URL_RE.match(cleaned)
    if url_match:
        owner, name = url_match.group(1), url_match.group(2)
    elif "/" in cleaned:
        parts = cleaned.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repository specifier '{raw_repo}'; expected 'owner/repo'.")
        owner, name = parts[0].strip(), parts[1].strip()
    else:
        org = (default_org or "").strip()
        if not org:
            raise ValueError(
                f"Repository '{raw_repo}' has no owner prefix and GH_ORG_NAME is not configured."
            )
        owner, name = org, cleaned

    if name.lower().endswith(".git"):
        name = name[:-4]
    if not _OWNER_RE.match(owner) or not _REPO_RE.match(name) or set(name) <= {"."}:
        raise ValueError(f"Invalid GitHub repository '{raw_repo}'.")
    return f"{owner}/{name}", owner, name


def _github_get_json(url: str, token: str, *, timeout: float = 20.0) -> tuple[int, Any, dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "software-factory-control-plane",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, (json.loads(raw) if raw else None), headers
    except urllib.error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(err_raw) if err_raw else {}
        except Exception:
            body = {"message": err_raw}
        return exc.code, body, {}


def _extract_next_link(headers: dict[str, str]) -> str | None:
    link = headers.get("link", "")
    if not link:
        return None
    for part in link.split(","):
        segs = [s.strip() for s in part.split(";")]
        if len(segs) >= 2 and any(s == 'rel="next"' for s in segs[1:]):
            if segs[0].startswith("<") and segs[0].endswith(">"):
                return segs[0][1:-1]
    return None


def _resolve_repo_list_endpoint(org: str, token: str, *, timeout: float) -> tuple[str, bool]:
    """Resolves the paginated GitHub API URL for org or user repositories."""
    encoded_org = urllib.parse.quote(org, safe="")
    u_status, u_body, _ = _github_get_json(
        f"https://api.github.com/users/{encoded_org}", token, timeout=timeout
    )
    if u_status == 200 and isinstance(u_body, dict) and u_body.get("type") == "Organization":
        return f"https://api.github.com/orgs/{encoded_org}/repos?per_page=100&sort=updated&type=all", False
    if u_status not in (200, 404):
        msg = u_body.get("message", f"HTTP {u_status}") if isinstance(u_body, dict) else str(u_body)
        raise RuntimeError(f"Failed inspecting GitHub owner '{org}': {msg}")

    me_status, me_body, _ = _github_get_json("https://api.github.com/user", token, timeout=timeout)
    if (
        me_status == 200
        and isinstance(me_body, dict)
        and str(me_body.get("login", "")).casefold() == org.casefold()
    ):
        return "https://api.github.com/user/repos?affiliation=owner&per_page=100&sort=updated", False
    if u_status == 404:
        raise RuntimeError(f"GitHub organization or user '{org}' was not found.")
    return f"https://api.github.com/users/{encoded_org}/repos?per_page=100&sort=updated&type=owner", True


def fetch_github_org_repos(
    org: str,
    token: str,
    *,
    timeout: float = 20.0,
    max_pages: int = 10,
) -> list[CachedGitHubRepo]:
    """Fetches non-archived repositories for org (excluding infra vault repos)."""
    clean_org = org.strip()
    clean_token = token.strip()
    if not clean_org:
        raise ValueError("GH_ORG_NAME is not configured.")
    if not clean_token:
        raise ValueError("GH_TOKEN is not configured.")

    next_url, filter_owner = _resolve_repo_list_endpoint(clean_org, clean_token, timeout=timeout)
    repos: list[CachedGitHubRepo] = []
    seen: set[str] = set()
    pages = 0

    while next_url and pages < max_pages:
        pages += 1
        status, body, headers = _github_get_json(next_url, clean_token, timeout=timeout)
        if status != 200 or not isinstance(body, list):
            msg = body.get("message", f"HTTP {status}") if isinstance(body, dict) else str(body)
            raise RuntimeError(f"Failed listing GitHub repositories for '{clean_org}': {msg}")

        for item in body:
            if not isinstance(item, dict) or item.get("archived"):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name.lower() in EXCLUDED_INFRA_REPOS:
                continue
            owner_obj = item.get("owner") or {}
            owner_login = str(owner_obj.get("login") or clean_org).strip()
            if filter_owner and owner_login.casefold() != clean_org.casefold():
                continue
            full_name = str(item.get("full_name") or f"{owner_login}/{name}").strip()
            if full_name.lower() in seen:
                continue
            seen.add(full_name.lower())
            repos.append(
                CachedGitHubRepo(
                    full_name=full_name,
                    name=name,
                    owner=owner_login,
                    private=bool(item.get("private", False)),
                    default_branch=str(item.get("default_branch") or "main"),
                    description=(str(item["description"]).strip() if item.get("description") else None),
                    updated_at=(str(item["updated_at"]) if item.get("updated_at") else None),
                    html_url=(str(item["html_url"]) if item.get("html_url") else None),
                )
            )
        next_url = _extract_next_link(headers)

    repos.sort(key=lambda r: r.updated_at or "", reverse=True)
    return repos
