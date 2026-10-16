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


class TestPreviewRegistrySync(unittest.TestCase):
    """Test suite for PreviewRegistry.sync_sandbox_to_main in factory/ui/registry.py."""

    def setUp(self):
        self.preview_reg = PreviewRegistry()

    def test_sync_sandbox_to_main_executes_git_checkout_and_updates_branch(self):
        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="inventory-app",
            branch="factory/inventory-v1",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://inventory-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-inv-1",
        )
        self.preview_reg._previews["inventory-app"] = preview

        listener = self.preview_reg.add_listener("inventory-app")

        res = self.preview_reg.sync_sandbox_to_main("inventory-app")
        self.assertTrue(res)

        # Assert sandbox.exec executed checkout and pull
        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertEqual(exec_args[0], "bash")
        self.assertEqual(exec_args[1], "-c")
        exec_cmd = exec_args[2]
        self.assertIn("git reset --hard && git clean -fd && git checkout main && git pull origin main", exec_cmd)

        # Assert preview branch updated to main
        updated_preview = self.preview_reg.get_preview("inventory-app")
        self.assertIsNotNone(updated_preview)
        self.assertEqual(updated_preview.branch, "main")

        # Assert refresh event broadcasted
        self.assertFalse(listener.empty())
        events = []
        while not listener.empty():
            events.append(listener.get_nowait())
        event_types = [e["event"] for e in events]
        self.assertIn("preview_refresh", event_types)

    def test_sync_sandbox_to_main_no_active_sandbox_returns_false(self):
        res = self.preview_reg.sync_sandbox_to_main("nonexistent-repo")
        self.assertFalse(res)

    def test_sync_sandbox_to_main_command_failure_returns_false(self):
        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="inventory-app",
            branch="factory/inventory-v1",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://inventory-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-inv-1",
        )
        self.preview_reg._previews["inventory-app"] = preview

        res = self.preview_reg.sync_sandbox_to_main("inventory-app")
        self.assertFalse(res)
        self.assertEqual(preview.branch, "factory/inventory-v1")


class TestStudioPullRequestEndpoints(unittest.TestCase):
    """Test suite for GET and POST /api/studio/repos/{repo}/pulls endpoints in factory/ui/app.py."""

    def setUp(self):
        self.registry = JobRegistry()
        self.preview_registry = PreviewRegistry()
        self.db = StudioDatabase(":memory:")
        self.app = create_app(
            registry=self.registry,
            preview_reg=self.preview_registry,
            db=self.db,
        )
        self.client = TestClient(
            self.app,
            headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
        )

    def test_get_pull_requests_endpoint_unauthenticated(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.get("/api/studio/repos/test-repo/pulls")
        self.assertEqual(resp.status_code, 401)

    def test_get_pull_requests_endpoint_success(self):
        fake_prs = [
            {
                "id": 101,
                "number": 1,
                "title": "feat: init",
                "status": "ready_for_review",
                "draft": False,
                "merged": False,
                "head_branch": "factory/init",
                "base_branch": "main",
                "html_url": "https://github.com/software-factory-09-test/test-repo/pull/1",
            }
        ]
        with patch("factory.ui.app.fetch_repo_pull_requests", return_value=fake_prs) as mock_fetch:
            resp = self.client.get("/api/studio/repos/test-repo/pulls?branch=factory/init")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["repo"], "test-repo")
            self.assertEqual(len(data["pulls"]), 1)
            self.assertEqual(data["pulls"][0]["number"], 1)
            self.assertEqual(data["pulls"][0]["status"], "ready_for_review")
            mock_fetch.assert_called_once_with("test-repo", branch="factory/init", state="all")

    def test_post_merge_pull_request_success_and_persists_delivery_gate_card(self):
        fake_merge_result = {
            "merged": True,
            "sha": "fedcba987654",
            "message": "Pull Request successfully merged",
            "pull_number": 42,
            "branch": "factory/feature-42",
            "branch_deleted": True,
            "commit_title": "feat: solve ticket 42 (#42)",
            "commit_message": "Resolved work items:\n- Fixes #42: Do it",
        }

        with patch("factory.ui.app.merge_repo_pull_request", return_value=fake_merge_result) as mock_merge, \
             patch.object(self.preview_registry, "sync_sandbox_to_main", return_value=True) as mock_sync:

            resp = self.client.post("/api/studio/repos/test-repo/pulls/42/merge", json={})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertTrue(data["merged"])
            self.assertTrue(data["preview_synced"])

            mock_merge.assert_called_once()
            mock_sync.assert_called_once_with("test-repo")

            # Verify Delivery Gate Card recorded in chat_messages table
            messages = self.db.get_chat_messages("test-repo")
            self.assertEqual(len(messages), 1)
            card = messages[0]
            self.assertEqual(card["role"], "assistant")
            self.assertIn("Merged Feature Pull Request #42", card["content"])
            self.assertIsNotNone(card["turn_data"])
            self.assertEqual(card["turn_data"]["type"], "delivery_gate")
            self.assertEqual(card["turn_data"]["status"], "merged")
            self.assertTrue(card["turn_data"]["merged"])
            self.assertEqual(card["turn_data"]["pull_number"], 42)
            self.assertEqual(card["turn_data"]["sha"], "fedcba987654")

    def test_post_merge_pull_request_conflict_returns_409(self):
        with patch(
            "factory.ui.app.merge_repo_pull_request",
            side_effect=PullRequestMergeError("Pull request has merge conflicts with base branch.", status_code=409),
        ):
            resp = self.client.post("/api/studio/repos/test-repo/pulls/42/merge", json={})
            self.assertEqual(resp.status_code, 409)
            self.assertIn("merge conflicts", resp.json()["detail"])

    def test_post_merge_pull_request_blocked_when_job_running(self):
        # Create and mark a job as RUNNING for test-repo
        job = self.registry.create_job(repo="test-repo", feature="feature-42")
        with self.registry._lock:
            job.status = JobStatus.RUNNING

        resp = self.client.post("/api/studio/repos/test-repo/pulls/42/merge", json={})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("active or queued", resp.json()["detail"].lower())

    def test_post_merge_pull_request_blocked_when_job_queued(self):
        # Create and mark a job as QUEUED for test-repo
        job = self.registry.create_job(repo="test-repo", feature="feature-42")
        with self.registry._lock:
            job.status = JobStatus.QUEUED

        resp = self.client.post("/api/studio/repos/test-repo/pulls/42/merge", json={})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("active or queued", resp.json()["detail"].lower())

    def test_post_mark_pull_request_ready_for_review_success(self):
        mock_result = {
            "success": True,
            "ready_for_review": True,
            "pull_number": 42,
            "pull": {"number": 42, "draft": False, "status": "ready_for_review"},
        }
        with patch("factory.ui.routes.studio_pulls.gh.mark_pull_request_ready_for_review", return_value=mock_result):
            resp = self.client.post("/api/studio/repos/test-repo/pulls/42/ready_for_review")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertTrue(data["ready_for_review"])
            self.assertEqual(data["pull_number"], 42)

    def test_post_mark_pull_request_ready_for_review_not_found(self):
        with patch(
            "factory.ui.routes.studio_pulls.gh.mark_pull_request_ready_for_review",
            side_effect=PullRequestMergeError("Pull request #42 not found.", status_code=404),
        ):
            resp = self.client.post("/api/studio/repos/test-repo/pulls/42/ready_for_review")
            self.assertEqual(resp.status_code, 404)
            self.assertIn("not found", resp.json()["detail"])
