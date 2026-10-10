"""GitHub Discovery Client for Canonical Test Organization.

Decrypts secrets_org/software-factory-09-test/token ephemerally into memory
and inspects organization repositories and .scratch/ issue tracking trees.
"""

from collections import defaultdict
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import httpx

DEFAULT_TEST_ORG = "software-factory-09-test"
FALLBACK_REPOS = ["test1", "test2", "test3"]

FACTORY_LABELS = {
    "READY": "factory:ready",
    "CLAIMED": "factory:claimed",
    "RESOLVED": "factory:resolved",
    "READY_FOR_HUMAN": "factory:ready-for-human",
}

CANONICAL_TEMPLATE_ORG = "software-factory-09-test"
CANONICAL_TEMPLATE_REPO = "tanstack-start-template"

REPO_NAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def validate_github_repo_name(name: str) -> tuple[bool, str | None]:
    """Validates that a repository name complies with GitHub repository slug requirements."""
    if not isinstance(name, str) or not name.strip():
        return False, "Repository name cannot be empty."

    trimmed = name.strip()
    if len(trimmed) > 100:
        return False, "Repository name cannot exceed 100 characters."

    if trimmed in (".", "..") or trimmed.lower() == ".git" or trimmed.lower().endswith(".git"):
        return False, "Repository name cannot be '.', '..', or end with '.git'."

    if not REPO_NAME_REGEX.match(trimmed):
        return False, (
            "Repository name must start with an alphanumeric character and contain "
            "only alphanumeric characters, hyphens, underscores, or periods."
        )

    return True, None


_cached_token: str | None = None


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    """Resolves software-factory root directory."""
    if repo_root is not None:
        return repo_root.resolve()
    return Path(__file__).resolve().parent.parent.parent


def get_test_org_token(repo_root: Path | None = None, force_refresh: bool = False) -> str | None:
    """Ephemerally decrypts the Test Organization token into memory via host SOPS.

    Credentials are never written to disk or exposed in logs.
    """
    global _cached_token
    if _cached_token and not force_refresh:
        return _cached_token

    root = resolve_repo_root(repo_root)
    token_file = root / "secrets_org" / DEFAULT_TEST_ORG / "token"
    if not token_file.is_file():
        return None

    # Check for age key file
    age_key_path = Path.home() / ".config" / "sops" / "age" / "keys.txt"
    env = os.environ.copy()
    if age_key_path.is_file() and "SOPS_AGE_KEY_FILE" not in env:
        env["SOPS_AGE_KEY_FILE"] = str(age_key_path)

    try:
        res = subprocess.run(
            ["sops", "-d", str(token_file)],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        token = res.stdout.strip()
        if token:
            _cached_token = token
            return token
    except Exception:
        pass
    return None


def check_tanstack_start_compatibility(repo_item: dict[str, Any]) -> bool:
    """Checks if a repository is compatible with TanStack Start template scaffolding."""
    if not repo_item or not isinstance(repo_item, dict):
        return False

    name = repo_item.get("name") or ""
    if name == CANONICAL_TEMPLATE_REPO:
        return True

    template_repo = repo_item.get("template_repository")
    if isinstance(template_repo, dict):
        tpl_name = template_repo.get("name") or ""
        if tpl_name == CANONICAL_TEMPLATE_REPO:
            return True

    topics = [str(t).lower() for t in repo_item.get("topics") or []]
    if "tanstack-start" in topics:
        return True

    description = (repo_item.get("description") or "").lower()
    if "tanstack start" in description or "@tanstack/start" in description:
        return True

    return False


def _fallback_repo_items(org: str = DEFAULT_TEST_ORG) -> list[dict[str, Any]]:
    """Generates default fallback repository items when organization credentials or API calls are unavailable."""
    return [
        {
            "name": r,
            "is_tanstack_compatible": False,
            "description": None,
            "html_url": f"https://github.com/{org}/{r}",
            "topics": [],
            "default_branch": "main",
        }
        for r in sorted(FALLBACK_REPOS)
    ]


def fetch_test_org_repos_detailed(
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches list of member repositories with TanStack Start compatibility indicator."""
    auth_token = token or get_test_org_token()
    if not auth_token:
        return _fallback_repo_items(org)

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }

    try:
        results: list[dict[str, Any]] = []
        page = 1
        with httpx.Client(timeout=timeout_secs) as client:
            while True:
                url = f"https://api.github.com/orgs/{org}/repos?per_page=100&page={page}&type=all"
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    break
                raw_repos = resp.json()
                if not isinstance(raw_repos, list) or not raw_repos:
                    break
                for r in raw_repos:
                    if not isinstance(r, dict) or "name" not in r:
                        continue
                    results.append({
                        "name": r["name"],
                        "is_tanstack_compatible": check_tanstack_start_compatibility(r),
                        "description": r.get("description"),
                        "html_url": r.get("html_url") or f"https://github.com/{org}/{r['name']}",
                        "topics": r.get("topics") or [],
                        "default_branch": r.get("default_branch", "main"),
                    })
                if len(raw_repos) < 100:
                    break
                page += 1

            if results:
                return sorted(results, key=lambda x: str(x["name"]))
    except Exception:
        pass

    return _fallback_repo_items(org)


def fetch_test_org_repos(
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> list[str]:
    """Fetches list of member repositories from GitHub API, falling back to known fixtures on error."""
    detailed = fetch_test_org_repos_detailed(token=token, org=org, timeout_secs=timeout_secs)
    return [d["name"] for d in detailed]


class RepoCreationError(Exception):
    """Raised when repository instantiation fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def instantiate_repo_from_template(
    repo_name: str,
    description: str | None = None,
    private: bool = False,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    template_org: str = CANONICAL_TEMPLATE_ORG,
    template_repo: str = CANONICAL_TEMPLATE_REPO,
    timeout_secs: float = 15.0,
) -> dict[str, Any]:
    """Creates a new repository in the test organization instantiated from the canonical TanStack Start template."""
    # 1. Slug validation
    valid, err_msg = validate_github_repo_name(repo_name)
    if not valid:
        raise RepoCreationError(err_msg or "Invalid repository name.", status_code=400)

    clean_name = repo_name.strip()

    # 2. Check for duplicate repo name in organization
    existing_repos = fetch_test_org_repos(token=token, org=org, timeout_secs=timeout_secs)
    if clean_name in existing_repos:
        raise RepoCreationError(f"Repository '{clean_name}' already exists in {org}.", status_code=409)

    # 3. Ephemerally decrypt Organization Credentials in memory
    auth_token = token or get_test_org_token()
    if not auth_token:
        raise RepoCreationError("Organization credentials not found or failed to decrypt.", status_code=500)

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }

    url = f"https://api.github.com/repos/{template_org}/{template_repo}/generate"
    payload = {
        "owner": org,
        "name": clean_name,
        "description": description or f"TanStack Start application generated by Factory Studio",
        "include_all_branches": False,
        "private": private,
    }

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.post(url, headers=headers, json=payload)
    except Exception as e:
        raise RepoCreationError(f"Network error communicating with GitHub API: {e}", status_code=502)

    if resp.status_code == 201:
        data = resp.json()
        return {
            "name": data.get("name", clean_name),
            "full_name": data.get("full_name", f"{org}/{clean_name}"),
            "html_url": data.get("html_url", f"https://github.com/{org}/{clean_name}"),
            "description": data.get("description", payload["description"]),
            "private": data.get("private", private),
            "is_tanstack_compatible": True,
            "template_repository": f"{template_org}/{template_repo}",
        }

    # Error handling
    try:
        error_json = resp.json()
        error_message = error_json.get("message", "GitHub API error")
        errors = error_json.get("errors", [])
        if errors and isinstance(errors, list):
            error_message += f": {', '.join(str(e) for e in errors)}"
    except Exception:
        error_message = resp.text or f"HTTP {resp.status_code}"

    if resp.status_code == 422:
        if "already exists" in error_message.lower():
            raise RepoCreationError(f"Repository '{clean_name}' already exists in {org}.", status_code=409)
        raise RepoCreationError(f"GitHub rejected repository creation: {error_message}", status_code=422)

    if resp.status_code == 404:
        raise RepoCreationError(f"Template repository '{template_org}/{template_repo}' not found.", status_code=502)

    raise RepoCreationError(f"GitHub API error ({resp.status_code}): {error_message}", status_code=502)




def fetch_repo_scratch_metadata(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Inspects the repository's Git Tree for .scratch/ feature folders and issue tickets."""
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    features_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    has_scratch = False

    if auth_token:
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SoftwareFactory-TestingConsole/1.0",
        }

        # Try main branch first, then master
        for branch in ("main", "master"):
            url = f"https://api.github.com/repos/{org}/{clean_repo}/git/trees/{branch}?recursive=1"
            try:
                with httpx.Client(timeout=timeout_secs) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        tree = resp.json().get("tree", [])
                        for item in tree:
                            path_str = item.get("path", "")
                            if not path_str.startswith(".scratch/"):
                                continue
                            has_scratch = True
                            parts = path_str.split("/")
                            if len(parts) >= 2:
                                feature_slug = parts[1]
                                if len(parts) >= 4 and parts[2] == "issues" and parts[3].endswith(".md"):
                                    issue_file = parts[3]
                                    # Extract issue number or prefix e.g. "01" from "01-name.md"
                                    issue_id = issue_file.split("-")[0]
                                    issue_slug = issue_file[:-3]  # remove .md
                                    features_map[feature_slug].append({
                                        "id": issue_id,
                                        "slug": issue_slug,
                                        "filename": issue_file,
                                    })
                        break
            except Exception:
                pass

    feature_list = []
    for slug, issues in sorted(features_map.items()):
        # Sort issues by ID
        sorted_issues = sorted(issues, key=lambda x: x["id"])
        feature_list.append({
            "slug": slug,
            "issues": sorted_issues,
        })

    return {
        "repo": clean_repo,
        "org": org,
        "has_scratch": has_scratch or bool(feature_list),
        "features": feature_list,
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

    tokens = [t.strip().strip("`*_").rstrip(".;").strip() for t in raw.split(",")]
    blocker_ids: list[str] = []
    for token in tokens:
        if re.match(r"^none(?:\s*\(.*?\))?[\.\s]*$", token, re.IGNORECASE):
            continue
        num_match = re.search(r"#?(\d+)", token)
        if num_match:
            blocker_ids.append(num_match.group(1))
        elif token:
            blocker_ids.append(token)
    return blocker_ids


def map_github_issue_status(issue: dict[str, Any]) -> str:
    """Maps GitHub issue state and labels to assembly line TicketStatus."""
    if issue.get("state") == "closed":
        return "resolved"

    raw_labels = issue.get("labels") or []
    label_names = [
        l["name"].lower() if isinstance(l, dict) and "name" in l else str(l).lower()
        for l in raw_labels
    ]

    if FACTORY_LABELS["RESOLVED"] in label_names:
        return "resolved"
    if FACTORY_LABELS["READY_FOR_HUMAN"] in label_names:
        return "ready-for-human"
    if FACTORY_LABELS["CLAIMED"] in label_names:
        return "claimed"
    if FACTORY_LABELS["READY"] in label_names:
        return "ready-for-agent"

    return "ready-for-agent"


def fetch_repo_milestones(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    state: str = "open",
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches repository milestones from GitHub API."""
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    if not auth_token:
        return []

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }

    url = f"https://api.github.com/repos/{org}/{clean_repo}/milestones?state={state}&per_page=100"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                milestones_data = resp.json()
                results = []
                for m in milestones_data:
                    title = m.get("title", "")
                    slug = title.strip().lower().replace(" ", "-")
                    results.append({
                        "id": m.get("id"),
                        "number": m.get("number"),
                        "title": title,
                        "slug": slug,
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
    labels = [
        label["name"] if isinstance(label, dict) and "name" in label else str(label)
        for label in raw_labels
    ]
    body = item.get("body")
    blocked_by = parse_github_blocked_by(body)
    status = map_github_issue_status(item)
    return {
        "id": item.get("id"),
        "number": item.get("number"),
        "title": item.get("title", ""),
        "body": body,
        "state": item.get("state", "open"),
        "labels": labels,
        "blocked_by": blocked_by,
        "status": status,
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
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    if not auth_token:
        return []

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }

    if milestone_number is not None:
        url = f"https://api.github.com/repos/{org}/{clean_repo}/issues?milestone={milestone_number}&state={state}&per_page=100"
    else:
        url = f"https://api.github.com/repos/{org}/{clean_repo}/issues?state={state}&per_page=100"

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                items = resp.json()
                results = []
                for item in items:
                    # Filter out PRs
                    if "pull_request" in item:
                        continue
                    results.append(_normalize_github_issue(item))
                return results
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
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    if not auth_token:
        return None

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }

    url = f"https://api.github.com/repos/{org}/{clean_repo}/issues/{issue_number}"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                item = resp.json()
                if "pull_request" in item:
                    return None
                return _normalize_github_issue(item)
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
    auth_token = token or get_test_org_token()
    clean_repo = repo_name.strip()
    if clean_repo.startswith(f"{org}/"):
        clean_repo = clean_repo[len(f"{org}/"):]

    if not auth_token:
        return {
            "repo": clean_repo,
            "org": org,
            "milestones": [],
        }

    milestones = fetch_repo_milestones(
        repo_name=clean_repo,
        token=auth_token,
        org=org,
        state="open",
        timeout_secs=timeout_secs,
    )

    for ms in milestones:
        ms_number = ms.get("number")
        if ms_number is not None:
            ms["issues"] = fetch_repo_issues(
                repo_name=clean_repo,
                milestone_number=ms_number,
                token=auth_token,
                org=org,
                state="all",
                timeout_secs=timeout_secs,
            )
        else:
            ms["issues"] = []

    return {
        "repo": clean_repo,
        "org": org,
        "milestones": milestones,
    }

