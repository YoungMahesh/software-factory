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


class TestFastApiApp(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp.text)
        self.assertIn("Software Factory", resp.text)

    def test_get_repos_endpoint(self):
        resp = self.client.get("/api/repos")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["org"], DEFAULT_TEST_ORG)
        self.assertTrue(isinstance(data["repos"], list))

    @patch("factory.ui.app.fetch_test_org_repos_detailed")
    def test_get_repos_with_tanstack_compatibility_indicator(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "name": "test1",
                "is_tanstack_compatible": False,
                "description": None,
                "html_url": "https://github.com/software-factory-09-test/test1",
            },
            {
                "name": "cool-app",
                "is_tanstack_compatible": True,
                "description": "TanStack Start app",
                "html_url": "https://github.com/software-factory-09-test/cool-app",
            },
        ]
        resp = self.client.get("/api/repos")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["org"], DEFAULT_TEST_ORG)
        self.assertEqual(len(data["repos"]), 2)
        self.assertEqual(data["repos"][0]["name"], "test1")
        self.assertFalse(data["repos"][0]["is_tanstack_compatible"])
        self.assertEqual(data["repos"][1]["name"], "cool-app")
        self.assertTrue(data["repos"][1]["is_tanstack_compatible"])

        # Studio dedicated endpoint
        resp_studio = self.client.get("/api/studio/repos")
        self.assertEqual(resp_studio.status_code, 200)
        data_studio = resp_studio.json()
        self.assertEqual(len(data_studio["repos"]), 2)
        self.assertTrue(data_studio["repos"][1]["is_tanstack_compatible"])

    def test_create_repo_endpoint_validation_invalid_slug(self):
        resp = self.client.post("/api/repos", json={"name": "invalid slug!"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("alphanumeric", resp.json()["detail"].lower())

    def test_create_repo_endpoint_empty_name(self):
        resp = self.client.post("/api/repos", json={"name": ""})
        self.assertEqual(resp.status_code, 400)

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_duplicate_conflict(self, mock_instantiate):
        mock_instantiate.side_effect = RepoCreationError(
            "Repository 'existing-app' already exists in software-factory-09-test.",
            status_code=409,
        )
        resp = self.client.post("/api/repos", json={"name": "existing-app"})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("already exists", resp.json()["detail"])

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_github_gateway_error(self, mock_instantiate):
        mock_instantiate.side_effect = RepoCreationError(
            "GitHub API error (502): Bad Gateway",
            status_code=502,
        )
        resp = self.client.post("/api/repos", json={"name": "gateway-err-app"})
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.json()["detail"], "GitHub API error (502): Bad Gateway")

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_success(self, mock_instantiate):
        mock_instantiate.return_value = {
            "name": "my-portfolio",
            "full_name": "software-factory-09-test/my-portfolio",
            "html_url": "https://github.com/software-factory-09-test/my-portfolio",
            "description": "Portfolio frontend",
            "private": True,
            "is_tanstack_compatible": True,
            "template_repository": "software-factory-09-test/tanstack-start-template",
        }
        resp = self.client.post("/api/repos", json={"name": "my-portfolio", "description": "Portfolio frontend"})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "my-portfolio")
        self.assertTrue(data["is_tanstack_compatible"])
        self.assertTrue(data["private"])
        self.assertEqual(data["template_repository"], "software-factory-09-test/tanstack-start-template")
        mock_instantiate.assert_called_once_with(
            repo_name="my-portfolio",
            description="Portfolio frontend",
            private=True,
        )

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_explicit_public(self, mock_instantiate):
        mock_instantiate.return_value = {
            "name": "my-public-portfolio",
            "full_name": "software-factory-09-test/my-public-portfolio",
            "html_url": "https://github.com/software-factory-09-test/my-public-portfolio",
            "description": "Public portfolio",
            "private": False,
            "is_tanstack_compatible": True,
            "template_repository": "software-factory-09-test/tanstack-start-template",
        }
        resp = self.client.post(
            "/api/repos",
            json={"name": "my-public-portfolio", "description": "Public portfolio", "private": False},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "my-public-portfolio")
        self.assertFalse(data["private"])
        mock_instantiate.assert_called_once_with(
            repo_name="my-public-portfolio",
            description="Public portfolio",
            private=False,
        )

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_studio_alias(self, mock_instantiate):
        mock_instantiate.return_value = {
            "name": "studio-app",
            "full_name": "software-factory-09-test/studio-app",
            "html_url": "https://github.com/software-factory-09-test/studio-app",
            "description": None,
            "private": True,
            "is_tanstack_compatible": True,
            "template_repository": "software-factory-09-test/tanstack-start-template",
        }
        resp = self.client.post("/api/studio/repos", json={"name": "studio-app"})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "studio-app")
        mock_instantiate.assert_called_once_with(
            repo_name="studio-app",
            description=None,
            private=True,
        )

    def test_get_repo_scratch_endpoint_returns_404(self):
        resp = self.client.get("/api/repos/test3/scratch")
        self.assertEqual(resp.status_code, 404)

    @patch("factory.ui.app.fetch_repo_milestones_and_issues")
    def test_get_repo_milestones_endpoint(self, mock_fetch):
        mock_fetch.return_value = {
            "repo": "test3",
            "org": DEFAULT_TEST_ORG,
            "milestones": [
                {
                    "number": 1,
                    "title": "queues-page",
                    "issues": [{"number": 10, "title": "Init", "status": "ready-for-agent", "blocked_by": []}],
                }
            ],
        }
        resp = self.client.get("/api/repos/test3/milestones")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertEqual(len(data["milestones"]), 1)
        self.assertEqual(data["milestones"][0]["title"], "queues-page")
        mock_fetch.assert_called_once_with("test3")

    @patch("factory.ui.app.fetch_repo_issues")
    def test_get_repo_issues_endpoint(self, mock_fetch):
        mock_fetch.return_value = [
            {"number": 10, "title": "Init", "status": "ready-for-agent", "blocked_by": []}
        ]
        resp = self.client.get("/api/repos/test3/issues?milestone=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertEqual(len(data["issues"]), 1)
        mock_fetch.assert_called_once_with("test3", milestone_number=1, state="all")

    @patch("factory.ui.app.fetch_repo_issue")
    def test_get_repo_single_issue_endpoint(self, mock_fetch):
        mock_fetch.return_value = {
            "number": 42,
            "title": "Bugfix",
            "status": "claimed",
            "blocked_by": [],
        }
        resp = self.client.get("/api/repos/test3/issues/42")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["number"], 42)

        # 404 case
        mock_fetch.return_value = None
        resp_404 = self.client.get("/api/repos/test3/issues/999")
        self.assertEqual(resp_404.status_code, 404)

    def test_launch_job_validation(self):
        # Missing both feature and issue
        resp1 = self.client.post("/api/jobs", json={"repo": "test3", "feature": "", "issue": ""})
        self.assertEqual(resp1.status_code, 400)

        # Missing repo
        resp2 = self.client.post("/api/jobs", json={"repo": "", "feature": "feat"})
        self.assertEqual(resp2.status_code, 400)

    @patch.object(JobRegistry, "start_job")
    def test_launch_job_adhoc_issue_without_feature(self, mock_start_job):
        payload = {
            "repo": "test3",
            "issue": "42",
            "model": "deepseek-v4.1-flash",
            "vm": False,
        }
        resp = self.client.post("/api/jobs", json=payload)
        self.assertEqual(resp.status_code, 200)
        job_data = resp.json()
        self.assertEqual(job_data["repo"], "test3")
        self.assertEqual(job_data["issue"], "42")
        self.assertEqual(job_data["feature"], "issue-42")
        mock_start_job.assert_called_once_with(job_data["id"])

    @patch.object(JobRegistry, "start_job")
    def test_launch_job_success(self, mock_start_job):
        payload = {
            "repo": "test3",
            "feature": "slug-generator",
            "issue": "01",
            "model": "deepseek-v4.1-flash",
            "vm": False,
        }
        resp = self.client.post("/api/jobs", json=payload)
        self.assertEqual(resp.status_code, 200)
        job_data = resp.json()
        self.assertEqual(job_data["repo"], "test3")
        self.assertEqual(job_data["feature"], "slug-generator")
        self.assertEqual(job_data["status"], "QUEUED")
        self.assertFalse(job_data["dev"])
        mock_start_job.assert_called_once_with(job_data["id"])

    @patch.object(JobRegistry, "start_job")
    def test_launch_job_with_dev_preview(self, mock_start_job):
        payload = {
            "repo": "test3",
            "feature": "slug-generator",
            "issue": "01",
            "model": "deepseek-v4.1-flash",
            "vm": False,
            "dev": True,
        }
        resp = self.client.post("/api/jobs", json=payload)
        self.assertEqual(resp.status_code, 200)
        job_data = resp.json()
        self.assertEqual(job_data["repo"], "test3")
        self.assertTrue(job_data["dev"])
        self.assertEqual(job_data["preview_url"], "https://3000.mahesh0.dev")
        mock_start_job.assert_called_once_with(job_data["id"])

    def test_cancel_job_endpoint(self):
        job = self.registry.create_job(repo="test3", feature="slug-gen")
        job.status = JobStatus.RUNNING

        resp = self.client.post(f"/api/jobs/{job.id}/cancel")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(job.status, JobStatus.CANCELLED)

    def test_stream_job_endpoint(self):
        job = self.registry.create_job(repo="test3", feature="slug-gen")
        job.status = JobStatus.SUCCESS
        self.registry.append_log(job.id, "Initial line 1\n")

        with self.client.stream("GET", f"/api/jobs/{job.id}/stream") as response:
            self.assertEqual(response.status_code, 200)
            lines = []
            for chunk in response.iter_lines():
                if chunk.startswith("data: "):
                    payload = json.loads(chunk[len("data: "):])
                    lines.append(payload)
                    break  # Got the init event
            self.assertTrue(len(lines) > 0)
            self.assertEqual(lines[0]["event"], "init")
            self.assertEqual(lines[0]["job"]["id"], job.id)


    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_route_aliases_return_identical_responses(self, mock_instantiate):
        mock_instantiate.return_value = {"name": "sample-repo", "html_url": "https://github.com/test/sample-repo"}

        # GET alias equivalence
        get_repos = self.client.get("/api/repos")
        get_studio_repos = self.client.get("/api/studio/repos")
        self.assertEqual(get_repos.status_code, 200)
        self.assertEqual(get_studio_repos.status_code, 200)
        self.assertEqual(get_repos.json(), get_studio_repos.json())

        # POST alias equivalence
        post_repos = self.client.post("/api/repos", json={"name": "sample-repo"})
        post_studio_repos = self.client.post("/api/studio/repos", json={"name": "sample-repo"})
        self.assertEqual(post_repos.status_code, 201)
        self.assertEqual(post_studio_repos.status_code, 201)
        self.assertEqual(post_repos.json(), post_studio_repos.json())
