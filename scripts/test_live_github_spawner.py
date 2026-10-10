#!/usr/bin/env python3
"""Live Integration Test for Modal Software Factory Spawner with GitHub Issues and PR Delivery.

Tests the complete end-to-end cloud orchestration path:
1. Provisions an ephemeral Modal Sandbox via `dispatch_job` targeting `software-factory-09-test/test3`.
2. Targets remote GitHub Milestone `test-delivery-gate` (Issue #1: 'Add delimiter test and documentation').
3. Inside the container:
   - SOPS Age key bootstrap from `share0`
   - Decrypts OpenCode credentials
   - Decrypts token and clones `software-factory-09-test/test3` to `/root/test3`
   - Checks out `factory/test-delivery-gate`
   - Preserves `GH_TOKEN` for pushing and GitHub REST/GraphQL operations
   - Runs `/root/factory/pipeline.ts` for Autonomous Feature Batch using `GitHubIssueTracker`
   - Claims ticket on GitHub (`factory:claimed`)
   - Planner -> Coder -> Verifier -> Reviewer loop executes
   - Pushes commits to `factory/test-delivery-gate`
   - Creates Draft Feature Pull Request (`factory/test-delivery-gate` -> `main`)
   - Posts quality gate audit comment to Issue #1 with `factory:resolved`
   - Converts Feature Pull Request to Ready for Review
4. Verifies exit code 0.
5. Verifies GitHub Issue #1 status and comments on remote origin.
6. Verifies GitHub Pull Request status and description on remote origin.
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
    print("🚀 Live Modal Cloud Sandbox GitHub Issues & PR Delivery Test")
    print("   Target: software-factory-09-test/test3")
    print("   Milestone: test-delivery-gate")
    print("================================================================\n")

    test3_token_file = root_dir / "secrets_org" / "software-factory-09-test" / "token"
    if not test3_token_file.is_file():
        raise FileNotFoundError(f"Missing {test3_token_file}")

    token = get_test_org_token()
    if not token:
        raise ValueError("Failed to decrypt Test Organization GitHub token")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Reset Issue #1 labels to factory:ready and state to open before running
    print("🔄 Ensuring Issue #1 is open and labeled factory:ready on GitHub...")
    httpx.patch(
        "https://api.github.com/repos/software-factory-09-test/test3/issues/1",
        json={"state": "open", "labels": ["factory:ready"]},
        headers=headers,
    )

    print("🛰️  Dispatching software factory job to Modal cloud sandbox...")
    exit_code = dispatch_job(
        project="test3",
        feature="test-delivery-gate",
        testing=True,
        timeout_secs=900,  # 15 minutes upper bound for sandbox
    )

    print(f"\n🏁 Sandbox execution completed with exit code: {exit_code}")

    if exit_code != 0:
        print(f"❌ Live factory sandbox test FAILED with exit code {exit_code}")
        sys.exit(exit_code)

    # 1. Verify remote branch on GitHub
    print("\n🔍 Verifying pushed feature branch on remote GitHub repository...")
    url = f"https://x-access-token:{token}@github.com/software-factory-09-test/test3.git"
    heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", url, "factory/test-delivery-gate"],
        text=True,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    print("Remote ref:\n" + heads.strip())
    if "refs/heads/factory/test-delivery-gate" not in heads:
        print("❌ Error: factory/test-delivery-gate was NOT found on remote origin!")
        sys.exit(1)
    print("✅ Remote branch refs/heads/factory/test-delivery-gate verified on GitHub origin!")

    # 2. Verify Issue #1 on GitHub
    print("\n🔍 Verifying GitHub Issue #1 state and comments...")
    resp_issue = httpx.get(
        "https://api.github.com/repos/software-factory-09-test/test3/issues/1",
        headers=headers,
    )
    issue_data = resp_issue.json()
    issue_labels = [l["name"] for l in issue_data.get("labels", [])]
    print(f"Issue #1 labels: {issue_labels}")
    if "factory:resolved" not in issue_labels:
        print(f"❌ Expected 'factory:resolved' label on Issue #1, found: {issue_labels}")
        sys.exit(1)
    print("✅ Issue #1 is labeled 'factory:resolved'!")

    resp_comments = httpx.get(
        "https://api.github.com/repos/software-factory-09-test/test3/issues/1/comments",
        headers=headers,
    )
    comments = resp_comments.json()
    print(f"Issue #1 comment count: {len(comments)}")
    if len(comments) == 0:
        print("❌ Expected quality gate audit comment on Issue #1, but found 0 comments")
        sys.exit(1)
    print("✅ Quality gate audit comment found on Issue #1!")

    # 3. Verify Pull Request on GitHub
    print("\n🔍 Verifying Feature Pull Request on GitHub...")
    resp_prs = httpx.get(
        "https://api.github.com/repos/software-factory-09-test/test3/pulls?state=open",
        headers=headers,
    )
    prs = resp_prs.json()
    target_pr = next(
        (p for p in prs if p.get("head", {}).get("ref") == "factory/test-delivery-gate"),
        None,
    )
    if not target_pr:
        print("❌ Expected open Pull Request for branch factory/test-delivery-gate")
        sys.exit(1)

    print(f"Pull Request #{target_pr['number']}: {target_pr['title']}")
    print(f"Draft status: {target_pr.get('draft')}")
    print(f"Body snippet:\n{target_pr.get('body')[:200]}...")

    if f"Fixes #1" not in target_pr.get("body", ""):
        print("❌ Expected 'Fixes #1' reference in Pull Request body!")
        sys.exit(1)
    print("✅ Pull Request body references 'Fixes #1'!")

    if target_pr.get("draft") is not False:
        print("❌ Expected Pull Request draft status to be False (Ready for Review)!")
        sys.exit(1)
    print("✅ Pull Request is marked Ready for Review (draft: False)!")

    print("\n================================================================")
    print("🎉 LIVE MODAL FACTORY GITHUB DELIVERY VERIFICATION PASSED!")
    print("================================================================\n")


if __name__ == "__main__":
    main()
