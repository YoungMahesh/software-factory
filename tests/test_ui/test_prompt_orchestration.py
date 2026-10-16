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


class TestConversationalPromptOrchestration(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.preview_registry = PreviewRegistry()
        self.app = create_app(registry=self.registry, preview_reg=self.preview_registry)
        self.client = TestClient(
            self.app,
            headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
        )

    def test_prompt_endpoint_missing_repo_returns_400(self):
        resp = self.client.post("/api/studio/prompt", json={"repo": "", "prompt": "Build a calculator"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Repository name is required", resp.json()["detail"])

    def test_prompt_endpoint_missing_prompt_returns_400(self):
        resp = self.client.post("/api/studio/prompt", json={"repo": "test3", "prompt": "   "})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Prompt is required", resp.json()["detail"])

    def test_prompt_endpoint_accepts_database_prompt_for_grilling(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Build a user login app with a PostgreSQL database and Prisma migrations",
                "mock": True,
                "grill": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["refusal"])
        self.assertIsNotNone(data["turn"])

    def test_prompt_endpoint_accepts_backend_and_storage_prompts(self):
        prompts = [
            "Build a FastAPI backend server with background worker endpoints",
            "Upload and store customer documents in an AWS S3 bucket",
        ]
        for p in prompts:
            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test3",
                    "prompt": p,
                    "mock": True,
                    "grill": True,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertIsNone(data["refusal"])
            self.assertIsNotNone(data["turn"])

    @patch("factory.ui.app.resolve_or_create_milestone")
    @patch("factory.ui.app.synthesize_and_create_issue")
    def test_prompt_endpoint_accepts_valid_frontend_prompt_and_orchestrates_job(
        self,
        mock_synthesize_issue,
        mock_resolve_milestone,
    ):
        mock_resolve_milestone.return_value = {
            "id": 991,
            "number": 1,
            "title": "v1: Initial App",
            "slug": "v1-initial-app",
            "html_url": "https://github.com/software-factory-09-test/test-calc/milestone/1",
        }
        mock_synthesize_issue.return_value = {
            "id": 771,
            "number": 1,
            "title": "01: Calculator UI And Logic",
            "body": "# 01...",
            "html_url": "https://github.com/software-factory-09-test/test-calc/issues/1",
        }
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-1"
        self.preview_registry._previews["test3"] = PreviewState(
            repo="test3",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://sb-active-1-3000.modal.host",
            sandbox_id="sb-active-1",
            sandbox=mock_sandbox,
        )

        with patch.object(self.registry, "start_job") as mock_start_job:
            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build a responsive calculator app with arithmetic history and dark mode",
                    "model": "deepseek-v4.1-flash",
                    "vm": False,
                    "grill": False,
                },
            )


            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertIsNone(data["refusal"])
            self.assertIsNotNone(data["job"])
            self.assertEqual(data["job"]["repo"], "test3")
            self.assertEqual(data["job"]["feature"], "v1-initial-app")
            self.assertEqual(data["job"]["issue"], "1")
            self.assertTrue(data["job"]["dev"])
            self.assertEqual(data["job"]["preview_url"], "https://sb-active-1-3000.modal.host")
            self.assertEqual(data["preview_url"], "https://sb-active-1-3000.modal.host")
            self.assertIsNotNone(data["preview"])
            self.assertEqual(data["preview"]["status"], "SERVING")
            self.assertEqual(data["preview"]["branch"], "factory/v1-initial-app")
            self.assertEqual(data["milestone"]["number"], 1)
            self.assertEqual(data["milestone"]["slug"], "v1-initial-app")
            self.assertEqual(data["issue"]["number"], 1)
            self.assertEqual(data["stage"], JobStage.IDLE.value)

            mock_resolve_milestone.assert_called_once_with(
                repo_name="test3",
                title=None,
            )
            mock_synthesize_issue.assert_called_once()
            mock_start_job.assert_called_once()

    @patch("factory.ui.app.resolve_or_create_milestone")
    @patch("factory.ui.app.synthesize_and_create_issue")
    @patch("factory.ui.registry.create_preview_sandbox")
    def test_prompt_endpoint_auto_provisions_when_no_active_sandbox(
        self,
        mock_create_preview,
        mock_synthesize_issue,
        mock_resolve_milestone,
    ):
        mock_resolve_milestone.return_value = {
            "id": 992,
            "number": 2,
            "title": "v2: Auto Provision Feature",
            "slug": "v2-auto-provision-feature",
        }
        mock_synthesize_issue.return_value = {
            "id": 772,
            "number": 2,
            "title": "02: Auto Provision Issue",
            "body": "...",
        }
        import threading
        stop_event = threading.Event()
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-auto-99"
        mock_sandbox.stdout = iter(["🌟 Launching Dev Preview Keep-Alive Daemon\n", "Dev server running on port 3000\n"])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.side_effect = lambda **kwargs: stop_event.wait(timeout=2.0)
        mock_sandbox.terminate = MagicMock(side_effect=lambda: stop_event.set())
        mock_sandbox.returncode = 0
        mock_create_preview.return_value = (mock_sandbox, "https://sb-auto-99-3000.modal.host")

        with patch.object(self.registry, "start_job") as mock_start_job:
            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test-inactive",
                    "prompt": "Build an auto-provisioned preview feature",
                    "model": "deepseek-v4.1-flash",
                    "grill": False,
                },
            )


            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["preview_url"], "https://sb-auto-99-3000.modal.host")
            self.assertEqual(data["job"]["preview_url"], "https://sb-auto-99-3000.modal.host")
            self.assertIsNotNone(data["preview"])
            self.assertEqual(data["preview"]["status"], "SERVING")
            self.assertEqual(data["preview"]["preview_url"], "https://sb-auto-99-3000.modal.host")
            self.assertEqual(data["preview"]["branch"], "factory/v2-auto-provision-feature")
            mock_create_preview.assert_called_once()
            mock_start_job.assert_called_once()

    @patch("factory.ui.app.resolve_or_create_milestone")
    @patch("factory.ui.app.synthesize_and_create_issue")
    @patch("factory.ui.registry.create_preview_sandbox")
    def test_prompt_endpoint_auto_provision_failure_returns_500(
        self,
        mock_create_preview,
        mock_synthesize_issue,
        mock_resolve_milestone,
    ):
        mock_resolve_milestone.return_value = {
            "id": 994,
            "number": 4,
            "title": "v4: Failing Feature",
            "slug": "v4-failing-feature",
        }
        mock_synthesize_issue.return_value = {
            "id": 774,
            "number": 4,
            "title": "04: Failing Issue",
            "body": "...",
        }
        mock_create_preview.side_effect = RuntimeError("Modal provisioning timeout")

        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test-fail-provision",
                "prompt": "Build a feature that fails sandbox provisioning",
                "model": "deepseek-v4.1-flash",
                "grill": False,
            },
        )


        self.assertEqual(resp.status_code, 500)
        self.assertIn("Unified Studio Sandbox failed to start", resp.json()["detail"])

    @patch("factory.ui.app.resolve_or_create_milestone")
    @patch("factory.ui.app.synthesize_and_create_issue")
    def test_prompt_endpoint_in_place_branch_transition_and_execution_delegation(
        self,
        mock_synthesize_issue,
        mock_resolve_milestone,
    ):
        mock_resolve_milestone.return_value = {
            "id": 993,
            "number": 3,
            "title": "v3: In Place Feature",
            "slug": "v3-in-place-feature",
        }
        mock_synthesize_issue.return_value = {
            "id": 773,
            "number": 3,
            "title": "03: Feature Issue",
            "body": "...",
        }
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-reuse"
        mock_process = MagicMock()
        mock_process.stdout = iter(["In-container pipeline executed successfully\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-reuse",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://sb-reuse-3000.modal.host",
            sandbox_id="sb-active-reuse",
            sandbox=mock_sandbox,
        )
        self.preview_registry._previews["test-reuse"] = preview

        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test-reuse",
                "prompt": "Add navigation header",
                "model": "deepseek-v4.1-flash",
                "grill": False,
            },
        )


        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertEqual(data["preview_url"], "https://sb-reuse-3000.modal.host")
        self.assertEqual(preview.branch, "factory/v3-in-place-feature")

        job_id = data["job"]["id"]
        # Wait for worker thread to complete execution
        import time
        for _ in range(50):
            j = self.registry.get_job(job_id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break
            time.sleep(0.05)

        j = self.registry.get_job(job_id)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "SUCCESS")
        self.assertTrue(j.is_in_sandbox_exec)

        # Verify in-sandbox execution command
        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertEqual(exec_args[0], "bash")
        self.assertEqual(exec_args[1], "-c")
        exec_cmd = exec_args[2]
        self.assertIn("--workspace /root/test-reuse", exec_cmd)
        self.assertIn("--feature v3-in-place-feature", exec_cmd)
        self.assertIn("--studio", exec_cmd)
        self.assertIn("STUDIO_MODE=1", exec_cmd)

    @patch("factory.ui.app.resolve_or_create_milestone")
    @patch("factory.ui.app.synthesize_and_create_issue")
    def test_prompt_endpoint_alias_api_prompt(
        self,
        mock_synthesize_issue,
        mock_resolve_milestone,
    ):
        mock_resolve_milestone.return_value = {
            "id": 991,
            "number": 1,
            "title": "v1: Initial App",
            "slug": "v1-initial-app",
        }
        mock_synthesize_issue.return_value = {
            "id": 771,
            "number": 1,
            "title": "01: App",
            "body": "# 01...",
        }
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-alias"
        self.preview_registry._previews["test3"] = PreviewState(
            repo="test3",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://sb-alias-3000.modal.host",
            sandbox_id="sb-active-alias",
            sandbox=mock_sandbox,
        )
        with patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build a simple weather dashboard",
                    "grill": False,
                },
            )

            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["accepted"])
            self.assertEqual(resp.json()["preview_url"], "https://sb-alias-3000.modal.host")

    def test_prompt_endpoint_unauthenticated_returns_401(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.post(
            "/api/studio/prompt",
            json={"repo": "test3", "prompt": "Build a calculator"},
        )
        self.assertEqual(resp.status_code, 401)
