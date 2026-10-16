"""Subsystem tests for Factory Testing Console and Studio UI."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from fastapi.testclient import TestClient

from factory.run import main, parse_args
from factory.ui.app import create_app
from factory.ui.github import (
    DEFAULT_TEST_ORG,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_milestones_and_issues,
    check_tanstack_start_compatibility,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    get_test_org_token,
    instantiate_repo_from_template,
    map_github_issue_status,
    parse_github_blocked_by,
    RepoCreationError,
    validate_github_repo_name,
    create_repo_milestone,
    create_repo_issue,
    resolve_or_create_milestone,
    synthesize_ticket_content,
    synthesize_and_create_issue,
    _normalize_github_issue,
    fetch_repo_pull_requests,
    merge_repo_pull_request,
    PullRequestMergeError,
    fetch_repo_branches,
    reopen_repo_issue_for_rollback,
    update_local_markdown_issue_for_rollback,
)
from factory.ui.db import StudioDatabase
from factory.ui.registry import (
    JobRegistry,
    JobStage,
    JobStatus,
    PreviewRegistry,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)


class TestGitHubPullRequestsClient(unittest.TestCase):
    """Test suite for GitHub pull request discovery and merge operations in factory/ui/github.py."""

    def test_fetch_repo_pull_requests_normalized_statuses(self):
        raw_prs = [
            {
                "id": 101,
                "number": 1,
                "title": "feat(inventory): add items table",
                "body": "Resolves initial inventory schema.\n\nFixes #1: Setup schema",
                "state": "open",
                "draft": True,
                "merged_at": None,
                "mergeable": True,
                "mergeable_state": "clean",
                "html_url": "https://github.com/software-factory-09-test/inventory-app/pull/1",
                "head": {"ref": "factory/inventory-v1"},
                "base": {"ref": "main"},
                "created_at": "2026-10-15T01:00:00Z",
                "updated_at": "2026-10-15T01:10:00Z",
            },
            {
                "id": 102,
                "number": 2,
                "title": "feat(inventory): add inventory dashboard",
                "body": "## Resolved Work Items\n- Fixes #2: Add metrics\n- Fixes #3: Add charts",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "mergeable": True,
                "mergeable_state": "clean",
                "html_url": "https://github.com/software-factory-09-test/inventory-app/pull/2",
                "head": {"ref": "factory/inventory-v2"},
                "base": {"ref": "main"},
                "created_at": "2026-10-15T02:00:00Z",
                "updated_at": "2026-10-15T02:10:00Z",
            },
            {
                "id": 103,
                "number": 3,
                "title": "feat(inventory): merged billing module",
                "body": "Completed billing.\n\nFixes #4: Add stripe",
                "state": "closed",
                "draft": False,
                "merged_at": "2026-10-15T03:00:00Z",
                "mergeable": None,
                "mergeable_state": "unknown",
                "html_url": "https://github.com/software-factory-09-test/inventory-app/pull/3",
                "head": {"ref": "factory/billing"},
                "base": {"ref": "main"},
                "created_at": "2026-10-15T02:30:00Z",
                "updated_at": "2026-10-15T03:00:00Z",
            },
            {
                "id": 104,
                "number": 4,
                "title": "feat(auth): conflict branch",
                "body": "Conflicting changes with main.",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "mergeable": False,
                "mergeable_state": "dirty",
                "html_url": "https://github.com/software-factory-09-test/inventory-app/pull/4",
                "head": {"ref": "factory/auth-conflict"},
                "base": {"ref": "main"},
                "created_at": "2026-10-15T03:15:00Z",
                "updated_at": "2026-10-15T03:20:00Z",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_prs

        with patch("httpx.Client.get", return_value=mock_resp):
            prs = fetch_repo_pull_requests(
                repo_name="inventory-app",
                token="test-token",
            )

            self.assertEqual(len(prs), 4)
            # PR 1: Draft
            self.assertEqual(prs[0]["number"], 1)
            self.assertEqual(prs[0]["status"], "draft")
            self.assertTrue(prs[0]["draft"])
            self.assertFalse(prs[0]["merged"])
            self.assertEqual(prs[0]["head_branch"], "factory/inventory-v1")
            self.assertEqual(prs[0]["base_branch"], "main")

            # PR 2: Ready for review
            self.assertEqual(prs[1]["number"], 2)
            self.assertEqual(prs[1]["status"], "ready_for_review")
            self.assertFalse(prs[1]["draft"])
            self.assertFalse(prs[1]["merged"])
            self.assertEqual(prs[1]["head_branch"], "factory/inventory-v2")

            # PR 3: Merged
            self.assertEqual(prs[2]["number"], 3)
            self.assertEqual(prs[2]["status"], "merged")
            self.assertTrue(prs[2]["merged"])

            # PR 4: Conflict
            self.assertEqual(prs[3]["number"], 4)
            self.assertEqual(prs[3]["status"], "conflict")
            self.assertFalse(prs[3]["merged"])

    def test_fetch_repo_pull_requests_branch_filtering(self):
        raw_prs = [
            {
                "id": 201,
                "number": 10,
                "title": "PR for branch A",
                "body": "",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "mergeable": True,
                "mergeable_state": "clean",
                "html_url": "https://github.com/software-factory-09-test/repo/pull/10",
                "head": {"ref": "factory/feature-a"},
                "base": {"ref": "main"},
            },
            {
                "id": 202,
                "number": 11,
                "title": "PR for branch B",
                "body": "",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "mergeable": True,
                "mergeable_state": "clean",
                "html_url": "https://github.com/software-factory-09-test/repo/pull/11",
                "head": {"ref": "factory/feature-b"},
                "base": {"ref": "main"},
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_prs

        with patch("httpx.Client.get", return_value=mock_resp):
            prs = fetch_repo_pull_requests(
                repo_name="repo",
                branch="factory/feature-b",
                token="test-token",
            )
            self.assertEqual(len(prs), 1)
            self.assertEqual(prs[0]["number"], 11)
            self.assertEqual(prs[0]["head_branch"], "factory/feature-b")

    def test_merge_repo_pull_request_squash_and_branch_deletion(self):
        pr_data = {
            "id": 105,
            "number": 4,
            "title": "Implement inventory dashboard",
            "body": "## Summary\nImplementation\n\n## Resolved Work Items\n- Fixes #1: Setup layout\n- Fixes #2: Add metrics",
            "state": "open",
            "draft": False,
            "merged": False,
            "merged_at": None,
            "mergeable": True,
            "mergeable_state": "clean",
            "head": {"ref": "factory/inventory-dashboard"},
            "base": {"ref": "main"},
        }

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = pr_data

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_put_resp.json.return_value = {
            "sha": "1a2b3c4d5e6f",
            "merged": True,
            "message": "Pull Request successfully merged",
        }

        mock_delete_resp = MagicMock()
        mock_delete_resp.status_code = 204

        with patch("httpx.Client.get", return_value=mock_get_resp), \
             patch("httpx.Client.put", return_value=mock_put_resp) as mock_put, \
             patch("httpx.Client.delete", return_value=mock_delete_resp) as mock_delete:

            res = merge_repo_pull_request(
                repo_name="inventory-app",
                pull_number=4,
                token="test-token",
            )

            self.assertTrue(res["merged"])
            self.assertEqual(res["sha"], "1a2b3c4d5e6f")
            self.assertEqual(res["pull_number"], 4)
            self.assertEqual(res["branch"], "factory/inventory-dashboard")
            self.assertTrue(res["branch_deleted"])

            # Verify squash merge payload
            mock_put.assert_called_once()
            put_args, put_kwargs = mock_put.call_args
            self.assertIn("/repos/software-factory-09-test/inventory-app/pulls/4/merge", put_args[0])
            put_json = put_kwargs["json"]
            self.assertEqual(put_json["merge_method"], "squash")
            self.assertEqual(put_json["commit_title"], "Implement inventory dashboard (#4)")
            self.assertIn("Fixes #1: Setup layout", put_json["commit_message"])
            self.assertIn("Fixes #2: Add metrics", put_json["commit_message"])

            # Verify branch deletion
            mock_delete.assert_called_once()
            del_args, _ = mock_delete.call_args
            self.assertIn("/repos/software-factory-09-test/inventory-app/git/refs/heads/factory/inventory-dashboard", del_args[0])

    def test_merge_repo_pull_request_closed_raises_error(self):
        pr_data = {
            "id": 108,
            "number": 7,
            "title": "Abandoned Feature",
            "body": "Fixes #30",
            "state": "closed",
            "draft": False,
            "merged": False,
            "merged_at": None,
            "mergeable": None,
            "head": {"ref": "factory/abandoned"},
            "base": {"ref": "main"},
        }
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = pr_data

        with patch("httpx.Client.get", return_value=mock_get_resp):
            with self.assertRaises(PullRequestMergeError) as ctx:
                merge_repo_pull_request(
                    repo_name="inventory-app",
                    pull_number=7,
                    token="test-token",
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("closed", ctx.exception.message.lower())

    def test_merge_repo_pull_request_draft_raises_error(self):
        pr_data = {
            "id": 106,
            "number": 5,
            "title": "WIP Feature",
            "body": "Fixes #10",
            "state": "open",
            "draft": True,
            "merged": False,
            "merged_at": None,
            "mergeable": True,
            "head": {"ref": "factory/wip"},
            "base": {"ref": "main"},
        }
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = pr_data

        with patch("httpx.Client.get", return_value=mock_get_resp):
            with self.assertRaises(PullRequestMergeError) as ctx:
                merge_repo_pull_request(
                    repo_name="inventory-app",
                    pull_number=5,
                    token="test-token",
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Draft", ctx.exception.message)

    def test_merge_repo_pull_request_conflict_raises_error(self):
        pr_data = {
            "id": 107,
            "number": 6,
            "title": "Conflicting Feature",
            "body": "Fixes #20",
            "state": "open",
            "draft": False,
            "merged": False,
            "merged_at": None,
            "mergeable": False,
            "mergeable_state": "dirty",
            "head": {"ref": "factory/conflict"},
            "base": {"ref": "main"},
        }
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = pr_data

        with patch("httpx.Client.get", return_value=mock_get_resp):
            with self.assertRaises(PullRequestMergeError) as ctx:
                merge_repo_pull_request(
                    repo_name="inventory-app",
                    pull_number=6,
                    token="test-token",
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("conflict", ctx.exception.message.lower())
