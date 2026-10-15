"""Issue and milestone operations, ticket content synthesis, and status mapping."""

import logging
import re
import sys
from typing import Any
import httpx

from factory.ui.github._client import DEFAULT_TEST_ORG, get_test_org_token, strip_repo_owner
from factory.ui.github._models import FACTORY_LABELS

logger = logging.getLogger(__name__)


def _get_pkg():
    return sys.modules.get("factory.ui.github")


def _headers(token: str, agent: str = "SoftwareFactory-TestingConsole/1.0") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": agent,
    }


def parse_github_blocked_by(body: str | None) -> list[str]:
    """Parses blocker issue identifiers from issue markdown body ('Blocked by: #<id>' or 'Blocked by: None')."""
    if not body:
        return []
    match = re.search(r"(?:^|\n|[\.\;]\s*)\s*\*{0,2}Blocked\s+by\*{0,2}\s*:\s*\*{0,2}([^\n\r]+)", body, re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1).strip().strip("`*_").rstrip(".;").strip()
    if not raw or re.match(r"^none(?:\s*\(.*?\))?[\.\s]*$", raw, re.IGNORECASE):
        return []

    blocker_ids: list[str] = []
    for token in [t.strip().strip("`*_").rstrip(".;").strip() for t in raw.split(",")]:
        if re.match(r"^none(?:\s*\(.*?\))?[\.\s]*$", token, re.IGNORECASE):
            continue
        num_match = re.search(r"#?(\d+)", token)
        blocker_ids.append(num_match.group(1) if num_match else token)
    return [b for b in blocker_ids if b]


def map_github_issue_status(issue: dict[str, Any]) -> str:
    """Maps GitHub issue state and labels to assembly line TicketStatus."""
    if issue.get("state") == "closed":
        return "resolved"
    raw_labels = issue.get("labels") or []
    label_names = [l["name"].lower() if isinstance(l, dict) and "name" in l else str(l).lower() for l in raw_labels]
    if FACTORY_LABELS["RESOLVED"] in label_names:
        return "resolved"
    if FACTORY_LABELS["READY_FOR_HUMAN"] in label_names:
        return "ready-for-human"
    if FACTORY_LABELS["CLAIMED"] in label_names:
        return "claimed"
    return "ready-for-agent"


def normalize_milestone_slug(title: str) -> str:
    """Normalizes milestone title to canonical slug (e.g. 'v1: Initial App' -> 'v1-initial-app')."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")


def fetch_repo_milestones(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    state: str = "open",
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches repository milestones from GitHub API."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    if not auth_token:
        return []

    url = f"https://api.github.com/repos/{org}/{clean_repo}/milestones?state={state}&per_page=100"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=_headers(auth_token))
            if resp.status_code == 200:
                results = []
                for m in resp.json():
                    title = m.get("title", "")
                    results.append({
                        "id": m.get("id"),
                        "number": m.get("number"),
                        "title": title,
                        "slug": normalize_milestone_slug(title),
                        "description": m.get("description"),
                        "state": m.get("state", "open"),
                        "open_issues": m.get("open_issues", 0),
                        "closed_issues": m.get("closed_issues", 0),
                        "html_url": m.get("html_url"),
                    })
                return results
    except Exception:
        pass
    return []


def _normalize_github_issue(item: dict[str, Any]) -> dict[str, Any]:
    """Extracts normalized issue fields from a raw GitHub issue payload."""
    raw_labels = item.get("labels") or []
    labels = [label["name"] if isinstance(label, dict) and "name" in label else str(label) for label in raw_labels]
    body = item.get("body")
    milestone_obj = None
    raw_milestone = item.get("milestone")
    if isinstance(raw_milestone, dict):
        m_title = raw_milestone.get("title") or ""
        milestone_obj = {
            "number": raw_milestone.get("number"),
            "title": m_title,
            "slug": raw_milestone.get("slug") or normalize_milestone_slug(m_title),
        }

    return {
        "id": item.get("id"),
        "number": item.get("number"),
        "title": item.get("title", ""),
        "body": body,
        "state": item.get("state", "open"),
        "labels": labels,
        "blocked_by": parse_github_blocked_by(body),
        "status": map_github_issue_status(item),
        "milestone": milestone_obj,
        "html_url": item.get("html_url"),
    }


def fetch_repo_issues(
    repo_name: str,
    milestone_number: int | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    state: str = "all",
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches candidate issues for a repository (optionally filtered by milestone number)."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    if not auth_token:
        return []

    url = (
        f"https://api.github.com/repos/{org}/{clean_repo}/issues?milestone={milestone_number}&state={state}&per_page=100"
        if milestone_number is not None
        else f"https://api.github.com/repos/{org}/{clean_repo}/issues?state={state}&per_page=100"
    )
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=_headers(auth_token))
            if resp.status_code == 200:
                return [_normalize_github_issue(i) for i in resp.json() if "pull_request" not in i]
    except Exception:
        pass
    return []


def fetch_repo_issue(
    repo_name: str,
    issue_number: int,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any] | None:
    """Fetches single issue details by issue number."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    if not auth_token:
        return None

    url = f"https://api.github.com/repos/{org}/{clean_repo}/issues/{issue_number}"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=_headers(auth_token))
            if resp.status_code == 200:
                item = resp.json()
                return None if "pull_request" in item else _normalize_github_issue(item)
    except Exception:
        pass
    return None


def fetch_repo_milestones_and_issues(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Queries GitHub REST endpoints for repository milestones and their candidate issues."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    milestones_fn = getattr(pkg, "fetch_repo_milestones", fetch_repo_milestones) if pkg else fetch_repo_milestones
    issues_fn = getattr(pkg, "fetch_repo_issues", fetch_repo_issues) if pkg else fetch_repo_issues

    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    if not auth_token:
        return {"repo": clean_repo, "org": org, "milestones": []}

    milestones = milestones_fn(clean_repo, auth_token, org, "open", timeout_secs)
    for ms in milestones:
        num = ms.get("number")
        ms["issues"] = issues_fn(clean_repo, num, auth_token, org, "all", timeout_secs) if num else []
    return {"repo": clean_repo, "org": org, "milestones": milestones}


def create_repo_milestone(
    repo_name: str,
    title: str = "v1: Initial App",
    description: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Creates a milestone in the target repository via GitHub API."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    slug = normalize_milestone_slug(title)

    fallback = {
        "id": 1,
        "number": 1,
        "title": title,
        "slug": slug,
        "description": description or "",
        "state": "open",
        "html_url": f"https://github.com/{org}/{clean_repo}/milestone/1",
    }
    if not auth_token:
        return fallback

    url = f"https://api.github.com/repos/{org}/{clean_repo}/milestones"
    payload = {"title": title, "state": "open", "description": description or "Initial frontend application"}
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.post(url, headers=_headers(auth_token, "SoftwareFactory-Studio/1.0"), json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                t = data.get("title", title)
                return {
                    "id": data.get("id"),
                    "number": data.get("number"),
                    "title": t,
                    "slug": normalize_milestone_slug(t),
                    "description": data.get("description"),
                    "state": data.get("state", "open"),
                    "html_url": data.get("html_url"),
                }
    except Exception:
        pass
    return fallback


def resolve_or_create_milestone(
    repo_name: str,
    title: str | None = None,
    description: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Finds an existing open milestone matching title/slug, or active milestone, or creates a new milestone."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    fetch_fn = getattr(pkg, "fetch_repo_milestones", fetch_repo_milestones) if pkg else fetch_repo_milestones
    create_fn = getattr(pkg, "create_repo_milestone", create_repo_milestone) if pkg else create_repo_milestone

    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    existing_milestones = fetch_fn(clean_repo, auth_token, org, "open", timeout_secs)

    if title:
        target_title = title.strip()
        target_slug = normalize_milestone_slug(target_title)
        for ms in existing_milestones:
            if ms.get("title", "").strip().lower() == target_title.lower() or ms.get("slug", "") == target_slug:
                return ms

    if not title and existing_milestones:
        return existing_milestones[0]

    return create_fn(clean_repo, title or "v1: Initial App", description, auth_token, org, timeout_secs)


def synthesize_ticket_content(
    prompt: str,
    seq_num: int = 1,
    previous_issue_number: int | None = None,
) -> tuple[str, str]:
    """Derives a formatted ticket title and markdown specification from user prompt."""
    clean = prompt.strip()
    lead_pattern = re.compile(
        r"^(?:build\s+(?:a|an)?|create\s+(?:a|an)?|implement\s+(?:a|an)?|add\s+(?:a|an)?)\s+",
        re.IGNORECASE,
    )
    base_text = lead_pattern.sub("", clean).strip()
    first_sentence = re.split(r"[.\n]", base_text)[0].strip()
    if len(first_sentence) > 60:
        first_sentence = first_sentence[:57] + "..."
    if not first_sentence:
        first_sentence = f"Feature Request {seq_num}"

    title_words = [w.capitalize() if not (w.isupper() or any(c.isdigit() for c in w)) else w for w in first_sentence.split()]
    formatted_subject = " ".join(title_words)
    title = f"{seq_num:02d}: {formatted_subject}"
    blocked_by = f"#{previous_issue_number}" if (previous_issue_number and previous_issue_number > 0) else "None"

    criteria = [
        f"Implement core UI layout and component hierarchy for {first_sentence.lower()} using TanStack Start and Tailwind CSS.",
        "Implement interactive client-side state management, user actions, and error handling.",
    ]
    p_lower = clean.lower()
    for keywords, text in [
        (("dark", "theme"), "Add dark mode / light mode theme toggle with persistent preference."),
        (("csv", "export", "download"), "Implement data export functionality with formatted file download."),
        (("history", "log", "saved"), "Implement stateful activity history with clear/delete controls."),
        (("keyboard", "shortcut"), "Support keyboard shortcuts and accessible navigation."),
        (("chart", "metric", "graph"), "Render interactive data visualizations and metric summaries."),
        (("filter", "search"), "Provide real-time query search and facet filtering."),
    ]:
        if any(k in p_lower for k in keywords):
            criteria.append(text)

    criteria.extend([
        "Ensure responsive design adapts seamlessly across Desktop, Tablet, and Mobile viewports.",
        "Add unit and component verification tests ensuring deterministic test passes.",
    ])

    body_lines = [
        f"# {seq_num:02d}: {formatted_subject}", "",
        f"**What to build:** {clean}", "",
        f"**Blocked by:** {blocked_by}", "",
        "**Status:** ready-for-agent", "",
    ]
    body_lines.extend(f"- [ ] {crit}" for crit in criteria)
    return title, "\n".join(body_lines) + "\n"


def create_repo_issue(
    repo_name: str,
    title: str,
    body: str,
    milestone_number: int | None = None,
    labels: list[str] | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Creates a GitHub issue under the target repository via GitHub API."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    issue_labels = labels or [FACTORY_LABELS["READY"]]

    fallback = {
        "id": 100,
        "number": 1,
        "title": title,
        "body": body,
        "state": "open",
        "labels": issue_labels,
        "milestone": milestone_number,
        "html_url": f"https://github.com/{org}/{clean_repo}/issues/1",
    }
    if not auth_token:
        return fallback

    url = f"https://api.github.com/repos/{org}/{clean_repo}/issues"
    payload: dict[str, Any] = {"title": title, "body": body, "labels": issue_labels}
    if milestone_number is not None:
        payload["milestone"] = milestone_number

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.post(url, headers=_headers(auth_token, "SoftwareFactory-Studio/1.0"), json=payload)
            if resp.status_code in (200, 201):
                return _normalize_github_issue(resp.json())
    except Exception:
        pass
    return fallback


def synthesize_and_create_issue(
    repo_name: str,
    prompt: str,
    milestone_number: int,
    milestone_slug: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Synthesizes ticket title/body from user prompt and creates sequential issue in milestone."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    fetch_fn = getattr(pkg, "fetch_repo_issues", fetch_repo_issues) if pkg else fetch_repo_issues
    create_fn = getattr(pkg, "create_repo_issue", create_repo_issue) if pkg else create_repo_issue

    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    existing_issues = fetch_fn(clean_repo, milestone_number, auth_token, org, "all", timeout_secs)
    sorted_issues = sorted(existing_issues, key=lambda x: x.get("number") or 0)
    seq_num = len(sorted_issues) + 1
    prev_num = sorted_issues[-1]["number"] if sorted_issues and "number" in sorted_issues[-1] else None

    title, body = synthesize_ticket_content(prompt, seq_num, prev_num)
    return create_fn(
        repo_name=clean_repo,
        title=title,
        body=body,
        milestone_number=milestone_number,
        labels=[FACTORY_LABELS["READY"]],
        token=auth_token,
        org=org,
        timeout_secs=timeout_secs,
    )
