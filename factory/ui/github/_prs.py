"""Pull request discovery, normalization, delivery gate evaluation, and merge operations."""

import logging
import re
import sys
from typing import Any
import httpx

from factory.ui.github._client import DEFAULT_TEST_ORG, get_test_org_token, strip_repo_owner
from factory.ui.github._models import PullRequestMergeError

logger = logging.getLogger(__name__)


def _get_pkg():
    return sys.modules.get("factory.ui.github")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }


def _normalize_github_pull_request(item: dict[str, Any]) -> dict[str, Any]:
    """Extracts normalized pull request fields from a raw GitHub pull request payload."""
    head = item.get("head") or {}
    base = item.get("base") or {}
    head_branch = head.get("ref", "")
    base_branch = base.get("ref", "main")

    is_merged = bool(item.get("merged_at")) or bool(item.get("merged", False))
    is_draft = bool(item.get("draft", False))
    mergeable = item.get("mergeable")
    mergeable_state = item.get("mergeable_state")

    if is_merged:
        status = "merged"
    elif item.get("state") == "closed":
        status = "closed"
    elif mergeable is False or mergeable_state in ("dirty", "conflict"):
        status = "conflict"
    elif is_draft:
        status = "draft"
    else:
        status = "ready_for_review"

    return {
        "id": item.get("id"),
        "number": item.get("number"),
        "title": item.get("title", ""),
        "body": item.get("body") or "",
        "state": item.get("state", "open"),
        "status": status,
        "draft": is_draft,
        "merged": is_merged,
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "head_branch": head_branch,
        "base_branch": base_branch,
        "html_url": item.get("html_url", ""),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "merged_at": item.get("merged_at"),
        "closed_at": item.get("closed_at"),
    }


def fetch_repo_pull_requests(
    repo_name: str,
    branch: str | None = None,
    state: str = "all",
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> list[dict[str, Any]]:
    """Fetches active and recent pull requests for a repository from GitHub API."""
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)

    if not auth_token:
        return []

    url = f"https://api.github.com/repos/{org}/{clean_repo}/pulls?state={state}&per_page=100"
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(url, headers=_headers(auth_token))
            if resp.status_code == 200:
                raw_prs = resp.json()
                if not isinstance(raw_prs, list):
                    return []
                results = []
                clean_target_branch = branch.strip() if branch else None
                for raw_pr in raw_prs:
                    if not isinstance(raw_pr, dict):
                        continue
                    norm = _normalize_github_pull_request(raw_pr)
                    if clean_target_branch and norm["head_branch"] != clean_target_branch:
                        continue
                    results.append(norm)
                return results
    except Exception:
        pass
    return []


def merge_repo_pull_request(
    repo_name: str,
    pull_number: int,
    commit_title: str | None = None,
    commit_message: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 10.0,
) -> dict[str, Any]:
    """Executes a squash merge of a pull request via GitHub API, extracting Fixes #<id> directives,

    and deleting the remote feature branch upon successful merge.
    """
    pkg = _get_pkg()
    token_fn = getattr(pkg, "get_test_org_token", get_test_org_token) if pkg else get_test_org_token
    auth_token = token or token_fn()
    clean_repo = strip_repo_owner(repo_name, org)

    if not auth_token:
        raise PullRequestMergeError("Organization Credentials are required to merge pull request.", status_code=401)

    headers = _headers(auth_token)
    pr_url = f"https://api.github.com/repos/{org}/{clean_repo}/pulls/{pull_number}"
    with httpx.Client(timeout=timeout_secs) as client:
        pr_resp = client.get(pr_url, headers=headers)
        if pr_resp.status_code != 200:
            raise PullRequestMergeError(
                f"Failed to fetch pull request #{pull_number} from GitHub: {pr_resp.status_code}",
                status_code=pr_resp.status_code,
            )
        pr_data = pr_resp.json()

        if pr_data.get("draft"):
            raise PullRequestMergeError(
                f"Cannot merge pull request #{pull_number} while in Draft status.",
                status_code=400,
            )

        if pr_data.get("merged") or pr_data.get("merged_at"):
            raise PullRequestMergeError(
                f"Pull request #{pull_number} is already merged.",
                status_code=400,
            )

        if pr_data.get("state") == "closed":
            raise PullRequestMergeError(
                f"Cannot merge closed pull request #{pull_number}.",
                status_code=400,
            )

        if pr_data.get("mergeable") is False or pr_data.get("mergeable_state") in ("dirty", "conflict"):
            raise PullRequestMergeError(
                f"Pull request #{pull_number} has merge conflicts with base branch and cannot be merged automatically.",
                status_code=409,
            )

        final_commit_title = commit_title or f"{pr_data.get('title', '').strip()} (#{pull_number})"

        if commit_message:
            final_commit_message = commit_message
        else:
            body = pr_data.get("body") or ""
            lines = [line.strip() for line in body.splitlines() if re.search(r"Fixes\s+#\d+", line, re.IGNORECASE)]
            if lines:
                formatted_lines = [f"- {l.lstrip('-* ').strip()}" for l in lines]
                final_commit_message = "Resolved work items:\n" + "\n".join(formatted_lines)
            else:
                final_commit_message = body or f"Squash merge pull request #{pull_number}"

        merge_url = f"https://api.github.com/repos/{org}/{clean_repo}/pulls/{pull_number}/merge"
        merge_payload = {
            "commit_title": final_commit_title,
            "commit_message": final_commit_message,
            "merge_method": "squash",
        }
        merge_resp = client.put(merge_url, headers=headers, json=merge_payload)
        if merge_resp.status_code != 200:
            err_code = 409 if merge_resp.status_code == 409 else (merge_resp.status_code if merge_resp.status_code >= 400 else 400)
            raise PullRequestMergeError(
                f"GitHub squash merge failed for pull request #{pull_number}: {merge_resp.text}",
                status_code=err_code,
            )
        merge_result = merge_resp.json()

        head = pr_data.get("head") or {}
        head_branch = head.get("ref", "")
        branch_deleted = False

        if head_branch and head_branch not in ("main", "master"):
            clean_branch = head_branch
            if clean_branch.startswith("refs/heads/"):
                clean_branch = clean_branch[len("refs/heads/"):]
            delete_ref_url = f"https://api.github.com/repos/{org}/{clean_repo}/git/refs/heads/{clean_branch}"
            try:
                del_resp = client.delete(delete_ref_url, headers=headers)
                if del_resp.status_code in (200, 204, 404):
                    branch_deleted = True
            except Exception:
                pass

        return {
            "merged": True,
            "sha": merge_result.get("sha"),
            "message": merge_result.get("message"),
            "pull_number": pull_number,
            "branch": head_branch,
            "branch_deleted": branch_deleted,
            "commit_title": final_commit_title,
            "commit_message": final_commit_message,
        }


def mark_pull_request_ready_for_review(repo_name: str, pull_number: int) -> dict[str, Any]:
    """Converts a draft pull request to ready for review via GitHub GraphQL mutation."""
    clean_repo = strip_repo_owner(repo_name)
    org = DEFAULT_TEST_ORG
    token = get_test_org_token()
    if not token:
        raise PullRequestMergeError(
            "GitHub test organization token is not configured.",
            status_code=500,
        )

    headers = _headers(token)
    with httpx.Client(timeout=20.0) as client:
        pr_url = f"https://api.github.com/repos/{org}/{clean_repo}/pulls/{pull_number}"
        pr_resp = client.get(pr_url, headers=headers)
        if pr_resp.status_code == 404:
            raise PullRequestMergeError(f"Pull request #{pull_number} not found.", status_code=404)
        if pr_resp.status_code != 200:
            raise PullRequestMergeError(
                f"Failed to fetch pull request #{pull_number}: {pr_resp.text}",
                status_code=pr_resp.status_code,
            )
        pr_data = pr_resp.json()
        node_id = pr_data.get("node_id")
        if not node_id:
            raise PullRequestMergeError("Pull request node_id could not be resolved.", status_code=500)

        graphql_url = "https://api.github.com/graphql"
        mutation = {
            "query": "mutation($id: ID!) { markPullRequestReadyForReview(input: {pullRequestId: $id}) { pullRequest { id isDraft } } }",
            "variables": {"id": node_id},
        }
        gql_resp = client.post(graphql_url, headers=headers, json=mutation)
        if gql_resp.status_code != 200:
            raise PullRequestMergeError(
                f"Failed to mark pull request #{pull_number} ready for review: {gql_resp.text}",
                status_code=gql_resp.status_code,
            )

        refetch_resp = client.get(pr_url, headers=headers)
        if refetch_resp.status_code == 200:
            updated_pr = _normalize_github_pull_request(refetch_resp.json())
        else:
            updated_pr = _normalize_github_pull_request(pr_data)
            updated_pr["draft"] = False
            updated_pr["status"] = "ready_for_review"

        return {
            "success": True,
            "ready_for_review": True,
            "pull_number": pull_number,
            "pull": updated_pr,
        }

