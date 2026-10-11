"""GitHub Discovery Client for Canonical Test Organization.

Decrypts secrets_org/software-factory-09-test/token ephemerally into memory
and inspects organization repositories and .scratch/ issue tracking trees.
"""

from collections import defaultdict
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import httpx

logger = logging.getLogger(__name__)

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
_template_lineage_cache: dict[str, bool] = {}


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
                    repo_name_str = r["name"]
                    is_compatible = check_tanstack_start_compatibility(r)
                    if not is_compatible and repo_name_str not in FALLBACK_REPOS:
                        if repo_name_str in _template_lineage_cache:
                            is_compatible = _template_lineage_cache[repo_name_str]
                        else:
                            try:
                                single_resp = client.get(
                                    f"https://api.github.com/repos/{org}/{repo_name_str}",
                                    headers=headers,
                                )
                                if single_resp.status_code == 200:
                                    s_data = single_resp.json()
                                    is_compatible = check_tanstack_start_compatibility(s_data)
                                    _template_lineage_cache[repo_name_str] = is_compatible
                            except Exception:
                                pass

                    results.append({
                        "name": repo_name_str,
                        "is_tanstack_compatible": is_compatible,
                        "description": r.get("description"),
                        "html_url": r.get("html_url") or f"https://github.com/{org}/{repo_name_str}",
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
    default_desc = "TanStack Start application generated by Factory Studio"
    if description and description.strip():
        if "tanstack" in description.lower():
            final_desc = description.strip()
        else:
            final_desc = f"{description.strip()} (TanStack Start)"
    else:
        final_desc = default_desc

    payload = {
        "owner": org,
        "name": clean_name,
        "description": final_desc,
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
        _template_lineage_cache[clean_name] = True

        try:
            from factory.ui.scaffold import scaffold_target_repo
            scaffold_result = scaffold_target_repo(
                repo_name=clean_name,
                token=auth_token,
                org=org,
                timeout_secs=timeout_secs,
            )
        except Exception as e:
            logger.error("Failed to scaffold repository %s/%s: %s", org, clean_name, e)
            raise RepoCreationError(
                f"Repository '{clean_name}' was created from template but failed to scaffold skills and ADRs: {e}",
                status_code=500,
            ) from e

        return {
            "name": data.get("name", clean_name),
            "full_name": data.get("full_name", f"{org}/{clean_name}"),
            "html_url": data.get("html_url", f"https://github.com/{org}/{clean_name}"),
            "description": data.get("description", payload["description"]),
            "private": data.get("private", private),
            "is_tanstack_compatible": True,
            "template_repository": f"{template_org}/{template_repo}",
            "scaffolded": scaffold_result.get("status") == "scaffolded" if scaffold_result else False,
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
                    slug = normalize_milestone_slug(title)
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


def strip_repo_owner(repo_name: str, org: str = DEFAULT_TEST_ORG) -> str:
    """Strips org/ prefix from repository name if present."""
    clean = repo_name.strip()
    if clean.startswith(f"{org}/"):
        return clean[len(f"{org}/"):]
    return clean


def create_repo_milestone(
    repo_name: str,
    title: str = "v1: Initial App",
    description: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Creates a milestone in the target repository via GitHub API."""
    auth_token = token or get_test_org_token()
    clean_repo = strip_repo_owner(repo_name, org)

    slug = normalize_milestone_slug(title)

    if not auth_token:
        return {
            "id": 1,
            "number": 1,
            "title": title,
            "slug": slug,
            "description": description or "",
            "state": "open",
            "html_url": f"https://github.com/{org}/{clean_repo}/milestone/1",
        }

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }
    url = f"https://api.github.com/repos/{org}/{clean_repo}/milestones"
    payload = {
        "title": title,
        "state": "open",
        "description": description or "Initial frontend application generated by Factory Studio",
    }

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                milestone_title = data.get("title", title)
                return {
                    "id": data.get("id"),
                    "number": data.get("number"),
                    "title": milestone_title,
                    "slug": normalize_milestone_slug(milestone_title),
                    "description": data.get("description"),
                    "state": data.get("state", "open"),
                    "html_url": data.get("html_url"),
                }
    except Exception:
        pass

    return {
        "id": 1,
        "number": 1,
        "title": title,
        "slug": slug,
        "description": description or "",
        "state": "open",
        "html_url": f"https://github.com/{org}/{clean_repo}/milestone/1",
    }


def resolve_or_create_milestone(
    repo_name: str,
    title: str | None = None,
    description: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Finds an existing open milestone matching title/slug, or active milestone, or creates a new milestone."""
    auth_token = token or get_test_org_token()
    clean_repo = strip_repo_owner(repo_name, org)

    existing_milestones = fetch_repo_milestones(
        repo_name=clean_repo,
        token=auth_token,
        org=org,
        state="open",
        timeout_secs=timeout_secs,
    )

    if title:
        target_title = title.strip()
        normalized_target_slug = normalize_milestone_slug(target_title)
        for ms in existing_milestones:
            ms_title = ms.get("title", "")
            ms_slug = ms.get("slug", "")
            if (
                ms_title.strip().lower() == target_title.lower()
                or ms_slug == normalized_target_slug
            ):
                return ms

    # If title was not explicitly specified and there is an open milestone, reuse active open milestone
    if not title and existing_milestones:
        return existing_milestones[0]

    final_title = title or "v1: Initial App"
    return create_repo_milestone(
        repo_name=clean_repo,
        title=final_title,
        description=description,
        token=auth_token,
        org=org,
        timeout_secs=timeout_secs,
    )


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

    title_words = [
        w.capitalize() if not (w.isupper() or any(c.isdigit() for c in w)) else w
        for w in first_sentence.split()
    ]
    formatted_subject = " ".join(title_words)
    title = f"{seq_num:02d}: {formatted_subject}"

    if previous_issue_number and previous_issue_number > 0:
        blocked_by = f"#{previous_issue_number}"
    else:
        blocked_by = "None"

    # Derive tailored acceptance criteria based on prompt content
    criteria = [
        f"Implement core UI layout and component hierarchy for {first_sentence.lower()} using TanStack Start and Tailwind CSS.",
        "Implement interactive client-side state management, user actions, and error handling.",
    ]
    p_lower = clean.lower()
    if "dark" in p_lower or "theme" in p_lower:
        criteria.append("Add dark mode / light mode theme toggle with persistent preference.")
    if "csv" in p_lower or "export" in p_lower or "download" in p_lower:
        criteria.append("Implement data export functionality with formatted file download.")
    if "history" in p_lower or "log" in p_lower or "saved" in p_lower:
        criteria.append("Implement stateful activity history with clear/delete controls.")
    if "keyboard" in p_lower or "shortcut" in p_lower:
        criteria.append("Support keyboard shortcuts and accessible navigation.")
    if "chart" in p_lower or "metric" in p_lower or "graph" in p_lower:
        criteria.append("Render interactive data visualizations and metric summaries.")
    if "filter" in p_lower or "search" in p_lower:
        criteria.append("Provide real-time query search and facet filtering.")

    criteria.extend([
        "Ensure responsive design adapts seamlessly across Desktop, Tablet, and Mobile viewports.",
        "Add unit and component verification tests ensuring deterministic test passes.",
    ])

    body_lines = [
        f"# {seq_num:02d}: {formatted_subject}",
        "",
        f"**What to build:** {clean}",
        "",
        f"**Blocked by:** {blocked_by}",
        "",
        "**Status:** ready-for-agent",
        "",
    ]
    for crit in criteria:
        body_lines.append(f"- [ ] {crit}")

    body = "\n".join(body_lines) + "\n"
    return title, body


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
    auth_token = token or get_test_org_token()
    clean_repo = strip_repo_owner(repo_name, org)

    issue_labels = labels or [FACTORY_LABELS["READY"]]

    if not auth_token:
        return {
            "id": 100,
            "number": 1,
            "title": title,
            "body": body,
            "state": "open",
            "labels": issue_labels,
            "milestone": milestone_number,
            "html_url": f"https://github.com/{org}/{clean_repo}/issues/1",
        }

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }
    url = f"https://api.github.com/repos/{org}/{clean_repo}/issues"
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "labels": issue_labels,
    }
    if milestone_number is not None:
        payload["milestone"] = milestone_number

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                item = resp.json()
                return _normalize_github_issue(item)
    except Exception:
        pass

    return {
        "id": 100,
        "number": 1,
        "title": title,
        "body": body,
        "state": "open",
        "labels": issue_labels,
        "milestone": milestone_number,
        "html_url": f"https://github.com/{org}/{clean_repo}/issues/1",
    }


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
    auth_token = token or get_test_org_token()
    clean_repo = strip_repo_owner(repo_name, org)

    existing_issues = fetch_repo_issues(
        repo_name=clean_repo,
        milestone_number=milestone_number,
        token=auth_token,
        org=org,
        state="all",
        timeout_secs=timeout_secs,
    )

    # Sort ascending by issue number to guarantee the latest issue is last
    sorted_issues = sorted(existing_issues, key=lambda x: x.get("number") or 0)
    seq_num = len(sorted_issues) + 1
    previous_issue_number = (
        sorted_issues[-1]["number"] if sorted_issues and "number" in sorted_issues[-1] else None
    )

    title, body = synthesize_ticket_content(
        prompt=prompt,
        seq_num=seq_num,
        previous_issue_number=previous_issue_number,
    )

    issue = create_repo_issue(
        repo_name=clean_repo,
        title=title,
        body=body,
        milestone_number=milestone_number,
        labels=[FACTORY_LABELS["READY"]],
        token=auth_token,
        org=org,
        timeout_secs=timeout_secs,
    )
    return issue


def commit_approved_adr_to_branch(
    repo_name: str,
    branch: str,
    draft_adr: dict[str, Any] | None = None,
    context_update: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 20.0,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Commits approved draft ADR and updated CONTEXT.md directly to GitHub branch."""
    clean_repo = strip_repo_owner(repo_name, org)
    auth_token = token or get_test_org_token(repo_root=repo_root)

    files_to_commit: dict[str, str] = {}
    if draft_adr:
        filename = draft_adr.get("filename")
        if not filename:
            title_slug = normalize_milestone_slug(draft_adr.get("title") or "decision")
            filename = f"docs/adr/0002-{title_slug}.md"
        content = draft_adr.get("content") or ""
        files_to_commit[filename] = content

    if context_update and context_update.strip():
        files_to_commit["CONTEXT.md"] = context_update.strip()

    if not files_to_commit:
        return {
            "repo": clean_repo,
            "org": org,
            "branch": branch,
            "status": "skipped",
            "files": [],
        }

    if not auth_token:
        return {
            "repo": clean_repo,
            "org": org,
            "branch": branch,
            "status": "mocked",
            "files": list(files_to_commit.keys()),
            "commit_sha": "mock-commit-sha",
        }

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }

    base_url = f"https://api.github.com/repos/{org}/{clean_repo}"

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            commit_sha: str | None = None
            base_tree_sha: str | None = None

            # 1. Check if target branch exists
            ref_resp = client.get(f"{base_url}/git/ref/heads/{branch}", headers=headers)
            if ref_resp.status_code != 200:
                ref_resp = client.get(f"{base_url}/git/refs/heads/{branch}", headers=headers)

            branch_exists = ref_resp.status_code == 200
            if branch_exists:
                commit_sha = ref_resp.json().get("object", {}).get("sha")
            else:
                # Fall back to main branch ref to branch off main
                main_ref_resp = client.get(f"{base_url}/git/ref/heads/main", headers=headers)
                if main_ref_resp.status_code != 200:
                    main_ref_resp = client.get(f"{base_url}/git/refs/heads/main", headers=headers)
                if main_ref_resp.status_code == 200:
                    commit_sha = main_ref_resp.json().get("object", {}).get("sha")

            if commit_sha:
                commit_resp = client.get(f"{base_url}/git/commits/{commit_sha}", headers=headers)
                if commit_resp.status_code == 200:
                    base_tree_sha = commit_resp.json().get("tree", {}).get("sha")

            # 2. Create new tree
            tree_items = [
                {
                    "path": path_str,
                    "mode": "100644",
                    "type": "blob",
                    "content": content_str,
                }
                for path_str, content_str in files_to_commit.items()
            ]
            tree_payload: dict[str, Any] = {"tree": tree_items}
            if base_tree_sha:
                tree_payload["base_tree"] = base_tree_sha

            tree_resp = client.post(f"{base_url}/git/trees", headers=headers, json=tree_payload)
            if tree_resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create Git tree ({tree_resp.status_code}): {tree_resp.text}")
            new_tree_sha = tree_resp.json()["sha"]

            # 3. Create commit
            commit_payload: dict[str, Any] = {
                "message": f"docs(adr): record architectural decision for {branch}",
                "tree": new_tree_sha,
                "parents": [commit_sha] if commit_sha else [],
            }
            new_commit_resp = client.post(f"{base_url}/git/commits", headers=headers, json=commit_payload)
            if new_commit_resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create Git commit ({new_commit_resp.status_code}): {new_commit_resp.text}")
            new_commit_sha = new_commit_resp.json()["sha"]

            # 4. Update or create branch ref
            if branch_exists:
                ref_update_resp = client.patch(
                    f"{base_url}/git/refs/heads/{branch}",
                    headers=headers,
                    json={"sha": new_commit_sha, "force": False},
                )
                if ref_update_resp.status_code not in (200, 201):
                    raise RuntimeError(f"Failed to update branch ref ({ref_update_resp.status_code}): {ref_update_resp.text}")
            else:
                ref_create_resp = client.post(
                    f"{base_url}/git/refs",
                    headers=headers,
                    json={"ref": f"refs/heads/{branch}", "sha": new_commit_sha},
                )
                if ref_create_resp.status_code not in (200, 201):
                    raise RuntimeError(f"Failed to create branch ref ({ref_create_resp.status_code}): {ref_create_resp.text}")

            return {
                "repo": clean_repo,
                "org": org,
                "branch": branch,
                "commit_sha": new_commit_sha,
                "files": list(files_to_commit.keys()),
                "status": "committed",
            }
    except Exception as e:
        raise RuntimeError(f"Error committing approved ADR to branch '{branch}': {e}")



