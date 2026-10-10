#!/usr/bin/env python3
"""Live Integration Test for Ad-hoc Single Issue Dispatch into Modal Sandbox.

Tests:
1. Creates an unassigned ad-hoc issue on GitHub (software-factory-09-test/test3).
2. Dispatches via `dispatch_job(project='test3', issue=str(issue_num), testing=True)`.
3. Verifies that the sandbox runs on branch `factory/issue-<id>`.
4. Verifies commit push, isolated PR creation (`Fixes #<id>`), issue resolution, and PR finalization.
"""

from pathlib import Path
import subprocess
import sys
import httpx

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from factory.orchestrator import dispatch_job
from factory.ui.github import get_test_org_token


def main() -> None:
    print("================================================================")
    print("🚀 Live Modal Cloud Sandbox Ad-hoc Single Issue Dispatch Test")
    print("================================================================\n")

    token = get_test_org_token()
    if not token:
        raise ValueError("Missing Test Organization token")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Create ad-hoc issue without a milestone
    issue_data = {
        "title": "Add readme documentation for delimiter option",
        "body": "What to build: Add an example of delimiter option in readme.md.\n\nBlocked by: None",
        "labels": ["factory:ready"],
    }
    resp = httpx.post(
        "https://api.github.com/repos/software-factory-09-test/test3/issues",
        json=issue_data,
        headers=headers,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"Failed to create ad-hoc issue: {resp.status_code} {resp.text}")

    issue_num = resp.json()["number"]
    print(f"Created ad-hoc Issue #{issue_num}: '{issue_data['title']}'")

    print(f"🛰️  Dispatching ad-hoc single issue #{issue_num} to Modal sandbox...")
    exit_code = dispatch_job(
        project="test3",
        issue=str(issue_num),
        testing=True,
        timeout_secs=900,
    )

    print(f"\n🏁 Sandbox completed with exit code: {exit_code}")
    if exit_code != 0:
        print(f"❌ Ad-hoc single issue test failed with exit code {exit_code}")
        sys.exit(exit_code)

    branch_name = f"factory/issue-{issue_num}"
    url = f"https://x-access-token:{token}@github.com/software-factory-09-test/test3.git"
    heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", url, branch_name],
        text=True,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    print(f"Remote ref:\n{heads.strip()}")
    if f"refs/heads/{branch_name}" not in heads:
        print(f"❌ Expected branch {branch_name} on GitHub origin!")
        sys.exit(1)
    print(f"✅ Verified branch refs/heads/{branch_name} on remote origin!")

    # Verify Issue resolution
    resp_issue = httpx.get(
        f"https://api.github.com/repos/software-factory-09-test/test3/issues/{issue_num}",
        headers=headers,
    )
    labels = [l["name"] for l in resp_issue.json().get("labels", [])]
    print(f"Issue #{issue_num} labels: {labels}")
    if "factory:resolved" not in labels:
        print(f"❌ Expected 'factory:resolved' label on Issue #{issue_num}")
        sys.exit(1)
    print(f"✅ Verified Issue #{issue_num} is labeled 'factory:resolved'!")

    # Verify PR
    resp_prs = httpx.get(
        "https://api.github.com/repos/software-factory-09-test/test3/pulls?state=open",
        headers=headers,
    )
    prs = resp_prs.json()
    target_pr = next(
        (p for p in prs if p.get("head", {}).get("ref") == branch_name),
        None,
    )
    if not target_pr:
        print(f"❌ Expected Pull Request for branch {branch_name}")
        sys.exit(1)

    print(f"Pull Request #{target_pr['number']}: {target_pr['title']}")
    print(f"Draft status: {target_pr.get('draft')}")
    if f"Fixes #{issue_num}" not in target_pr.get("body", ""):
        print(f"❌ Expected 'Fixes #{issue_num}' in PR body")
        sys.exit(1)
    print(f"✅ Pull Request references 'Fixes #{issue_num}'!")
    if target_pr.get("draft") is not False:
        print(f"❌ Expected PR draft status to be False")
        sys.exit(1)
    print("✅ Pull Request is Ready for Review!")

    print("\n================================================================")
    print("🎉 LIVE AD-HOC SINGLE ISSUE MODAL SANDBOX VERIFICATION PASSED!")
    print("================================================================\n")


if __name__ == "__main__":
    main()
