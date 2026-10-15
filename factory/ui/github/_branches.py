"""Branch inspection, git tree fetching, template instantiation, and ADR commits."""

from collections import defaultdict
import logging
from pathlib import Path
import sys
from typing import Any
import httpx

from factory.ui.github._client import (
    DEFAULT_TEST_ORG,
    FALLBACK_REPOS,
    _fallback_repo_items,
    get_test_org_token,
    strip_repo_owner,
)
from factory.ui.github._issues import normalize_milestone_slug
from factory.ui.github._models import (
    CANONICAL_TEMPLATE_ORG,
    CANONICAL_TEMPLATE_REPO,
    RepoCreationError,
    validate_github_repo_name,
)

logger = logging.getLogger(__name__)

_template_lineage_cache: dict[str, bool] = {}


def _get_pkg():
    return sys.modules.get("factory.ui.github")


def check_tanstack_start_compatibility(repo_item: dict[str, Any]) -> bool:
    """Checks if a repository is compatible with TanStack Start template scaffolding."""
    if not repo_item or not isinstance(repo_item, dict):
        return False
    if (repo_item.get("name") or "") == CANONICAL_TEMPLATE_REPO:
        return True
    template_repo = repo_item.get("template_repository")
    if isinstance(template_repo, dict) and (template_repo.get("name") or "") == CANONICAL_TEMPLATE_REPO:
        return True
    topics = [str(t).lower() for t in repo_item.get("topics") or []]
    if "tanstack-start" in topics:
        return True
    desc = (repo_item.get("description") or "").lower()
    return "tanstack start" in desc or "@tanstack/start" in desc


def fetch_test_org_repos_detailed(
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches list of member repositories with TanStack Start compatibility indicator."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
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
                    r_name = r["name"]
                    is_compat = check_tanstack_start_compatibility(r)
                    if not is_compat and r_name not in FALLBACK_REPOS:
                        if r_name in _template_lineage_cache:
                            is_compat = _template_lineage_cache[r_name]
                        else:
                            try:
                                s_resp = client.get(f"https://api.github.com/repos/{org}/{r_name}", headers=headers)
                                if s_resp.status_code == 200:
                                    is_compat = check_tanstack_start_compatibility(s_resp.json())
                                    _template_lineage_cache[r_name] = is_compat
                            except Exception:
                                pass

                    results.append({
                        "name": r_name,
                        "is_tanstack_compatible": is_compat,
                        "description": r.get("description"),
                        "html_url": r.get("html_url") or f"https://github.com/{org}/{r_name}",
                        "topics": r.get("topics") or [],
                        "default_branch": r.get("default_branch", "main"),
                        "private": bool(r.get("private", False)),
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
    pkg = _get_pkg()
    detailed_fn = getattr(pkg, "fetch_test_org_repos_detailed", fetch_test_org_repos_detailed) if pkg else fetch_test_org_repos_detailed
    return [d["name"] for d in detailed_fn(token=token, org=org, timeout_secs=timeout_secs)]


def instantiate_repo_from_template(
    repo_name: str,
    description: str | None = None,
    private: bool = True,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    template_org: str = CANONICAL_TEMPLATE_ORG,
    template_repo: str = CANONICAL_TEMPLATE_REPO,
    timeout_secs: float = 20.0,
    poll_interval_secs: float = 1.0,
) -> dict[str, Any]:
    """Creates a new repository in the test organization instantiated from the canonical TanStack Start template."""
    valid, err_msg = validate_github_repo_name(repo_name)
    if not valid:
        raise RepoCreationError(err_msg or "Invalid repository name.", status_code=400)

    clean_name = repo_name.strip()
    pkg = _get_pkg()
    fetch_repos_fn = getattr(pkg, "fetch_test_org_repos", fetch_test_org_repos) if pkg else fetch_test_org_repos
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token

    if clean_name in fetch_repos_fn(token=token, org=org, timeout_secs=timeout_secs):
        raise RepoCreationError(f"Repository '{clean_name}' already exists in {org}.", status_code=409)

    auth_token = token or token_fn()
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
        final_desc = description.strip() if "tanstack" in description.lower() else f"{description.strip()} (TanStack Start)"
    else:
        final_desc = default_desc

    payload = {"owner": org, "name": clean_name, "description": final_desc, "include_all_branches": False, "private": private}
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
                poll_interval_secs=poll_interval_secs,
            )
        except Exception as e:
            logger.error("Failed to scaffold repository %s/%s: %s", org, clean_name, e)
            status_code = getattr(e, "status_code", 500)
            raise RepoCreationError(
                f"Repository '{clean_name}' was created from template but failed to scaffold skills and ADRs: {e}",
                status_code=status_code,
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
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    features_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    has_scratch = False

    if auth_token:
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SoftwareFactory-TestingConsole/1.0",
        }
        for branch in ("main", "master"):
            url = f"https://api.github.com/repos/{org}/{clean_repo}/git/trees/{branch}?recursive=1"
            try:
                with httpx.Client(timeout=timeout_secs) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        for item in resp.json().get("tree", []):
                            p = item.get("path", "")
                            if not p.startswith(".scratch/"):
                                continue
                            has_scratch = True
                            parts = p.split("/")
                            if len(parts) >= 4 and parts[2] == "issues" and parts[3].endswith(".md"):
                                features_map[parts[1]].append({
                                    "id": parts[3].split("-")[0],
                                    "slug": parts[3][:-3],
                                    "filename": parts[3],
                                })
                        break
            except Exception:
                pass

    feature_list = [{"slug": s, "issues": sorted(iss, key=lambda x: x["id"])} for s, iss in sorted(features_map.items())]
    return {
        "repo": clean_repo,
        "org": org,
        "has_scratch": has_scratch or bool(feature_list),
        "features": feature_list,
    }


def fetch_repo_branches(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
    default_branch: str = "main",
) -> list[str]:
    """Queries GitHub REST API GET /repos/{owner}/{repo}/branches and returns candidate branches."""
    pkg = _get_pkg()
    diag_fn = getattr(pkg, "fetch_repo_branches_with_diagnostics", fetch_repo_branches_with_diagnostics) if pkg else fetch_repo_branches_with_diagnostics
    branches, _ = diag_fn(repo_name=repo_name, token=token, org=org, timeout_secs=timeout_secs, default_branch=default_branch)
    return branches


def fetch_repo_branches_with_diagnostics(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
    default_branch: str = "main",
) -> tuple[list[str], str | None]:
    """Queries GitHub REST API GET /repos/{owner}/{repo}/branches with non-blocking diagnostic error feedback."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)
    if not auth_token:
        return [default_branch], "GitHub credentials unavailable"

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }
    url = f"https://api.github.com/repos/{org}/{clean_repo}/branches?per_page=100"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("GitHub API returned status %s for branches %s/%s", resp.status_code, org, clean_repo)
                return [default_branch], f"GitHub API error (status {resp.status_code})"
            data = resp.json()
            if not isinstance(data, list):
                return [default_branch], "Invalid GitHub response payload"
            factory_branches = [b.get("name", "") for b in data if isinstance(b, dict) and b.get("name", "").startswith("factory/")]
            return [default_branch] + sorted(set(factory_branches)), None
    except Exception as e:
        logger.warning("Failed to fetch branches for %s/%s: %s", org, clean_repo, e)
        return [default_branch], f"Network error: {e}"


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
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn(repo_root=repo_root)

    files_to_commit: dict[str, str] = {}
    if draft_adr:
        fn = draft_adr.get("filename") or f"docs/adr/0002-{normalize_milestone_slug(draft_adr.get('title') or 'decision')}.md"
        files_to_commit[fn] = draft_adr.get("content") or ""
    if context_update and context_update.strip():
        files_to_commit["CONTEXT.md"] = context_update.strip()

    if not files_to_commit:
        return {"repo": clean_repo, "org": org, "branch": branch, "status": "skipped", "files": []}
    if not auth_token:
        return {"repo": clean_repo, "org": org, "branch": branch, "status": "mocked", "files": list(files_to_commit.keys()), "commit_sha": "mock-commit-sha"}

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

            ref_resp = client.get(f"{base_url}/git/ref/heads/{branch}", headers=headers)
            if ref_resp.status_code != 200:
                ref_resp = client.get(f"{base_url}/git/refs/heads/{branch}", headers=headers)
            branch_exists = ref_resp.status_code == 200
            if branch_exists:
                commit_sha = ref_resp.json().get("object", {}).get("sha")
            else:
                main_ref = client.get(f"{base_url}/git/ref/heads/main", headers=headers)
                if main_ref.status_code != 200:
                    main_ref = client.get(f"{base_url}/git/refs/heads/main", headers=headers)
                if main_ref.status_code == 200:
                    commit_sha = main_ref.json().get("object", {}).get("sha")

            if commit_sha:
                commit_resp = client.get(f"{base_url}/git/commits/{commit_sha}", headers=headers)
                if commit_resp.status_code == 200:
                    base_tree_sha = commit_resp.json().get("tree", {}).get("sha")

            tree_payload: dict[str, Any] = {"tree": [{"path": p, "mode": "100644", "type": "blob", "content": c} for p, c in files_to_commit.items()]}
            if base_tree_sha:
                tree_payload["base_tree"] = base_tree_sha
            tree_resp = client.post(f"{base_url}/git/trees", headers=headers, json=tree_payload)
            if tree_resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create Git tree ({tree_resp.status_code}): {tree_resp.text}")

            commit_payload: dict[str, Any] = {
                "message": f"docs(adr): record architectural decision for {branch}",
                "tree": tree_resp.json()["sha"],
                "parents": [commit_sha] if commit_sha else [],
            }
            new_commit_resp = client.post(f"{base_url}/git/commits", headers=headers, json=commit_payload)
            if new_commit_resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create Git commit ({new_commit_resp.status_code}): {new_commit_resp.text}")
            new_commit_sha = new_commit_resp.json()["sha"]

            if branch_exists:
                ref_update_resp = client.patch(f"{base_url}/git/refs/heads/{branch}", headers=headers, json={"sha": new_commit_sha, "force": False})
                if ref_update_resp.status_code not in (200, 201):
                    raise RuntimeError(f"Failed to update branch ref ({ref_update_resp.status_code}): {ref_update_resp.text}")
            else:
                ref_create_resp = client.post(f"{base_url}/git/refs", headers=headers, json={"ref": f"refs/heads/{branch}", "sha": new_commit_sha})
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
