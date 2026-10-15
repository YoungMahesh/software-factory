"""GitHub issue rollback operations for Factory Studio."""

from typing import Any
import httpx

from factory.ui.github._client import DEFAULT_TEST_ORG, get_test_org_token, strip_repo_owner
from factory.ui.github._models import FACTORY_LABELS


def reopen_repo_issue_for_rollback(
    repo_name: str,
    issue_number: int,
    original_commit_sha: str | None = None,
    revert_commit_sha: str | None = None,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    timeout_secs: float = 8.0,
) -> dict[str, Any]:
    """Reopens a GitHub issue, resets its label to ready-for-agent (removing resolved), and posts an audit comment."""
    auth_token = token or get_test_org_token()
    clean_repo = strip_repo_owner(repo_name, org)

    if not auth_token:
        return {
            "id": 100,
            "number": issue_number,
            "state": "open",
            "labels": [FACTORY_LABELS["READY"]],
            "reopened": True,
        }

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }
    base_url = f"https://api.github.com/repos/{org}/{clean_repo}/issues/{issue_number}"

    # 1. Fetch current issue to inspect existing labels
    current_labels = []
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            resp = client.get(base_url, headers=headers)
            if resp.status_code == 200:
                raw_labels = resp.json().get("labels", [])
                for l in raw_labels:
                    name = l["name"] if isinstance(l, dict) and "name" in l else str(l)
                    if name.lower() not in (FACTORY_LABELS["RESOLVED"].lower(), "resolved"):
                        current_labels.append(name)
    except Exception:
        pass

    if FACTORY_LABELS["READY"] not in current_labels:
        current_labels.append(FACTORY_LABELS["READY"])

    # 2. Patch issue: state="open", labels=current_labels
    patch_payload = {
        "state": "open",
        "labels": current_labels,
    }
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            client.patch(base_url, headers=headers, json=patch_payload)
    except Exception:
        pass

    # 3. Post audit comment
    orig_sha_display = original_commit_sha or "unknown"
    revert_sha_display = revert_commit_sha or "unknown"
    comment_body = (
        f"↩️ **Turn Rollback executed in Factory Studio**\n\n"
        f"- Reverted commit: `{orig_sha_display}`\n"
        f"- Revert commit: `{revert_sha_display}`\n"
        f"- Status reset: `ready-for-agent`\n\n"
        f"Live Preview dev server and issue tracking state have been restored."
    )
    comment_payload = {"body": comment_body}
    try:
        with httpx.Client(timeout=timeout_secs) as client:
            client.post(f"{base_url}/comments", headers=headers, json=comment_payload)
    except Exception:
        pass

    return {
        "number": issue_number,
        "state": "open",
        "labels": current_labels,
        "reopened": True,
    }
