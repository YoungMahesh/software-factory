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


class TestStudioDispatchEndpoint(unittest.TestCase):
    """Test suite for POST /api/studio/dispatch endpoint."""

    def setUp(self):
        from factory.ui.db import StudioDatabase
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

    def _register_serving_preview(self, repo: str, preview_url: str = "https://preview.modal.host") -> PreviewState:
        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        state = PreviewState(
            repo=repo,
            status=PreviewStatus.SERVING,
            preview_url=preview_url,
            sandbox=mock_sandbox,
            sandbox_id=f"sb-{repo}",
        )
        self.preview_registry._previews[repo] = state
        return state

    def test_dispatch_endpoint_unauthenticated_returns_401(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.post(
            "/api/studio/dispatch",
            json={"repo": "test3", "milestone_slug": "v1-core"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_dispatch_endpoint_missing_repo_returns_400(self):
        resp = self.client.post(
            "/api/studio/dispatch",
            json={"repo": "", "milestone_slug": "v1-core"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Repository name is required", resp.json()["detail"])

    def test_dispatch_endpoint_missing_milestone_and_issue_returns_400(self):
        resp = self.client.post(
            "/api/studio/dispatch",
            json={"repo": "test3"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Either milestone or issue number must be provided", resp.json()["detail"])

    def test_dispatch_milestone_batch_binds_branch_and_attaches_preview_url(self):
        self._register_serving_preview("test3", "https://preview-3000.modal.host")

        with patch.object(self.registry, "start_job") as mock_start_job:
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "test3",
                    "milestone_title": "v1: Initial App",
                    "model": "mimo-v2.6-flash",
                    "vm": True,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["milestone_slug"], "v1-initial-app")
            self.assertEqual(data["branch"], "factory/v1-initial-app")
            self.assertEqual(data["target_branch"], "factory/v1-initial-app")
            self.assertEqual(data["preview_url"], "https://preview-3000.modal.host")
            self.assertIsNone(data["issue_number"])

            job_id = data["job"]["id"]
            job = self.registry.get_job(job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job.repo, "test3")
            self.assertEqual(job.feature, "v1-initial-app")
            self.assertIsNone(job.issue)
            self.assertEqual(job.model, "mimo-v2.6-flash")
            self.assertTrue(job.vm)
            self.assertTrue(job.dev)
            self.assertEqual(job.preview_url, "https://preview-3000.modal.host")
            mock_start_job.assert_called_once_with(job_id)

    def test_dispatch_milestone_associated_issue_with_explicit_milestone(self):
        self._register_serving_preview("test3", "https://preview-3000.modal.host")

        with patch.object(self.registry, "start_job") as mock_start_job:
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "test3",
                    "issue_number": 42,
                    "milestone_slug": "feature-auth",
                    "model": "deepseek-v4.1-flash",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["issue_number"], 42)
            self.assertEqual(data["milestone_slug"], "feature-auth")
            self.assertEqual(data["branch"], "factory/feature-auth")
            self.assertEqual(data["target_branch"], "factory/feature-auth")

            job = self.registry.get_job(data["job"]["id"])
            self.assertIsNotNone(job)
            self.assertEqual(job.feature, "feature-auth")
            self.assertEqual(job.issue, "42")
            self.assertTrue(job.dev)

    def test_dispatch_milestone_associated_issue_resolves_from_github(self):
        self._register_serving_preview("test3", "https://preview-3000.modal.host")

        fake_github_issue = {
            "number": 15,
            "title": "Setup OAuth login",
            "milestone": {
                "number": 3,
                "title": "Auth & Users",
                "slug": "auth-users",
            },
        }

        with patch("factory.ui.app.fetch_repo_issue", return_value=fake_github_issue) as mock_fetch, \
             patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "test3",
                    "issue_number": 15,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["issue_number"], 15)
            self.assertEqual(data["milestone_slug"], "auth-users")
            self.assertEqual(data["branch"], "factory/auth-users")
            self.assertEqual(data["target_branch"], "factory/auth-users")

            job = self.registry.get_job(data["job"]["id"])
            self.assertEqual(job.feature, "auth-users")
            self.assertEqual(job.issue, "15")

    def test_dispatch_standalone_issue_binds_to_target_branch(self):
        self._register_serving_preview("test3", "https://preview-3000.modal.host")

        fake_standalone_issue = {
            "number": 88,
            "title": "Fix navbar alignment",
            "milestone": None,
        }

        with patch("factory.ui.app.fetch_repo_issue", return_value=fake_standalone_issue) as mock_fetch, \
             patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "test3",
                    "issue_number": 88,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["issue_number"], 88)
            self.assertIsNone(data["milestone_slug"])
            self.assertEqual(data["branch"], "factory/issue-88")
            self.assertEqual(data["target_branch"], "factory/issue-88")

            job = self.registry.get_job(data["job"]["id"])
            self.assertEqual(job.feature, "issue-88")
            self.assertEqual(job.issue, "88")

    def test_dispatch_persists_structured_execution_card_in_studio_database(self):
        self._register_serving_preview("chat-repo", "https://preview-chat.modal.host")

        with patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "chat-repo",
                    "issue_number": 10,
                    "milestone_title": "v2: Dashboard",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            job_id = data["job"]["id"]

            # Query database directly
            messages = self.db.get_chat_messages("chat-repo")
            self.assertEqual(len(messages), 1)
            card = messages[0]
            self.assertEqual(card["role"], "assistant")
            self.assertEqual(card["milestone_slug"], "v2-dashboard")
            self.assertEqual(card["issue_number"], 10)
            self.assertIsNotNone(card["turn_data"])
            self.assertEqual(card["turn_data"]["job_id"], job_id)
            self.assertEqual(card["turn_data"]["issue_number"], 10)
            self.assertEqual(card["turn_data"]["milestone_slug"], "v2-dashboard")
            self.assertEqual(card["turn_data"]["target_branch"], "factory/v2-dashboard")
            self.assertEqual(card["turn_data"]["preview_url"], "https://preview-chat.modal.host")

            # Query messages endpoint
            msg_resp = self.client.get("/api/studio/repos/chat-repo/messages")
            self.assertEqual(msg_resp.status_code, 200)
            endpoint_messages = msg_resp.json()["messages"]
            self.assertEqual(len(endpoint_messages), 1)
            self.assertEqual(endpoint_messages[0]["turn_data"]["job_id"], job_id)

    def test_dispatch_milestone_batch_persists_card_without_issue_number(self):
        self._register_serving_preview("batch-repo", "https://preview-batch.modal.host")

        with patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "batch-repo",
                    "milestone_slug": "release-v1",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            messages = self.db.get_chat_messages("batch-repo")
            self.assertEqual(len(messages), 1)
            card = messages[0]
            self.assertEqual(card["role"], "assistant")
            self.assertEqual(card["milestone_slug"], "release-v1")
            self.assertIsNone(card["issue_number"])
            self.assertEqual(card["turn_data"]["job_id"], data["job"]["id"])
            self.assertIsNone(card["turn_data"]["issue_number"])
            self.assertEqual(card["turn_data"]["milestone_slug"], "release-v1")
            self.assertEqual(card["turn_data"]["target_branch"], "factory/release-v1")

    def test_dispatch_standalone_issue_persists_card_without_milestone_slug(self):
        self._register_serving_preview("standalone-repo", "https://preview-standalone.modal.host")

        with patch("factory.ui.app.fetch_repo_issue", return_value=None), \
             patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/studio/dispatch",
                json={
                    "repo": "standalone-repo",
                    "issue_number": 77,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            messages = self.db.get_chat_messages("standalone-repo")
            self.assertEqual(len(messages), 1)
            card = messages[0]
            self.assertEqual(card["role"], "assistant")
            self.assertIsNone(card["milestone_slug"])
            self.assertEqual(card["issue_number"], 77)
            self.assertEqual(card["turn_data"]["job_id"], data["job"]["id"])
            self.assertEqual(card["turn_data"]["issue_number"], 77)
            self.assertIsNone(card["turn_data"]["milestone_slug"])
            self.assertEqual(card["turn_data"]["target_branch"], "factory/issue-77")
