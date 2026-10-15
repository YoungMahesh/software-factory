"""Unit and Integration Tests for Factory Testing Console."""

import json
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
    fetch_repo_scratch_metadata,
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
)
from factory.ui.guard import (
    evaluate_prompt_intent,
    IntentGuardResult,
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


class TestGitHubDiscovery(unittest.TestCase):
    def test_token_decryption_real_or_fallback(self):
        token = get_test_org_token()
        if token is not None:
            self.assertTrue(len(token) > 10)
            self.assertTrue(token.startswith("github_pat_") or token.startswith("ghp_"))

    def test_fetch_test_org_repos_fallback_on_empty_token(self):
        repos = fetch_test_org_repos(token="invalid_token_test", timeout_secs=0.5)
        self.assertIn("test1", repos)
        self.assertIn("test2", repos)
        self.assertIn("test3", repos)

    def test_fetch_repo_branches_filtering_and_sorting(self):
        mock_branches = [
            {"name": "develop"},
            {"name": "factory/issue-42"},
            {"name": "experimental"},
            {"name": "factory/auth"},
            {"name": "main"},
            {"name": "feature/ui"},
            {"name": "factory/v1-core"},
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_branches

        with patch("httpx.Client.get", return_value=mock_resp):
            branches = fetch_repo_branches("test-app", token="mock_token")
            # Must strictly include default branch (main) and factory/* branches
            # and sort with main first, followed by sorted factory branches
            self.assertEqual(branches, ["main", "factory/auth", "factory/issue-42", "factory/v1-core"])

    def test_fetch_repo_branches_fallback_on_unauthorized_or_network_error(self):
        # 401 Unauthorized
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        with patch("httpx.Client.get", return_value=mock_resp_401):
            branches = fetch_repo_branches("test-app", token="bad_token")
            self.assertEqual(branches, ["main"])

        # Network error
        with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
            branches = fetch_repo_branches("test-app", token="mock_token")
            self.assertEqual(branches, ["main"])

        # Missing token
        with patch("factory.ui.github.get_test_org_token", return_value=None):
            branches = fetch_repo_branches("test-app", token=None)
            self.assertEqual(branches, ["main"])

    def test_fetch_repo_scratch_metadata_parsing(self):
        mock_tree = {
            "tree": [
                {"path": ".scratch/queues-page/spec.md"},
                {"path": ".scratch/queues-page/issues/01-initial-view.md"},
                {"path": ".scratch/queues-page/issues/02-bulk-actions.md"},
                {"path": "src/index.ts"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tree

        with patch("httpx.Client.get", return_value=mock_resp):
            meta = fetch_repo_scratch_metadata("test-mock", token="test_token")
            self.assertTrue(meta["has_scratch"])
            self.assertEqual(len(meta["features"]), 1)
            feature = meta["features"][0]
            self.assertEqual(feature["slug"], "queues-page")
            self.assertEqual(len(feature["issues"]), 2)
            self.assertEqual(feature["issues"][0]["id"], "01")
            self.assertEqual(feature["issues"][1]["id"], "02")

    def test_parse_github_blocked_by(self):
        self.assertEqual(parse_github_blocked_by("Blocked by: #12"), ["12"])
        self.assertEqual(parse_github_blocked_by("Blocked by: #12, #14"), ["12", "14"])
        self.assertEqual(parse_github_blocked_by("**Blocked by**: `01`, `02`"), ["01", "02"])
        self.assertEqual(parse_github_blocked_by("Blocked by: None"), [])
        self.assertEqual(parse_github_blocked_by("Blocked by: none (first ticket)"), [])
        self.assertEqual(parse_github_blocked_by("No blockers declared here"), [])
        self.assertEqual(parse_github_blocked_by(None), [])

    def test_map_github_issue_status(self):
        self.assertEqual(map_github_issue_status({"state": "closed", "labels": []}), "resolved")
        self.assertEqual(
            map_github_issue_status({"state": "open", "labels": ["factory:resolved"]}),
            "resolved",
        )
        self.assertEqual(
            map_github_issue_status({"state": "open", "labels": [{"name": "factory:ready-for-human"}]}),
            "ready-for-human",
        )
        self.assertEqual(
            map_github_issue_status({"state": "open", "labels": ["factory:claimed"]}),
            "claimed",
        )
        self.assertEqual(
            map_github_issue_status({"state": "open", "labels": ["factory:ready"]}),
            "ready-for-agent",
        )
        self.assertEqual(
            map_github_issue_status({"state": "open", "labels": ["bug", "documentation"]}),
            "ready-for-agent",
        )

    def test_normalize_github_issue_extracts_milestone_and_blocked_by(self):
        raw_issue = {
            "id": 101,
            "number": 5,
            "title": "Add user authentication",
            "body": "Implement JWT auth.\n\nBlocked by: #3, #4",
            "state": "open",
            "labels": [{"name": "factory:ready"}],
            "milestone": {
                "number": 2,
                "title": "v1: Core Platform",
            },
            "html_url": "https://github.com/software-factory-09-test/app/issues/5",
        }
        normalized = _normalize_github_issue(raw_issue)
        self.assertEqual(normalized["number"], 5)
        self.assertEqual(normalized["title"], "Add user authentication")
        self.assertEqual(normalized["blocked_by"], ["3", "4"])
        self.assertEqual(normalized["status"], "ready-for-agent")
        self.assertIsNotNone(normalized["milestone"])
        self.assertEqual(normalized["milestone"]["number"], 2)
        self.assertEqual(normalized["milestone"]["title"], "v1: Core Platform")
        self.assertEqual(normalized["milestone"]["slug"], "v1-core-platform")

        # Standalone issue without milestone
        raw_issue_standalone = {
            "id": 102,
            "number": 6,
            "title": "Standalone bugfix",
            "body": "Fix footer padding. Blocked by: None",
            "state": "open",
            "labels": [],
            "milestone": None,
        }
        normalized_standalone = _normalize_github_issue(raw_issue_standalone)
        self.assertIsNone(normalized_standalone["milestone"])
        self.assertEqual(normalized_standalone["blocked_by"], [])

    def test_fetch_repo_milestones_and_issues_parsing(self):
        mock_milestones = [
            {
                "id": 101,
                "number": 1,
                "title": "queues-page",
                "description": "Queues management feature",
                "state": "open",
                "open_issues": 2,
                "closed_issues": 0,
            }
        ]
        mock_issues = [
            {
                "id": 201,
                "number": 10,
                "title": "Initial queue view",
                "body": "Blocked by: None",
                "state": "open",
                "labels": [{"name": "factory:ready"}],
            },
            {
                "id": 202,
                "number": 11,
                "title": "Bulk actions",
                "body": "Blocked by: #10",
                "state": "open",
                "labels": [{"name": "factory:ready"}, {"name": "enhancement"}],
            },
            {
                "id": 203,
                "number": 12,
                "title": "Pull Request to be filtered",
                "body": "",
                "state": "open",
                "labels": [],
                "pull_request": {"url": "https://api.github.com/pulls/12"},
            },
        ]

        def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "milestones" in url:
                resp.json.return_value = mock_milestones
            elif "issues" in url:
                resp.json.return_value = mock_issues
            return resp

        with patch("httpx.Client.get", side_effect=mock_get):
            data = fetch_repo_milestones_and_issues("test3", token="mock-token")
            self.assertEqual(data["repo"], "test3")
            self.assertEqual(len(data["milestones"]), 1)
            ms = data["milestones"][0]
            self.assertEqual(ms["number"], 1)
            self.assertEqual(ms["title"], "queues-page")
            # Should filter out PR 12 and keep issues 10 & 11
            self.assertEqual(len(ms["issues"]), 2)
            iss0 = ms["issues"][0]
            self.assertEqual(iss0["number"], 10)
            self.assertEqual(iss0["status"], "ready-for-agent")
            self.assertEqual(iss0["blocked_by"], [])
            iss1 = ms["issues"][1]
            self.assertEqual(iss1["number"], 11)
            self.assertEqual(iss1["status"], "ready-for-agent")
            self.assertEqual(iss1["blocked_by"], ["10"])

    def test_fetch_repo_milestones_fallback_on_missing_or_error(self):
        # 1. 404 response
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_404.json.return_value = {"message": "Not Found"}

        with patch("httpx.Client.get", return_value=mock_404):
            data = fetch_repo_milestones_and_issues("unknown-repo", token="mock-token")
            self.assertEqual(data["repo"], "unknown-repo")
            self.assertEqual(data["milestones"], [])

        # 2. Exception/Network error
        with patch("httpx.Client.get", side_effect=Exception("Connection timeout")):
            data = fetch_repo_milestones_and_issues("test3", token="mock-token")
            self.assertEqual(data["repo"], "test3")
            self.assertEqual(data["milestones"], [])

        # 3. No token available
        with patch("factory.ui.github.get_test_org_token", return_value=None):
            data = fetch_repo_milestones_and_issues("test3", token=None)
            self.assertEqual(data["repo"], "test3")
            self.assertEqual(data["milestones"], [])

    def test_fetch_repo_issue_single(self):
        mock_issue = {
            "id": 999,
            "number": 42,
            "title": "Fix memory leak",
            "body": "Fixes bug in worker. Blocked by: #40",
            "state": "open",
            "labels": [{"name": "factory:claimed"}],
            "html_url": "https://github.com/software-factory-09-test/test3/issues/42",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_issue

        with patch("httpx.Client.get", return_value=mock_resp):
            iss = fetch_repo_issue("test3", 42, token="mock-token")
            self.assertIsNotNone(iss)
            self.assertEqual(iss["number"], 42)
            self.assertEqual(iss["status"], "claimed")
            self.assertEqual(iss["blocked_by"], ["40"])
            self.assertIn("factory:claimed", iss["labels"])

        # 404 not found
        mock_404 = MagicMock()
        mock_404.status_code = 404
        with patch("httpx.Client.get", return_value=mock_404):
            iss_none = fetch_repo_issue("test3", 9999, token="mock-token")
            self.assertIsNone(iss_none)


class TestJobRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry(max_log_lines=50)

    def test_create_and_get_job(self):
        job = self.registry.create_job(
            repo="test3",
            feature="slug-generator",
            issue="01",
            model="deepseek-v4.1-flash",
            vm=True,
        )
        self.assertEqual(job.repo, "test3")
        self.assertEqual(job.feature, "slug-generator")
        self.assertEqual(job.issue, "01")
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.stage, JobStage.IDLE)
        self.assertTrue(job.vm)

        fetched = self.registry.get_job(job.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, job.id)

    def test_append_log_and_stage_detection(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator")
        q = self.registry.add_listener(job.id)

        # Stage 0: Preflight
        self.registry.append_log(job.id, "Running Pre-flight Guard Check on workspace...\n")
        self.assertEqual(job.stage, JobStage.PREFLIGHT)
        event1 = q.get_nowait()
        self.assertEqual(event1["event"], "stage")
        self.assertEqual(event1["stage"], JobStage.PREFLIGHT.value)

        # Stage 1: Planner
        self.registry.append_log(job.id, "Stage 1: Planner Agent analyzing codebase\n")
        self.assertEqual(job.stage, JobStage.PLANNER)

        # Stage 2: Coder
        self.registry.append_log(job.id, "Stage 2: Coder Agent coding implementation\n")
        self.assertEqual(job.stage, JobStage.CODER)

        # Stage 3: Verifier
        self.registry.append_log(job.id, "Stage 3: Deterministic Verifier running test suite\n")
        self.assertEqual(job.stage, JobStage.VERIFIER)

        # Stage 4: Reviewer
        self.registry.append_log(job.id, "Stage 4: Reviewer Agent auditing diff\n")
        self.assertEqual(job.stage, JobStage.REVIEWER)

        # Stage complete
        self.registry.append_log(job.id, "🎉 Assembly line pipeline completed successfully!\n")
        self.assertEqual(job.stage, JobStage.COMPLETED)

        self.registry.remove_listener(job.id, q)

    def test_cancel_running_job(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator")
        mock_sandbox = MagicMock()
        job.sandbox = mock_sandbox
        job.status = JobStatus.RUNNING

        res = self.registry.cancel_job(job.id)
        self.assertTrue(res)
        self.assertEqual(job.status, JobStatus.CANCELLED)
        mock_sandbox.terminate.assert_called_once()
        self.assertIn("cancelled", job.logs[-1].lower())

    def test_create_job_with_dev_preview(self):
        job = self.registry.create_job(
            repo="test3",
            feature="preview-feat",
            dev=True,
        )
        self.assertTrue(job.dev)
        self.assertEqual(job.preview_url, "https://3000.mahesh0.dev")
        d = job.to_dict()
        self.assertTrue(d["dev"])
        self.assertEqual(d["preview_url"], "https://3000.mahesh0.dev")

    def test_stage_detection_serving(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator", dev=True)
        self.registry.append_log(job.id, "🎉 Assembly line pipeline completed successfully!\n")
        self.assertEqual(job.stage, JobStage.COMPLETED)

        self.registry.append_log(job.id, "⏳ Container entering active serving keep-alive state (https://3000.mahesh0.dev)...\n")
        self.assertEqual(job.stage, JobStage.SERVING)

    def test_cancel_serving_job_terminates_sandbox(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator", dev=True)
        mock_sandbox = MagicMock()
        job.sandbox = mock_sandbox
        job.status = JobStatus.RUNNING
        job.stage = JobStage.SERVING

        res = self.registry.cancel_job(job.id)
        self.assertTrue(res)
        self.assertEqual(job.status, JobStatus.CANCELLED)
        mock_sandbox.terminate.assert_called_once()
        self.assertIn("cancelled", job.logs[-1].lower())


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

    def test_get_repo_scratch_endpoint(self):
        resp = self.client.get("/api/repos/test3/scratch")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertIn("features", data)

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

    def test_preview_endpoints_require_auth(self):
        unauth_client = TestClient(self.app)
        resp_branches = unauth_client.get("/api/studio/repos/test3/branches")
        self.assertEqual(resp_branches.status_code, 401)
        resp = unauth_client.get("/api/studio/repos/test3/preview")
        self.assertEqual(resp.status_code, 401)
        resp_post = unauth_client.post("/api/studio/repos/test3/preview")
        self.assertEqual(resp_post.status_code, 401)
        resp_post_branch = unauth_client.post("/api/studio/repos/test3/preview/branch", json={"branch": "factory/feat"})
        self.assertEqual(resp_post_branch.status_code, 401)
        resp_del = unauth_client.delete("/api/studio/repos/test3/preview")
        self.assertEqual(resp_del.status_code, 401)
        resp_stream = unauth_client.get("/api/studio/repos/test3/preview/stream")
        self.assertEqual(resp_stream.status_code, 401)

    @patch("factory.ui.registry.create_preview_sandbox")
    def test_preview_lifecycle_endpoints(self, mock_create):
        import threading
        import time

        stop_event = threading.Event()
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-preview-999"
        mock_sandbox.stdout = iter(["Dev server started on port 3000\n"])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.side_effect = lambda **kwargs: stop_event.wait(timeout=2.0)
        mock_sandbox.terminate = MagicMock()
        mock_sandbox.terminate.aio = AsyncMock(side_effect=lambda: stop_event.set())
        mock_sandbox.returncode = 0
        mock_create.return_value = (mock_sandbox, "https://sb-preview-999-3000.modal.host")

        # 1. Initial status is IDLE
        resp_get_init = self.client.get("/api/studio/repos/test3/preview")
        self.assertEqual(resp_get_init.status_code, 200)
        init_data = resp_get_init.json()
        self.assertEqual(init_data["repo"], "test3")
        self.assertEqual(init_data["status"], "IDLE")
        self.assertIn("logs", init_data)
        self.assertEqual(init_data["logs"], [])

        # 2. Launch preview via POST
        resp_post = self.client.post(
            "/api/studio/repos/test3/preview",
            json={"branch": "factory/test-ui-feat"},
        )
        self.assertIn(resp_post.status_code, (200, 201))
        post_data = resp_post.json()
        self.assertEqual(post_data["repo"], "test3")
        self.assertEqual(post_data["branch"], "factory/test-ui-feat")

        # 3. Check status until SERVING
        serving_data = None
        for _ in range(20):
            r = self.client.get("/api/studio/repos/test3/preview")
            if r.status_code == 200 and r.json().get("status") == "SERVING":
                serving_data = r.json()
                break
            time.sleep(0.05)

        self.assertIsNotNone(serving_data)
        self.assertEqual(serving_data["status"], "SERVING")
        self.assertEqual(serving_data["preview_url"], "https://sb-preview-999-3000.modal.host")
        self.assertEqual(serving_data["sandbox_id"], "sb-preview-999")
        self.assertIn("logs", serving_data)
        self.assertIsInstance(serving_data["logs"], list)

        # 4. Stop preview via DELETE
        resp_del = self.client.delete("/api/studio/repos/test3/preview")
        self.assertEqual(resp_del.status_code, 200)
        del_data = resp_del.json()
        self.assertTrue(del_data["success"])
        mock_sandbox.terminate.aio.assert_awaited_once()

        # 5. Subsequent DELETE returns 400 or 404
        resp_del_again = self.client.delete("/api/studio/repos/test3/preview")
        self.assertIn(resp_del_again.status_code, (400, 404))

    def test_preview_stream_sse_endpoint(self):
        # 1. 404 when preview does not exist
        resp_404 = self.client.get("/api/studio/repos/unknown-repo/preview/stream")
        self.assertEqual(resp_404.status_code, 404)

        # 2. When preview exists, streams init event and real-time logs
        from factory.ui.registry import preview_registry, PreviewState, PreviewStage, PreviewStatus
        preview = PreviewState(
            repo="stream-repo",
            status=PreviewStatus.STOPPED,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://preview.modal.host",
        )
        preview.add_log("Booting container...\n")
        preview_registry._previews["stream-repo"] = preview

        orig_add_listener = preview_registry.add_listener

        def mock_add_listener(repo_name):
            q = orig_add_listener(repo_name)
            if repo_name == "stream-repo" and q is not None:
                q.put_nowait({"event": "log", "data": "Compiling Vite...\n"})
                q.put_nowait({"event": "stage", "stage": "STARTING_DEV"})
            return q

        with patch.object(preview_registry, "add_listener", side_effect=mock_add_listener):
            with self.client.stream("GET", "/api/studio/repos/stream-repo/preview/stream") as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/event-stream", response.headers["content-type"])
                events = []
                for chunk in response.iter_lines():
                    if chunk.startswith("data: "):
                        payload = json.loads(chunk[len("data: "):])
                        events.append(payload)

                self.assertTrue(len(events) >= 3)
                init_event = events[0]
                self.assertEqual(init_event["event"], "init")
                self.assertEqual(init_event["status"], "STOPPED")
                self.assertEqual(init_event["stage"], "SERVING")
                self.assertEqual(init_event["preview_url"], "https://preview.modal.host")
                self.assertIn("Booting container...\n", init_event["backlog"])

                log_events = [e for e in events if e.get("event") == "log"]
                self.assertTrue(len(log_events) >= 1)
                self.assertEqual(log_events[0]["data"], "Compiling Vite...\n")

                stage_events = [e for e in events if e.get("event") == "stage"]
                self.assertTrue(len(stage_events) >= 1)
                self.assertEqual(stage_events[0]["stage"], "STARTING_DEV")

    @patch("factory.ui.app.fetch_repo_branches")
    def test_get_repo_branches_endpoint(self, mock_fetch_branches):
        mock_fetch_branches.return_value = ["main", "factory/feature-a", "factory/feature-b"]

        resp = self.client.get("/api/studio/repos/test3/branches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertEqual(data["org"], "software-factory-09-test")
        self.assertEqual(data["branches"], ["main", "factory/feature-a", "factory/feature-b"])
        self.assertEqual(data["default_branch"], "main")
        mock_fetch_branches.assert_called_once_with("test3")

        # Also verify /api/repos/{repo}/branches alias works
        resp_alias = self.client.get("/api/repos/test3/branches")
        self.assertEqual(resp_alias.status_code, 200)
        self.assertEqual(resp_alias.json()["branches"], ["main", "factory/feature-a", "factory/feature-b"])

    @patch("factory.ui.app.fetch_repo_branches_with_diagnostics")
    def test_get_repo_branches_endpoint(self, mock_fetch_branches):
        mock_fetch_branches.return_value = (["main", "factory/feature-a", "factory/feature-b"], None)

        resp = self.client.get("/api/studio/repos/test3/branches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertEqual(data["org"], "software-factory-09-test")
        self.assertEqual(data["branches"], ["main", "factory/feature-a", "factory/feature-b"])
        self.assertEqual(data["default_branch"], "main")
        self.assertNotIn("error", data)
        mock_fetch_branches.assert_called_once_with("test3")

        # Also verify /api/repos/{repo}/branches alias works
        resp_alias = self.client.get("/api/repos/test3/branches")
        self.assertEqual(resp_alias.status_code, 200)
        self.assertEqual(resp_alias.json()["branches"], ["main", "factory/feature-a", "factory/feature-b"])

    @patch("factory.ui.app.fetch_repo_branches_with_diagnostics")
    def test_get_repo_branches_endpoint_graceful_error_handling(self, mock_fetch_branches):
        mock_fetch_branches.return_value = (["main"], "GitHub API error (status 401)")

        resp = self.client.get("/api/studio/repos/test3/branches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertEqual(data["branches"], ["main"])
        self.assertEqual(data["error"], "GitHub API error (status 401)")

    @patch("factory.ui.registry.create_preview_sandbox")
    def test_post_preview_branch_endpoint_idle_and_stopped(self, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-branch-test"
        mock_sandbox.stdout = iter([])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.return_value = 0
        mock_sandbox.returncode = 0
        mock_create.return_value = (mock_sandbox, "https://sb-branch-test-3000.modal.host")

        # 1. Update target branch when preview is idle (no preview started yet)
        resp = self.client.post(
            "/api/studio/repos/branch-test-repo/preview/branch",
            json={"branch": "factory/feature-preselected"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "branch-test-repo")
        self.assertEqual(data["branch"], "factory/feature-preselected")
        self.assertEqual(data["status"], "IDLE")
        self.assertFalse(data["in_place"])
        self.assertTrue(data["success"])

        # 2. Launch preview without specifying branch -> boots on preselected branch!
        resp_launch = self.client.post("/api/studio/repos/branch-test-repo/preview", json={})
        self.assertIn(resp_launch.status_code, (200, 201))
        launch_data = resp_launch.json()
        self.assertEqual(launch_data["branch"], "factory/feature-preselected")

        mock_create.assert_called_once()
        spawn_cfg = mock_create.call_args[0][0]
        self.assertEqual(spawn_cfg.branch, "factory/feature-preselected")

    def test_post_preview_branch_validation(self):
        # Empty branch
        resp_empty = self.client.post(
            "/api/studio/repos/test3/preview/branch",
            json={"branch": ""},
        )
        self.assertEqual(resp_empty.status_code, 400)

        # Missing branch
        resp_missing = self.client.post(
            "/api/studio/repos/test3/preview/branch",
            json={},
        )
        self.assertEqual(resp_missing.status_code, 422)

        # Invalid branch format (not main and doesn't start with factory/)
        resp_invalid = self.client.post(
            "/api/studio/repos/test3/preview/branch",
            json={"branch": "random-branch-name"},
        )
        self.assertEqual(resp_invalid.status_code, 400)
        self.assertIn("must be 'main' or start with 'factory/'", resp_invalid.json()["detail"])

    def test_post_preview_branch_concurrency_guard(self):
        # When an Assembly Line job is running or queued, branch changes are blocked with 409
        job = self.registry.create_job(repo="busy-repo", feature="active-feat")
        job.status = JobStatus.RUNNING

        resp = self.client.post(
            "/api/studio/repos/busy-repo/preview/branch",
            json={"branch": "factory/new-branch"},
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Assembly Line Pipeline job is currently active", resp.json()["detail"])

    def test_post_preview_branch_active_in_place_switching_success(self):
        from factory.ui.registry import preview_registry
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-switcher"
        mock_process = MagicMock()
        mock_process.stdout = iter(["Switched to branch 'factory/active-feature'\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        active_preview = PreviewState(
            repo="active-switcher-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://active-switch.modal.host",
            sandbox=mock_sandbox,
        )
        preview_registry._previews["active-switcher-repo"] = active_preview

        try:
            resp = self.client.post(
                "/api/studio/repos/active-switcher-repo/preview/branch",
                json={"branch": "factory/active-feature"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["repo"], "active-switcher-repo")
            self.assertEqual(data["branch"], "factory/active-feature")
            self.assertEqual(data["status"], "SERVING")
            self.assertEqual(data["preview_url"], "https://active-switch.modal.host")
            self.assertTrue(data["in_place"])
            self.assertTrue(data["success"])

            # Verify in-container execution occurred
            mock_sandbox.exec.assert_called_once()
            exec_args = mock_sandbox.exec.call_args[0]
            self.assertIn("git reset --hard && git clean -fd", exec_args[2])
            self.assertIn("git checkout factory/active-feature && git pull origin factory/active-feature", exec_args[2])
        finally:
            preview_registry._previews.pop("active-switcher-repo", None)

    def test_post_preview_branch_active_in_place_switching_failure(self):
        from factory.ui.registry import preview_registry
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-fail"
        mock_sandbox.terminate = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = iter(["fatal: Remote branch factory/nonexistent not found\n"])
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        active_preview = PreviewState(
            repo="active-fail-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://active-fail.modal.host",
            sandbox=mock_sandbox,
        )
        preview_registry._previews["active-fail-repo"] = active_preview

        try:
            resp = self.client.post(
                "/api/studio/repos/active-fail-repo/preview/branch",
                json={"branch": "factory/nonexistent"},
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("failed", resp.json()["detail"].lower())

            # Unified Studio Sandbox must remain SERVING on original branch
            self.assertEqual(active_preview.status, PreviewStatus.SERVING)
            self.assertEqual(active_preview.branch, "main")
            mock_sandbox.terminate.assert_not_called()
        finally:
            preview_registry._previews.pop("active-fail-repo", None)

    def test_post_preview_branch_provisioning_guard(self):
        from factory.ui.registry import preview_registry
        prov_preview = PreviewState(
            repo="prov-repo",
            status=PreviewStatus.PROVISIONING,
            stage=PreviewStage.PROVISIONING,
            branch="main",
        )
        preview_registry._previews["prov-repo"] = prov_preview

        try:
            resp = self.client.post(
                "/api/studio/repos/prov-repo/preview/branch",
                json={"branch": "factory/some-target"},
            )
            self.assertEqual(resp.status_code, 409)
            self.assertIn("provisioning", resp.json()["detail"].lower())
        finally:
            preview_registry._previews.pop("prov-repo", None)

    def test_post_preview_branch_broadcasts_sse_events(self):
        from factory.ui.registry import preview_registry
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-sse-broadcast"
        mock_process = MagicMock()
        mock_process.stdout = iter(["Switched to branch 'factory/sse-feature'\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        active_preview = PreviewState(
            repo="sse-broadcast-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            preview_url="https://sse-broadcast.modal.host",
            sandbox=mock_sandbox,
        )
        preview_registry._previews["sse-broadcast-repo"] = active_preview
        q = preview_registry.add_listener("sse-broadcast-repo")

        try:
            resp = self.client.post(
                "/api/studio/repos/sse-broadcast-repo/preview/branch",
                json={"branch": "factory/sse-feature"},
            )
            self.assertEqual(resp.status_code, 200)

            # Collect queued SSE broadcast events
            events = []
            while not q.empty():
                events.append(q.get_nowait())

            branch_events = [e for e in events if e.get("event") == "branch"]
            self.assertEqual(len(branch_events), 1)
            self.assertEqual(branch_events[0]["branch"], "factory/sse-feature")
            self.assertEqual(branch_events[0]["repo"], "sse-broadcast-repo")

            refresh_events = [e for e in events if e.get("event") == "preview_refresh"]
            self.assertEqual(len(refresh_events), 1)
            self.assertEqual(refresh_events[0]["repo"], "sse-broadcast-repo")
        finally:
            preview_registry._previews.pop("sse-broadcast-repo", None)

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


class TestCompiledSpaRootRouteServing(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_root_requires_authentication(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)

    def test_root_serves_spa_shell_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp.text)
        self.assertIn("Software Factory", resp.text)

    def test_client_routing_fallback_on_root(self):
        resp = self.client.get("/console")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp.text)

        resp2 = self.client.get("/studio/repo/my-app")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("text/html", resp2.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp2.text)

        resp3 = self.client.get("/arbitrary/nested/deep-link")
        self.assertEqual(resp3.status_code, 200)
        self.assertIn("text/html", resp3.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp3.text)

        resp_api_404 = self.client.get("/api/unknown_endpoint")
        self.assertEqual(resp_api_404.status_code, 404)

    def test_v2_redirects_to_root(self):
        # Without follow_redirects, verify HTTP 307/308 redirect and query preservation
        resp = self.client.get("/v2", follow_redirects=False)
        self.assertIn(resp.status_code, (307, 308))
        self.assertEqual(resp.headers["location"], "/")

        resp_query = self.client.get("/v2?feature=test", follow_redirects=False)
        self.assertIn(resp_query.status_code, (307, 308))
        self.assertEqual(resp_query.headers["location"], "/?feature=test")

        resp_sub = self.client.get("/v2/console?tab=1", follow_redirects=False)
        self.assertIn(resp_sub.status_code, (307, 308))
        self.assertEqual(resp_sub.headers["location"], "/console?tab=1")

        # With follow_redirects, verify redirect resolves to compiled SPA
        resp_followed = self.client.get("/v2", follow_redirects=True)
        self.assertEqual(resp_followed.status_code, 200)
        self.assertIn('<div id="root"></div>', resp_followed.text)

    def test_compiled_bundle_delivery(self):
        from factory.ui.app import STATIC_DIST_DIR

        assets_dir = STATIC_DIST_DIR / "assets"
        js_files = list(assets_dir.glob("*.js"))
        css_files = list(assets_dir.glob("*.css"))

        if js_files:
            js_name = js_files[0].name
            resp_js = self.client.get(f"/assets/{js_name}")
            self.assertEqual(resp_js.status_code, 200)
            self.assertIn("javascript", resp_js.headers["content-type"])

        if css_files:
            css_name = css_files[0].name
            resp_css = self.client.get(f"/assets/{css_name}")
            self.assertEqual(resp_css.status_code, 200)
            self.assertIn("text/css", resp_css.headers["content-type"])

    def test_fallback_when_dist_index_missing(self):
        with patch("pathlib.Path.is_file", return_value=False):
            resp = self.client.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("Compiled SPA bundle not found", resp.text)

    def test_static_assets_serving(self):
        from factory.ui.app import STATIC_DIST_DIR

        # Create a mock asset in STATIC_DIST_DIR/assets
        assets_dir = STATIC_DIST_DIR / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        test_asset = assets_dir / "test-bundle.js"
        test_asset.write_text("console.log('spa bundle');", encoding="utf-8")
        try:
            resp = self.client.get("/assets/test-bundle.js")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("javascript", resp.headers["content-type"])
            self.assertEqual(resp.text, "console.log('spa bundle');")

            # Legacy /v2/assets path redirects to /assets
            resp_v2 = self.client.get("/v2/assets/test-bundle.js", follow_redirects=False)
            self.assertIn(resp_v2.status_code, (307, 308))
            self.assertEqual(resp_v2.headers["location"], "/assets/test-bundle.js")

            resp_v2_followed = self.client.get("/v2/assets/test-bundle.js", follow_redirects=True)
            self.assertEqual(resp_v2_followed.status_code, 200)
            self.assertEqual(resp_v2_followed.text, "console.log('spa bundle');")

            # Also verify via /static/dist/assets/test-bundle.js
            resp_dist = self.client.get("/static/dist/assets/test-bundle.js")
            self.assertEqual(resp_dist.status_code, 200)
            self.assertIn("javascript", resp_dist.headers["content-type"])
        finally:
            if test_asset.exists():
                test_asset.unlink()


class TestCliDispatcherUiFlag(unittest.TestCase):
    def test_parse_args_ui_flags(self):
        with patch.dict("os.environ", {}, clear=True):
            args1 = parse_args(["--ui"])
            self.assertTrue(args1.ui)
            self.assertEqual(args1.port, 3010)
            self.assertEqual(args1.host, "127.0.0.1")

        args2 = parse_args(["--console", "--port", "9090", "--host", "0.0.0.0"])
        self.assertTrue(args2.ui)
        self.assertEqual(args2.port, 9090)
        self.assertEqual(args2.host, "0.0.0.0")

    def test_parse_args_ui_port_env_var(self):
        with patch.dict("os.environ", {"PORT": "4567"}):
            args = parse_args(["--ui"])
            self.assertEqual(args.port, 4567)

    def test_parse_args_ui_port_cli_precedence(self):
        with patch.dict("os.environ", {"PORT": "4567"}):
            args = parse_args(["--ui", "--port", "8989"])
            self.assertEqual(args.port, 8989)

    @patch("factory.ui.server.start_server")
    def test_main_with_ui_flag(self, mock_start_server):
        code = main(["--ui", "--port", "8888"])
        self.assertEqual(code, 0)
        mock_start_server.assert_called_once_with(host="127.0.0.1", port=8888, open_browser=True)


class TestServerRunner(unittest.TestCase):
    def test_get_default_port_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 3010)

    def test_get_default_port_env(self):
        with patch.dict("os.environ", {"PORT": "4000"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 4000)

    def test_get_default_port_invalid_env(self):
        with patch.dict("os.environ", {"PORT": "invalid"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 3010)

    @patch("factory.ui.server.start_server")
    def test_server_main_defaults(self, mock_start_server):
        from factory.ui.server import main as server_main
        with patch.dict("os.environ", {}, clear=True):
            server_main([])
            mock_start_server.assert_called_once_with(host="127.0.0.1", port=3010, open_browser=False)

    @patch("factory.ui.server.start_server")
    def test_server_main_custom_args(self, mock_start_server):
        from factory.ui.server import main as server_main
        server_main(["--host", "0.0.0.0", "-p", "5000", "--open"])
        mock_start_server.assert_called_once_with(host="0.0.0.0", port=5000, open_browser=True)

    @patch("uvicorn.run")
    def test_start_server_warning_fallback(self, mock_uvicorn_run):
        from factory.ui.server import start_server
        import io
        from contextlib import redirect_stdout

        with patch.dict("os.environ", {}, clear=True):
            f = io.StringIO()
            with redirect_stdout(f):
                start_server(host="127.0.0.1", port=3010)
            output = f.getvalue()
            self.assertIn("Factory Studio", output)
            self.assertIn("3010", output)
            self.assertIn("Compiled Vite React SPA", output)
            self.assertIn("SECURITY WARNING: Using local dev fallback", output)
            mock_uvicorn_run.assert_called_once()

    @patch("uvicorn.run")
    def test_start_server_configured_auth(self, mock_uvicorn_run):
        from factory.ui.server import start_server
        import io
        from contextlib import redirect_stdout

        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "produser", "FACTORY_AUTH_PASS": "secret"}, clear=True):
            f = io.StringIO()
            with redirect_stdout(f):
                start_server(host="127.0.0.1", port=3010)
            output = f.getvalue()
            self.assertIn("Compiled Vite React SPA", output)
            self.assertIn("HTTP Basic Auth enabled (user: 'produser')", output)
            mock_uvicorn_run.assert_called_once()


class TestAuthCredentials(unittest.TestCase):
    def test_get_auth_credentials_from_env(self):
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "myuser", "FACTORY_AUTH_PASS": "mypass123"}, clear=True):
            from factory.ui.auth import get_auth_credentials
            user, password, is_fallback = get_auth_credentials()
            self.assertEqual(user, "myuser")
            self.assertEqual(password, "mypass123")
            self.assertFalse(is_fallback)

    def test_get_auth_credentials_fallback_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            from factory.ui.auth import get_auth_credentials
            with self.assertLogs("factory.ui.auth", level="WARNING") as log_cm:
                user, password, is_fallback = get_auth_credentials()
                self.assertEqual(user, "admin")
                self.assertEqual(password, "admin")
                self.assertTrue(is_fallback)
                self.assertTrue(any("FACTORY_AUTH_USER" in msg for msg in log_cm.output))

    def test_get_auth_credentials_fallback_when_partial(self):
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "myuser"}, clear=True):
            from factory.ui.auth import get_auth_credentials
            with self.assertLogs("factory.ui.auth", level="WARNING") as log_cm:
                user, password, is_fallback = get_auth_credentials()
                self.assertEqual(user, "admin")
                self.assertEqual(password, "admin")
                self.assertTrue(is_fallback)
                self.assertTrue(any("FACTORY_AUTH_PASS" in msg for msg in log_cm.output))


class TestBasicAuthSecurity(unittest.TestCase):
    def test_unauthenticated_request_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)
        self.assertIn('Basic realm="Factory Studio"', resp.headers["www-authenticate"])

        resp_api = client.get("/api/repos")
        self.assertEqual(resp_api.status_code, 401)
        self.assertIn("www-authenticate", resp_api.headers)

    def test_invalid_credentials_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/", auth=("wronguser", "wrongpass"))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)

    def test_malformed_auth_header_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/", headers={"Authorization": "Bearer not-a-basic-token"})
        self.assertEqual(resp.status_code, 401)

        resp_bad_b64 = client.get("/", headers={"Authorization": "Basic !!!not-valid-b64!!!"})
        self.assertEqual(resp_bad_b64.status_code, 401)

        resp_no_colon = client.get("/", headers={"Authorization": "Basic YWRtaW4="})  # 'admin' without ':'
        self.assertEqual(resp_no_colon.status_code, 401)

    def test_authenticated_request_with_env_credentials(self):
        with patch.dict(
            "os.environ",
            {"FACTORY_AUTH_USER": "custom_user", "FACTORY_AUTH_PASS": "custom_pass"},
            clear=True,
        ):
            registry = JobRegistry()
            app = create_app(registry=registry)
            client = TestClient(app)

            # Incorrect credentials fail
            resp_fail = client.get("/api/repos", auth=("admin", "admin"))
            self.assertEqual(resp_fail.status_code, 401)

            # Correct credentials succeed
            resp_ok = client.get("/api/repos", auth=("custom_user", "custom_pass"))
            self.assertEqual(resp_ok.status_code, 200)

    def test_authenticated_request_with_dev_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            registry = JobRegistry()
            app = create_app(registry=registry)
            client = TestClient(app)

            resp = client.get("/api/repos", auth=("admin", "admin"))
            self.assertEqual(resp.status_code, 200)

    def test_sse_stream_unauthenticated_returns_401(self):
        registry = JobRegistry()
        job = registry.create_job(repo="test3", feature="test-feature")
        job.status = JobStatus.SUCCESS
        app = create_app(registry=registry)
        client = TestClient(app)

        with client.stream("GET", f"/api/jobs/{job.id}/stream") as resp:
            self.assertEqual(resp.status_code, 401)
            self.assertIn("www-authenticate", resp.headers)

    def test_sse_stream_authenticated_succeeds(self):
        with patch.dict(
            "os.environ",
            {"FACTORY_AUTH_USER": "stream_user", "FACTORY_AUTH_PASS": "stream_pass"},
            clear=True,
        ):
            registry = JobRegistry()
            job = registry.create_job(repo="test3", feature="test-feature")
            job.status = JobStatus.SUCCESS
            registry.append_log(job.id, "Stream line 1\n")
            app = create_app(registry=registry)
            client = TestClient(app)

            with client.stream(
                "GET",
                f"/api/jobs/{job.id}/stream",
                auth=("stream_user", "stream_pass"),
            ) as response:
                self.assertEqual(response.status_code, 200)
                for chunk in response.iter_lines():
                    if chunk.startswith("data: "):
                        data = json.loads(chunk[len("data: "):])
                        self.assertEqual(data["event"], "init")
                        break

    def test_case_insensitive_basic_scheme(self):
        import base64
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "u", "FACTORY_AUTH_PASS": "p"}, clear=True):
            app = create_app()
            client = TestClient(app)
            raw = base64.b64encode(b"u:p").decode("ascii")

            # Lowercase "basic <b64>"
            resp_lower = client.get("/api/repos", headers={"Authorization": f"basic {raw}"})
            self.assertEqual(resp_lower.status_code, 200)

            # Mixed case "bAsIc <b64>"
            resp_mixed = client.get("/api/repos", headers={"Authorization": f"bAsIc {raw}"})
            self.assertEqual(resp_mixed.status_code, 200)

    def test_static_asset_protection(self):
        import tempfile
        from starlette.staticfiles import StaticFiles

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "style.css"
            test_file.write_text("body { color: red; }")

            app = create_app()
            app.mount("/static", StaticFiles(directory=tmpdir), name="static")
            client = TestClient(app)

            # Unauthenticated access to static asset is blocked with 401
            resp_unauth = client.get("/static/style.css")
            self.assertEqual(resp_unauth.status_code, 401)
            self.assertIn("www-authenticate", resp_unauth.headers)

            # Authenticated access to static asset succeeds with 200
            resp_auth = client.get("/static/style.css", auth=("admin", "admin"))
            self.assertEqual(resp_auth.status_code, 200)
            self.assertIn("color: red", resp_auth.text)


class TestGitHubRepoValidation(unittest.TestCase):
    def test_valid_repo_names(self):
        valid_cases = ["my-app", "tanstack-start-app", "app123", "cool_project", "web.app", "A1-b2_c3"]
        for name in valid_cases:
            valid, err = validate_github_repo_name(name)
            self.assertTrue(valid, f"Expected '{name}' to be valid, got error: {err}")
            self.assertIsNone(err)

    def test_invalid_repo_names(self):
        invalid_cases = [
            ("", "empty"),
            ("   ", "whitespace"),
            ("-leading-dash", "leading dash"),
            (".leading-dot", "leading dot"),
            ("_leading-underscore", "leading underscore"),
            ("my app", "contains space"),
            ("app@name", "special character @"),
            ("app/repo", "slash"),
            ("repo.git", "ends with .git"),
            (".", "single dot"),
            ("..", "double dot"),
            ("a" * 101, "exceeds 100 characters"),
        ]
        for name, reason in invalid_cases:
            valid, err = validate_github_repo_name(name)
            self.assertFalse(valid, f"Expected '{name}' ({reason}) to be invalid")
            self.assertIsNotNone(err)


class TestGitHubTanStackCompatibility(unittest.TestCase):
    def test_check_tanstack_compatibility_detection(self):
        # 1. Created from template repository
        self.assertTrue(
            check_tanstack_start_compatibility({
                "name": "my-app",
                "template_repository": {"name": "tanstack-start-template"},
            })
        )
        # 2. Template repo itself
        self.assertTrue(
            check_tanstack_start_compatibility({
                "name": "tanstack-start-template",
            })
        )
        # 3. Topic contains tanstack-start
        self.assertTrue(
            check_tanstack_start_compatibility({
                "name": "frontend-web",
                "topics": ["tanstack-start", "vite"],
            })
        )
        # 4. Description mentions TanStack Start
        self.assertTrue(
            check_tanstack_start_compatibility({
                "name": "dashboard",
                "description": "An interactive TanStack Start dashboard application",
            })
        )
        # 5. Non-compatible repo
        self.assertFalse(
            check_tanstack_start_compatibility({
                "name": "test1",
                "description": "Generic backend test fixture",
                "topics": ["python", "modal"],
            })
        )
        # 6. Unrelated TanStack libraries (Query/Table) are not TanStack Start
        self.assertFalse(
            check_tanstack_start_compatibility({
                "name": "data-grid",
                "description": "TanStack Table component demo",
                "topics": ["tanstack-query", "tanstack-table"],
            })
        )
        # 7. Empty dict
        self.assertFalse(check_tanstack_start_compatibility({}))

    def test_fetch_test_org_repos_detailed_mock(self):
        mock_github_repos = [
            {
                "name": "test1",
                "html_url": "https://github.com/software-factory-09-test/test1",
                "description": "Standard repo",
                "topics": [],
                "private": False,
            },
            {
                "name": "todo-app",
                "html_url": "https://github.com/software-factory-09-test/todo-app",
                "description": "Generated from TanStack Start",
                "template_repository": {"name": "tanstack-start-template"},
                "topics": ["tanstack-start"],
                "private": True,
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_github_repos

        with patch("httpx.Client.get", return_value=mock_resp):
            repos = fetch_test_org_repos_detailed(token="mock-token")
            self.assertEqual(len(repos), 2)
            # Should be sorted by name
            self.assertEqual(repos[0]["name"], "test1")
            self.assertFalse(repos[0]["is_tanstack_compatible"])
            self.assertFalse(repos[0]["private"])
            self.assertEqual(repos[1]["name"], "todo-app")
            self.assertTrue(repos[1]["is_tanstack_compatible"])
            self.assertTrue(repos[1]["private"])

    def test_fetch_test_org_repos_detailed_fallback_on_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.Client.get", return_value=mock_resp):
            repos = fetch_test_org_repos_detailed(token="mock-token")
            self.assertEqual(len(repos), 3)
            names = [r["name"] for r in repos]
            self.assertIn("test1", names)
            self.assertIn("test2", names)
            self.assertIn("test3", names)
            for r in repos:
                self.assertFalse(r["is_tanstack_compatible"])
                self.assertFalse(r.get("private", False))


class TestGitHubTemplateInstantiation(unittest.TestCase):
    def test_invalid_slug_raises_error(self):
        with self.assertRaises(RepoCreationError) as ctx:
            instantiate_repo_from_template("bad name!", token="mock-token")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("alphanumeric", ctx.exception.message)

    @patch("factory.ui.github.fetch_test_org_repos", return_value=["test1", "existing-app"])
    def test_duplicate_repo_raises_conflict(self, mock_fetch):
        with self.assertRaises(RepoCreationError) as ctx:
            instantiate_repo_from_template("existing-app", token="mock-token")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("already exists", ctx.exception.message)

    @patch("factory.ui.github.get_test_org_token", return_value=None)
    def test_missing_token_raises_error(self, mock_get_token):
        with self.assertRaises(RepoCreationError) as ctx:
            instantiate_repo_from_template("valid-app", token=None)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("Organization credentials not found", ctx.exception.message)

    @patch("factory.ui.github.fetch_test_org_repos", return_value=["test1", "test2"])
    def test_successful_instantiation_from_template(self, mock_fetch):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": 888123,
            "name": "new-portfolio",
            "full_name": "software-factory-09-test/new-portfolio",
            "html_url": "https://github.com/software-factory-09-test/new-portfolio",
            "description": "TanStack Start portfolio app",
            "private": True,
            "template_repository": {
                "name": "tanstack-start-template",
            },
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post, \
             patch("factory.ui.scaffold.scaffold_target_repo") as mock_scaffold:
            result = instantiate_repo_from_template(
                repo_name="new-portfolio",
                description="TanStack Start portfolio app",
                token="test-secret-token",
            )
            self.assertEqual(result["name"], "new-portfolio")
            self.assertEqual(result["full_name"], "software-factory-09-test/new-portfolio")
            self.assertEqual(result["html_url"], "https://github.com/software-factory-09-test/new-portfolio")
            self.assertTrue(result["is_tanstack_compatible"])
            self.assertTrue(result["private"])
            self.assertEqual(result["template_repository"], "software-factory-09-test/tanstack-start-template")
            mock_scaffold.assert_called_once()

            # Verify POST request parameters
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            url = args[0]
            self.assertEqual(
                url,
                "https://api.github.com/repos/software-factory-09-test/tanstack-start-template/generate",
            )
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-secret-token")
            self.assertEqual(kwargs["json"]["name"], "new-portfolio")
            self.assertEqual(kwargs["json"]["owner"], "software-factory-09-test")
            self.assertTrue(kwargs["json"]["private"])

    @patch("factory.ui.github.fetch_test_org_repos", return_value=["test1", "test2"])
    def test_successful_instantiation_explicit_public(self, mock_fetch):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": 888124,
            "name": "public-portfolio",
            "full_name": "software-factory-09-test/public-portfolio",
            "html_url": "https://github.com/software-factory-09-test/public-portfolio",
            "description": "Public portfolio app",
            "private": False,
            "template_repository": {
                "name": "tanstack-start-template",
            },
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post, \
             patch("factory.ui.scaffold.scaffold_target_repo") as mock_scaffold:
            result = instantiate_repo_from_template(
                repo_name="public-portfolio",
                description="Public portfolio app",
                private=False,
                token="test-secret-token",
            )
            self.assertEqual(result["name"], "public-portfolio")
            self.assertFalse(result["private"])
            args, kwargs = mock_post.call_args
            self.assertFalse(kwargs["json"]["private"])

    @patch("factory.ui.github.fetch_test_org_repos", return_value=[])
    def test_github_422_duplicate_raises_conflict(self, mock_fetch):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {
            "message": "Repository creation failed.",
            "errors": ["name already exists on this account"],
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template("clashing-app", token="test-token")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("already exists", ctx.exception.message)

    @patch("factory.ui.github.fetch_test_org_repos", return_value=[])
    def test_github_404_template_missing(self, mock_fetch):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Not Found"}

        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template("new-app", token="test-token")
            self.assertEqual(ctx.exception.status_code, 502)
            self.assertIn("not found", ctx.exception.message)


class TestFastIntentGuard(unittest.TestCase):
    def test_guard_allows_pure_frontend_requests(self):
        frontend_prompts = [
            "Build a responsive calculator app with arithmetic history and dark mode toggle.",
            "Create a kanban board with drag and drop columns using client-side state and localStorage.",
            "Design a dashboard with Chart.js showing interactive metrics with mock data.",
            "Build a weather app calling the Open-Meteo public REST API and rendering forecast cards.",
            "Implement a markdown editor with live side-by-side preview and syntax highlighting in TanStack Start.",
            "Create an interactive todo list with filtering, search, and sessionStorage persistence.",
        ]
        for prompt in frontend_prompts:
            with self.subTest(prompt=prompt):
                result = evaluate_prompt_intent(prompt)
                self.assertTrue(result.allowed, f"Expected prompt to be allowed: {prompt}")
                self.assertIsNone(result.refusal_message)
                self.assertIsNone(result.category)

    def test_guard_rejects_database_prompts(self):
        database_prompts = [
            "Create a blog with a PostgreSQL database and Prisma schema migrations.",
            "Build a user service storing profiles in MongoDB with mongoose models.",
            "Set up a Redis caching database with session persistence.",
            "Create an application with MySQL tables, foreign keys, and SQL queries.",
            "Build a todo app backed by SQLite database with server migrations.",
            "Connect this to a Supabase database to persist user records in Postgres.",
        ]
        for prompt in database_prompts:
            with self.subTest(prompt=prompt):
                result = evaluate_prompt_intent(prompt)
                self.assertFalse(result.allowed, f"Expected prompt to be rejected: {prompt}")
                self.assertIsNotNone(result.refusal_message)
                self.assertEqual(result.category, "database")
                self.assertIn("TanStack Start", result.refusal_message)
                self.assertIn("frontend", result.refusal_message.lower())

    def test_guard_rejects_backend_server_prompts(self):
        backend_prompts = [
            "Build a Node.js Express server with backend endpoints for authentication.",
            "Create a Python FastAPI backend service with background tasks.",
            "Build a REST backend API with Flask and server-side routes.",
            "Implement a Spring Boot backend microservice architecture.",
            "Add a Django backend server handling user registration and server sessions.",
            "Create a WebSocket server daemon running on the backend.",
        ]
        for prompt in backend_prompts:
            with self.subTest(prompt=prompt):
                result = evaluate_prompt_intent(prompt)
                self.assertFalse(result.allowed, f"Expected prompt to be rejected: {prompt}")
                self.assertIsNotNone(result.refusal_message)
                self.assertEqual(result.category, "backend_api")
                self.assertIn("TanStack Start", result.refusal_message)

    def test_guard_rejects_external_storage_prompts(self):
        storage_prompts = [
            "Store uploaded user images in an AWS S3 bucket.",
            "Upload files to Google Cloud Storage (GCS) blob storage.",
            "Persist customer attachments on Azure Blob Storage containers.",
            "Implement server filesystem persistence storing files in /var/data on the server.",
        ]
        for prompt in storage_prompts:
            with self.subTest(prompt=prompt):
                result = evaluate_prompt_intent(prompt)
                self.assertFalse(result.allowed, f"Expected prompt to be rejected: {prompt}")
                self.assertIsNotNone(result.refusal_message)
                self.assertEqual(result.category, "server_storage")
                self.assertIn("storage", result.refusal_message.lower())

    def test_guard_handles_empty_or_whitespace_prompts(self):
        result = evaluate_prompt_intent("")
        self.assertFalse(result.allowed)
        self.assertIn("empty", result.reason.lower() if result.reason else "")

        result2 = evaluate_prompt_intent("   \n\t  ")
        self.assertFalse(result2.allowed)


class TestTicketAndMilestoneSynthesis(unittest.TestCase):
    def test_synthesize_ticket_content_initial_ticket(self):
        prompt = "Build a responsive calculator app with arithmetic history and dark mode toggle."
        title, body = synthesize_ticket_content(prompt, seq_num=1, previous_issue_number=None)

        self.assertTrue(title.startswith("01: "))
        self.assertIn("Calculator", title)
        self.assertIn("# 01: ", body)
        self.assertIn("**What to build:**", body)
        self.assertIn("**Blocked by:** None", body)
        self.assertIn("**Status:** ready-for-agent", body)
        self.assertIn("- [ ]", body)
        self.assertIn("calculator", body.lower())

    def test_synthesize_ticket_content_sequential_ticket(self):
        prompt = "Add CSV export for calculation history with a download button."
        title, body = synthesize_ticket_content(prompt, seq_num=2, previous_issue_number=1)

        self.assertTrue(title.startswith("02: "))
        self.assertIn("CSV", title)
        self.assertIn("**Blocked by:** #1", body)
        self.assertIn("**Status:** ready-for-agent", body)
        self.assertIn("- [ ]", body)

    def test_create_repo_milestone_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": 991,
            "number": 1,
            "title": "v1: Initial App",
            "description": "Initial frontend application",
            "state": "open",
            "html_url": "https://github.com/software-factory-09-test/test-calc/milestone/1",
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            ms = create_repo_milestone(
                repo_name="test-calc",
                title="v1: Initial App",
                description="Initial frontend application",
                token="test-token",
            )
            self.assertEqual(ms["number"], 1)
            self.assertEqual(ms["title"], "v1: Initial App")
            self.assertEqual(ms["slug"], "v1-initial-app")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("/repos/software-factory-09-test/test-calc/milestones", args[0])
            self.assertEqual(kwargs["json"]["title"], "v1: Initial App")

    @patch("factory.ui.github.fetch_repo_milestones")
    def test_resolve_or_create_milestone_finds_existing(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": 991,
                "number": 1,
                "title": "v1: Initial App",
                "slug": "v1-initial-app",
                "state": "open",
                "html_url": "https://github.com/software-factory-09-test/test-calc/milestone/1",
            }
        ]
        with patch("factory.ui.github.create_repo_milestone") as mock_create:
            ms = resolve_or_create_milestone(
                repo_name="test-calc",
                title="v1: Initial App",
                token="test-token",
            )
            self.assertEqual(ms["number"], 1)
            self.assertEqual(ms["title"], "v1: Initial App")
            mock_create.assert_not_called()

    @patch("factory.ui.github.fetch_repo_milestones")
    def test_resolve_or_create_milestone_reuses_active_when_title_omitted(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": 993,
                "number": 2,
                "title": "v2: Advanced Widgets",
                "slug": "v2-advanced-widgets",
                "state": "open",
            }
        ]
        with patch("factory.ui.github.create_repo_milestone") as mock_create:
            ms = resolve_or_create_milestone(
                repo_name="test-calc",
                title=None,
                token="test-token",
            )
            self.assertEqual(ms["number"], 2)
            self.assertEqual(ms["title"], "v2: Advanced Widgets")
            mock_create.assert_not_called()

    @patch("factory.ui.github.fetch_repo_milestones", return_value=[])
    @patch("factory.ui.github.create_repo_milestone")
    def test_resolve_or_create_milestone_creates_if_missing(self, mock_create, mock_fetch):
        mock_create.return_value = {
            "id": 992,
            "number": 1,
            "title": "v1: Initial App",
            "slug": "v1-initial-app",
            "state": "open",
        }
        ms = resolve_or_create_milestone(
            repo_name="test-calc",
            title="v1: Initial App",
            token="test-token",
        )
        self.assertEqual(ms["number"], 1)
        mock_create.assert_called_once()

    def test_create_repo_issue_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": 771,
            "number": 1,
            "title": "01: Initial App UI",
            "body": "Issue spec",
            "state": "open",
            "labels": [{"name": "factory:ready"}],
            "html_url": "https://github.com/software-factory-09-test/test-calc/issues/1",
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            issue = create_repo_issue(
                repo_name="test-calc",
                title="01: Initial App UI",
                body="Issue spec",
                milestone_number=1,
                labels=["factory:ready"],
                token="test-token",
            )
            self.assertEqual(issue["number"], 1)
            self.assertEqual(issue["title"], "01: Initial App UI")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("/repos/software-factory-09-test/test-calc/issues", args[0])
            self.assertEqual(kwargs["json"]["milestone"], 1)
            self.assertEqual(kwargs["json"]["labels"], ["factory:ready"])

    @patch("factory.ui.github.fetch_repo_issues")
    @patch("factory.ui.github.create_repo_issue")
    def test_synthesize_and_create_issue_sequential_flow(self, mock_create_issue, mock_fetch_issues):
        # 1. First prompt in milestone (no existing issues)
        mock_fetch_issues.return_value = []
        mock_create_issue.return_value = {
            "id": 771,
            "number": 1,
            "title": "01: Calculator App Scaffolding",
            "body": "# 01...",
            "html_url": "https://github.com/software-factory-09-test/test-calc/issues/1",
        }

        first_issue = synthesize_and_create_issue(
            repo_name="test-calc",
            prompt="Build a calculator application with state and dark mode",
            milestone_number=1,
            milestone_slug="v1-initial-app",
            token="test-token",
        )
        self.assertEqual(first_issue["number"], 1)
        mock_create_issue.assert_called_once()
        args, kwargs = mock_create_issue.call_args
        self.assertTrue(kwargs["title"].startswith("01: "))
        self.assertIn("**Blocked by:** None", kwargs["body"])

        # 2. Second prompt in milestone (1 existing issue)
        mock_create_issue.reset_mock()
        mock_fetch_issues.return_value = [first_issue]
        mock_create_issue.return_value = {
            "id": 772,
            "number": 2,
            "title": "02: Calculation History CSV Export",
            "body": "# 02...",
            "html_url": "https://github.com/software-factory-09-test/test-calc/issues/2",
        }

        second_issue = synthesize_and_create_issue(
            repo_name="test-calc",
            prompt="Add export calculation history to CSV",
            milestone_number=1,
            milestone_slug="v1-initial-app",
            token="test-token",
        )
        self.assertEqual(second_issue["number"], 2)
        mock_create_issue.assert_called_once()
        args2, kwargs2 = mock_create_issue.call_args
        self.assertTrue(kwargs2["title"].startswith("02: "))
        self.assertIn("**Blocked by:** #1", kwargs2["body"])


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

    def test_prompt_endpoint_rejects_database_prompt_without_dispatching_job(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Build a user login app with a PostgreSQL database and Prisma migrations",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertIsNotNone(data["refusal"])
        self.assertIn("TanStack Start", data["refusal"])
        self.assertIsNone(data["job"])
        self.assertIsNone(data["issue"])
        self.assertIsNone(data["milestone"])
        # Ensure no job dispatched in registry
        self.assertEqual(len(self.registry.list_jobs()), 0)

    def test_prompt_endpoint_rejects_backend_server_prompt_without_dispatching_job(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Build a FastAPI backend server with background worker endpoints",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertIn("backend", data["refusal"].lower())
        self.assertIsNone(data["job"])
        self.assertEqual(len(self.registry.list_jobs()), 0)

    def test_prompt_endpoint_rejects_storage_prompt_without_dispatching_job(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Upload and store customer documents in an AWS S3 bucket",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertIn("storage", data["refusal"].lower())
        self.assertIsNone(data["job"])
        self.assertEqual(len(self.registry.list_jobs()), 0)

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

    def test_prompt_endpoint_grill_mode_default_returns_grill_round_without_sandbox(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Build an interactive analytics chart dashboard",
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["refusal"])
        self.assertIsNone(data["job"])
        self.assertIsNone(data["issue"])
        self.assertIsNone(data["milestone"])

        # Turn payload structure
        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertEqual(turn["type"], "grill_round")
        self.assertEqual(turn["round"], 1)
        self.assertGreaterEqual(len(turn["questions"]), 2)
        self.assertIn("❓ **Q1**", turn["formatted_text"])
        self.assertIn("➡️", turn["formatted_text"])
        self.assertIsNone(turn["draft_adr"])

        # Verify no job dispatched in registry and no sandbox auto-provisioned
        self.assertEqual(len(self.registry.list_jobs()), 0)
        self.assertIsNone(self.preview_registry.get_preview("test3"))

    def test_prompt_endpoint_grill_mode_with_history_reaches_ready_for_approval(self):
        history = [
            {"role": "user", "text": "Build an interactive analytics chart dashboard"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Route Placement**: Where should this route go?\n➡️ app/routes/analytics.tsx",
            },
        ]
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Accept recommended defaults and build the feature",
                "grill": True,
                "history": history,
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["job"])

        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertEqual(turn["type"], "ready_for_approval")
        self.assertEqual(turn["round"], 2)
        self.assertIsNotNone(turn["plan"])
        self.assertIn("Implementation Plan", turn["plan"])

        draft_adr = turn["draft_adr"]
        self.assertIsNotNone(draft_adr)
        self.assertIn("docs/adr/", draft_adr["filename"])
        self.assertTrue(draft_adr["filename"].endswith(".md"))
        self.assertIn("Status**: Proposed", draft_adr["content"])

        # No container or job dispatched yet
        self.assertEqual(len(self.registry.list_jobs()), 0)

    def test_prompt_endpoint_grill_mode_sharpens_domain_terms(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Add a customer orders list with a redux store",
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertTrue(any(s["canonical_term"] == "Client State" for s in turn["sharpened_terms"]))

    def test_prompt_endpoint_inference_failure_returns_structured_error_turn_and_saves_to_db(self):
        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection failed to opencode.ai")):
            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build an interactive analytics chart dashboard",
                    "grill": True,
                    "mock": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            turn = data["turn"]
            self.assertIsNotNone(turn)
            self.assertEqual(turn["type"], "error")
            self.assertIn("Connection failed", turn["error_message"])
            self.assertIn("OpenCode Go", turn["error_details"])

            # Verify persisted in Studio Chat History (Studio Database)
            get_resp = self.client.get("/api/studio/repos/test3/messages")
            self.assertEqual(get_resp.status_code, 200)
            messages = get_resp.json()["messages"]
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[1]["role"], "assistant")
            self.assertEqual(messages[1]["turn_data"]["type"], "error")
            self.assertEqual(messages[1]["turn_data"]["error_message"], turn["error_message"])

    def test_prompt_endpoint_grill_mode_conducts_codebase_grounding_and_passes_milestone_slug(self):
        remote_resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Clarifying social link removal in Footer",
                            "questions": [
                                {
                                    "id": "Q1",
                                    "title": "Social Links Scope",
                                    "question": "Should all social links in Footer.tsx be removed?",
                                    "recommended": "Remove GitHub, X, and Discord from Footer.tsx.",
                                    "options": ["Remove all links (Recommended)"],
                                }
                            ],
                        })
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_resp
        mock_resp.raise_for_status = MagicMock()

        fake_branches = MagicMock()
        fake_branches.status_code = 200
        fake_branches.json.return_value = [{"name": "factory/v1-initial-app"}]

        fake_tree = MagicMock()
        fake_tree.status_code = 200
        fake_tree.json.return_value = {
            "tree": [
                {"path": "app/routes/index.tsx", "type": "blob"},
                {"path": "app/components/Footer.tsx", "type": "blob"},
            ]
        }

        fake_footer = MagicMock()
        fake_footer.status_code = 200
        fake_footer.text = "export function Footer() { return <div><a href='https://x.com'>X</a></div>; }"

        def fake_async_get(url, headers=None):
            if "branches" in url:
                return fake_branches
            if "git/trees" in url:
                return fake_tree
            return fake_footer

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"), \
             patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_async_get), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:

            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test3",
                    "prompt": "remove social media links like github, x.com, etc",
                    "milestone_title": "v1: Initial App",
                    "grill": True,
                    "mock": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            turn = data["turn"]
            self.assertIsNotNone(turn)
            self.assertEqual(turn["type"], "grill_round")

            # Check that OpenCode Go received grounded prompt
            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            system_instruction = called_payload["messages"][0]["content"]

            self.assertIn("Repository Codebase Structure", system_instruction)
            self.assertIn("factory/v1-initial-app", system_instruction)
            self.assertIn("app/components/Footer.tsx", system_instruction)
            self.assertIn("Relevant Candidate Component Source Code", system_instruction)
            self.assertIn("https://x.com", system_instruction)
            self.assertIn("forbid proposing new route", system_instruction.lower())

    def test_prompt_endpoint_mock_mode_archetype_aware_questions_and_conditional_adr(self):
        # Round 1: Deletion prompt in mock mode
        resp1 = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "remove social media links like github, x.com, etc",
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1["accepted"])
        turn1 = data1["turn"]
        self.assertEqual(turn1["type"], "grill_round")
        self.assertEqual(turn1["round"], 1)
        self.assertGreaterEqual(len(turn1["questions"]), 2)

        # Questions should be component-scoped, no new route proposed
        q_titles = [q["title"].lower() for q in turn1["questions"]]
        self.assertTrue(any("component" in t or "scope" in t for t in q_titles))
        for q in turn1["questions"]:
            self.assertNotIn("app/routes/", q["recommended"])

        # Round 2: Accept recommended defaults / proceed
        resp2 = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "/proceed",
                "history": [
                    {"role": "user", "text": "remove social media links like github, x.com, etc"},
                    {"role": "assistant", "text": "❓ **Q1** - Component Scope..."},
                ],
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["accepted"])
        turn2 = data2["turn"]
        self.assertEqual(turn2["type"], "ready_for_approval")
        self.assertIsNotNone(turn2["plan"])
        # Conditional ADR: draft_adr is None for deletion
        self.assertIsNone(turn2["draft_adr"])
        self.assertNotIn("Draft ADR Ready", turn2["formatted_text"])

    def test_prompt_endpoint_grill_mode_rejects_intent_guard_violations(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test3",
                "prompt": "Create a backend PostgreSQL database with custom SQL tables",
                "grill": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertIsNotNone(data["refusal"])
        self.assertIsNone(data["turn"])
        self.assertIsNone(data["job"])
        self.assertEqual(len(self.registry.list_jobs()), 0)


class TestStudioApproveEndpoint(unittest.TestCase):
    """Test suite for POST /api/studio/approve endpoint."""

    def setUp(self):
        self.registry = JobRegistry()
        self.preview_registry = PreviewRegistry()
        self.app = create_app(registry=self.registry, preview_reg=self.preview_registry)
        self.client = TestClient(
            self.app,
            headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
        )

    def test_approve_endpoint_unauthenticated_returns_401(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.post(
            "/api/studio/approve",
            json={"repo": "test3", "prompt": "Build dark mode"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_approve_endpoint_missing_repo_returns_400(self):
        resp = self.client.post(
            "/api/studio/approve",
            json={"repo": "", "prompt": "Build dark mode"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Repository name is required", resp.json()["detail"])

    def test_approve_endpoint_missing_prompt_returns_400(self):
        resp = self.client.post(
            "/api/studio/approve",
            json={"repo": "test3", "prompt": "   "},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Prompt is required", resp.json()["detail"])

    def test_approve_endpoint_commits_adr_creates_issue_and_dispatches_job(self):
        fake_milestone = {"number": 12, "title": "Dark Mode Toggle", "slug": "dark-mode-toggle"}
        fake_issue = {
            "number": 42,
            "title": "01: Implement dark mode toggle",
            "body": "Acceptance criteria...",
        }
        draft_adr = {
            "title": "0002: Dark Mode Toggle",
            "filename": "docs/adr/0002-dark-mode-toggle.md",
            "content": "# 0002: Dark Mode Toggle\n\n**Status**: Accepted",
        }

        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        self.preview_registry._previews["test3"] = PreviewState(
            repo="test3",
            status=PreviewStatus.SERVING,
            preview_url="https://sb-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-3000",
        )

        with patch("factory.ui.app.resolve_or_create_milestone", return_value=fake_milestone) as mock_milestone, \
             patch("factory.ui.app.commit_approved_adr_to_branch") as mock_commit_adr, \
             patch("factory.ui.app.synthesize_and_create_issue", return_value=fake_issue) as mock_issue, \
             patch.object(self.registry, "start_job") as mock_start_job:

            mock_commit_adr.return_value = {
                "status": "committed",
                "branch": "factory/dark-mode-toggle",
                "commit_sha": "abc1234",
                "files": ["docs/adr/0002-dark-mode-toggle.md", "CONTEXT.md"],
            }

            resp = self.client.post(
                "/api/studio/approve",
                json={
                    "repo": "test3",
                    "prompt": "Build dark mode toggle with theme persistence",
                    "milestone_title": "Dark Mode Toggle",
                    "draft_adr": draft_adr,
                    "context_update": "# Target Application Domain Context\nUpdated glossary",
                    "model": "deepseek-v4.1-flash",
                },
            )

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["branch"], "factory/dark-mode-toggle")
            self.assertEqual(data["issue"]["number"], 42)
            self.assertEqual(data["milestone"]["slug"], "dark-mode-toggle")
            self.assertIsNotNone(data["job"])
            self.assertEqual(data["job"]["repo"], "test3")
            self.assertEqual(data["job"]["feature"], "dark-mode-toggle")
            self.assertEqual(data["job"]["issue"], "42")

            mock_milestone.assert_called_once_with(repo_name="test3", title="Dark Mode Toggle")
            mock_commit_adr.assert_called_once_with(
                repo_name="test3",
                branch="factory/dark-mode-toggle",
                draft_adr=draft_adr,
                context_update="# Target Application Domain Context\nUpdated glossary",
            )
            mock_issue.assert_called_once_with(
                repo_name="test3",
                prompt="Build dark mode toggle with theme persistence",
                milestone_number=12,
                milestone_slug="dark-mode-toggle",
            )
            mock_start_job.assert_called_once()

    def test_approve_endpoint_with_null_draft_adr_creates_issue_and_dispatches_job(self):
        fake_milestone = {"number": 15, "title": "v1: Initial App", "slug": "v1-initial-app"}
        fake_issue = {
            "number": 43,
            "title": "02: Remove social media links",
            "body": "Acceptance criteria...",
        }

        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        self.preview_registry._previews["test3"] = PreviewState(
            repo="test3",
            status=PreviewStatus.SERVING,
            preview_url="https://sb-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-3000",
        )

        with patch("factory.ui.app.resolve_or_create_milestone", return_value=fake_milestone) as mock_milestone, \
             patch("factory.ui.app.commit_approved_adr_to_branch") as mock_commit_adr, \
             patch("factory.ui.app.synthesize_and_create_issue", return_value=fake_issue) as mock_issue, \
             patch.object(self.registry, "start_job") as mock_start_job:

            mock_commit_adr.return_value = {
                "status": "skipped",
                "branch": "factory/v1-initial-app",
                "files": [],
            }

            resp = self.client.post(
                "/api/studio/approve",
                json={
                    "repo": "test3",
                    "prompt": "Remove social media links from Footer.tsx",
                    "milestone_title": None,
                    "draft_adr": None,
                    "context_update": None,
                },
            )

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            self.assertEqual(data["branch"], "factory/v1-initial-app")
            self.assertEqual(data["issue"]["number"], 43)
            self.assertEqual(data["milestone"]["slug"], "v1-initial-app")
            self.assertIsNotNone(data["job"])
            self.assertEqual(data["job"]["issue"], "43")

            mock_milestone.assert_called_once_with(repo_name="test3", title=None)
            mock_commit_adr.assert_called_once_with(
                repo_name="test3",
                branch="factory/v1-initial-app",
                draft_adr=None,
                context_update=None,
            )
            mock_issue.assert_called_once_with(
                repo_name="test3",
                prompt="Remove social media links from Footer.tsx",
                milestone_number=15,
                milestone_slug="v1-initial-app",
            )
            mock_start_job.assert_called_once()


class TestCommitApprovedAdrToBranch(unittest.TestCase):
    """Test suite for commit_approved_adr_to_branch Git Data API integration."""

    def test_commit_approved_adr_to_branch_success(self):
        from factory.ui.github import commit_approved_adr_to_branch

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/factory/dark-mode" in url:
                # Branch does not exist yet
                resp.status_code = 404
            elif method == "get" and "/git/ref/heads/main" in url:
                # Base main branch exists
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "maincommit123"}}
            elif method == "get" and "/git/commits/maincommit123" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "maintree456"}}
            elif method == "post" and "/git/trees" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree789"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommitabc"}
            elif method == "post" and "/git/refs" in url:
                resp.status_code = 201
                resp.json.return_value = {"ref": "refs/heads/factory/dark-mode", "object": {"sha": "newcommitabc"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)):
            result = commit_approved_adr_to_branch(
                repo_name="my-app",
                branch="factory/dark-mode",
                draft_adr={
                    "filename": "docs/adr/0002-dark-mode.md",
                    "content": "# 0002: Dark Mode\n\nStatus: Accepted",
                },
                context_update="# Updated context",
                token="test-token",
                org="software-factory-09-test",
            )
            self.assertEqual(result["status"], "committed")
            self.assertEqual(result["commit_sha"], "newcommitabc")
            self.assertEqual(result["branch"], "factory/dark-mode")
            self.assertIn("docs/adr/0002-dark-mode.md", result["files"])
            self.assertIn("CONTEXT.md", result["files"])

    def test_commit_approved_adr_to_branch_skipped_when_no_files(self):
        from factory.ui.github import commit_approved_adr_to_branch

        result = commit_approved_adr_to_branch(
            repo_name="my-app",
            branch="factory/no-files",
            draft_adr=None,
            context_update=None,
            token="test-token",
        )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(len(result["files"]), 0)


class TestTargetRepoScaffolding(unittest.TestCase):
    def test_get_scaffold_files(self):
        from factory.ui.scaffold import get_scaffold_files

        files = get_scaffold_files()
        self.assertIn("CONTEXT.md", files)
        self.assertIn("docs/adr/0001-tanstack-start-spa-architecture.md", files)
        self.assertIn("docs/agents/domain.md", files)
        self.assertIn("docs/agents/issue-tracker.md", files)
        self.assertIn("docs/agents/triage-labels.md", files)

        # Check core skills are included in .agents/skills/
        skill_files = [f for f in files if f.startswith(".agents/skills/")]
        self.assertTrue(len(skill_files) > 0)
        self.assertTrue(any("code-review" in f for f in skill_files))
        self.assertTrue(any("tdd" in f for f in skill_files))
        self.assertTrue(any("domain-modeling" in f for f in skill_files))

    def test_scaffold_target_repo_success(self):
        from factory.ui.scaffold import scaffold_target_repo

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "base123commit"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "basetree123"}}
            elif method == "post" and "/git/trees" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)):
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            self.assertTrue(res["files_count"] > 0)

    def test_scaffold_target_repo_transient_delay_polling_success(self):
        from factory.ui.scaffold import scaffold_target_repo

        call_counts = {"ref_calls": 0, "tree_payloads": []}

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                call_counts["ref_calls"] += 1
                if call_counts["ref_calls"] == 1:
                    resp.status_code = 404
                    resp.text = "Not Found"
                else:
                    resp.status_code = 200
                    resp.json.return_value = {"object": {"sha": "base123commit"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "basetree123"}}
            elif method == "post" and "/git/trees" in url:
                call_counts["tree_payloads"].append(kwargs.get("json"))
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)), \
             patch("factory.ui.scaffold.sleep", return_value=None):
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
                timeout_secs=5.0,
                poll_interval_secs=0.1,
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            self.assertGreaterEqual(call_counts["ref_calls"], 2)
            self.assertEqual(len(call_counts["tree_payloads"]), 1)
            self.assertEqual(call_counts["tree_payloads"][0].get("base_tree"), "basetree123")

    def test_scaffold_target_repo_initialization_timeout_raises_504(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        post_calls = []

        def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 404
            resp.text = "Not Found"
            return resp

        def mock_post(url, *args, **kwargs):
            post_calls.append(url)
            resp = MagicMock()
            resp.status_code = 201
            return resp

        with patch("httpx.Client.get", side_effect=mock_get), \
             patch("httpx.Client.post", side_effect=mock_post), \
             patch("factory.ui.scaffold.sleep", return_value=None):
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token="test-token",
                    org="software-factory-09-test",
                    timeout_secs=0.5,
                    poll_interval_secs=0.1,
                )
            self.assertEqual(ctx.exception.status_code, 504)
            self.assertIn("Timed out waiting for repository template replication", str(ctx.exception))
            # Verify POST /git/trees was never invoked
            self.assertFalse(any("/git/trees" in call_url for call_url in post_calls))

    def test_scaffold_target_repo_immediate_readiness_fast_path(self):
        from factory.ui.scaffold import scaffold_target_repo

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "fastcommit1"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "fasttree1"}}
            elif method == "post" and "/git/trees" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)), \
             patch("factory.ui.scaffold.sleep") as mock_sleep:
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
                timeout_secs=5.0,
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            mock_sleep.assert_not_called()

    def test_scaffold_target_repo_fatal_http_error_fails_fast(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 401
            resp.text = "Unauthorized: Bad credentials"
            return resp

        with patch("httpx.Client.get", side_effect=mock_get), \
             patch("factory.ui.scaffold.sleep") as mock_sleep:
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token="bad-token",
                    org="software-factory-09-test",
                    timeout_secs=10.0,
                    poll_interval_secs=1.0,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Failed to check branch reference", str(ctx.exception))
            mock_sleep.assert_not_called()

    def test_scaffold_target_repo_missing_token_raises_error(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        with patch("factory.ui.scaffold.get_test_org_token", return_value=None):
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token=None,
                    org="software-factory-09-test",
                )
            self.assertIn("Missing GitHub organization credentials", str(ctx.exception))

    def test_instantiate_repo_from_template_invokes_scaffolding(self):
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "new-app",
            "full_name": "software-factory-09-test/new-app",
            "html_url": "https://github.com/software-factory-09-test/new-app",
            "description": "App description",
            "private": False,
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {"status": "scaffolded", "commit_sha": "abc1234"}
            result = instantiate_repo_from_template(
                repo_name="new-app",
                token="valid-mock-token",
            )
            self.assertEqual(result["name"], "new-app")
            self.assertTrue(result["is_tanstack_compatible"])
            self.assertTrue(result["scaffolded"])
            mock_scaffold.assert_called_once_with(
                repo_name="new-app",
                token="valid-mock-token",
                org="software-factory-09-test",
                timeout_secs=20.0,
                poll_interval_secs=1.0,
            )

    def test_instantiate_repo_from_template_scaffolding_failure_raises_repo_creation_error(self):
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "failing-app",
            "full_name": "software-factory-09-test/failing-app",
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo", side_effect=RuntimeError("GitHub Git API timeout")):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template(
                    repo_name="failing-app",
                    token="valid-mock-token",
                )
            self.assertIn("failed to scaffold skills and ADRs", str(ctx.exception))

    def test_instantiate_repo_from_template_scaffolding_timeout_raises_504_creation_error(self):
        from factory.ui.scaffold import RepoScaffoldingError
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "timeout-app",
            "full_name": "software-factory-09-test/timeout-app",
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo", side_effect=RepoScaffoldingError("Timed out waiting for repository template replication on 'software-factory-09-test/timeout-app' after 15.0s. Template Provisioning Readiness was not established (default branch reference or base tree SHA unavailable).", status_code=504)):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template(
                    repo_name="timeout-app",
                    token="valid-mock-token",
                )
            self.assertEqual(ctx.exception.status_code, 504)
            self.assertIn("failed to scaffold skills and ADRs", str(ctx.exception))
            self.assertIn("Timed out waiting for repository template replication", str(ctx.exception))




class TestSyncTargetRepoSkills(unittest.TestCase):
    def test_sync_target_repo_skills_sync_repos(self):
        import scripts.sync_target_repo_skills as sync_script

        with patch("scripts.sync_target_repo_skills.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {
                "status": "scaffolded",
                "commit_sha": "abcdef1234",
                "files_count": 31,
            }
            code = sync_script.sync_repos(
                repos=["test1", "test2"],
                token="mock-token",
                org="software-factory-09-test",
            )
            self.assertEqual(code, 0)
            self.assertEqual(mock_scaffold.call_count, 2)

    def test_sync_target_repo_skills_main_repo_arg(self):
        import scripts.sync_target_repo_skills as sync_script

        with patch("scripts.sync_target_repo_skills.get_test_org_token", return_value="mock-token"), \
             patch("scripts.sync_target_repo_skills.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {
                "status": "scaffolded",
                "commit_sha": "abcdef1234",
                "files_count": 31,
            }
            code = sync_script.main(["--repo", "test2"])
            self.assertEqual(code, 0)
            mock_scaffold.assert_called_once()


class TestStudioChatPersistenceAndEndpoints(unittest.TestCase):
    def setUp(self):
        from factory.ui.db import StudioDatabase
        from factory.ui.registry import JobRegistry, PreviewRegistry

        self.db = StudioDatabase(":memory:")
        self.registry = JobRegistry(db=self.db)
        self.preview_registry = PreviewRegistry(db=self.db)
        self.app = create_app(
            registry=self.registry,
            preview_reg=self.preview_registry,
            db=self.db,
        )
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def tearDown(self):
        self.db.close()

    def test_get_chat_messages_empty(self):
        resp = self.client.get("/api/studio/repos/empty-repo/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "empty-repo")
        self.assertEqual(data["messages"], [])

    def test_prompt_submission_fast_guard_rejection_recorded(self):
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "test-repo",
                "prompt": "Set up a PostgreSQL database with schema migrations",
                "grill": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["accepted"])
        self.assertIsNotNone(data["refusal"])

        # Check recorded messages in DB via endpoint
        get_resp = self.client.get("/api/studio/repos/test-repo/messages")
        self.assertEqual(get_resp.status_code, 200)
        messages = get_resp.json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Set up a PostgreSQL database with schema migrations")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], data["refusal"])
        self.assertIsNotNone(messages[1]["turn_data"])
        self.assertTrue(messages[1]["turn_data"]["refusal"])

    def test_prompt_submission_grill_turn_recorded(self):
        history = [
            {"role": "user", "text": "Build an interactive analytics chart dashboard"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Route Placement**: Where should this route go?\n➡️ app/routes/analytics.tsx",
            },
        ]
        resp = self.client.post(
            "/api/studio/prompt",
            json={
                "repo": "auth-app",
                "prompt": "Accept recommended defaults and build the feature",
                "grill": True,
                "history": history,
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNotNone(data["turn"])

        # Check recorded messages
        get_resp = self.client.get("/api/studio/repos/auth-app/messages")
        self.assertEqual(get_resp.status_code, 200)
        messages = get_resp.json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Accept recommended defaults and build the feature")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["turn_data"]["type"], "ready_for_approval")
        self.assertIsNotNone(messages[1]["draft_adr"])
        self.assertIn("docs/adr/", messages[1]["draft_adr"]["filename"])

    def test_approve_plan_records_messages_and_job(self):
        fake_milestone = {"number": 1, "slug": "auth-v1", "title": "Auth"}
        fake_issue = {"number": 42, "title": "Implement OAuth"}

        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        self.preview_registry._previews["auth-app"] = PreviewState(
            repo="auth-app",
            status=PreviewStatus.SERVING,
            preview_url="https://sb-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-3000",
        )

        with patch("factory.ui.app.resolve_or_create_milestone", return_value=fake_milestone), \
             patch("factory.ui.app.commit_approved_adr_to_branch") as mock_commit_adr, \
             patch("factory.ui.app.synthesize_and_create_issue", return_value=fake_issue), \
             patch.object(self.registry, "start_job"):

            mock_commit_adr.return_value = {
                "status": "committed",
                "branch": "factory/auth-v1",
                "commit_sha": "abc1234",
                "files": ["docs/adr/0001-auth.md"],
            }

            resp = self.client.post(
                "/api/studio/approve",
                json={
                    "repo": "auth-app",
                    "prompt": "Approved OAuth 2.0 architecture",
                    "milestone_title": "Auth",
                    "draft_adr": {"title": "ADR 01", "content": "ADR body"},
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            job_id = data["job"]["id"]

            # Check recorded message
            get_resp = self.client.get("/api/studio/repos/auth-app/messages")
            self.assertEqual(get_resp.status_code, 200)
            messages = get_resp.json()["messages"]
            self.assertGreaterEqual(len(messages), 1)
            last_msg = messages[-1]
            self.assertEqual(last_msg["role"], "assistant")
            self.assertEqual(last_msg["milestone_slug"], "auth-v1")
            self.assertEqual(last_msg["issue_number"], 42)
            self.assertEqual(last_msg["turn_data"]["status"], "approved")

            # Check job in database
            db_job = self.db.get_job(job_id)
            self.assertIsNotNone(db_job)
            self.assertEqual(db_job["repo"], "auth-app")
            self.assertEqual(db_job["issue"], "42")

    def test_delete_chat_messages_endpoint(self):
        # Seed message
        self.db.save_chat_message(
            repo="clean-repo",
            role="user",
            content="Hello world",
        )
        self.db.save_chat_message(
            repo="other-repo",
            role="user",
            content="Keep this",
        )

        resp = self.client.delete("/api/studio/repos/clean-repo/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "clean-repo")
        self.assertEqual(data["deleted"], 1)
        self.assertTrue(data["success"])

        # Verify clean-repo messages are gone
        get_resp = self.client.get("/api/studio/repos/clean-repo/messages")
        self.assertEqual(len(get_resp.json()["messages"]), 0)

        # Verify other-repo messages remain
        other_resp = self.client.get("/api/studio/repos/other-repo/messages")
        self.assertEqual(len(other_resp.json()["messages"]), 1)

    def test_rehydration_after_simulated_server_restart(self):
        # Save chat messages and job
        self.db.save_chat_message(
            repo="persist-repo",
            role="user",
            content="Persisted prompt",
        )
        job = self.registry.create_job(
            repo="persist-repo",
            feature="feature-x",
            issue="1",
        )

        # Simulate restart: create new registry and app sharing the same db
        from factory.ui.registry import JobRegistry, PreviewRegistry
        new_registry = JobRegistry(db=self.db)
        new_preview_reg = PreviewRegistry(db=self.db)
        new_app = create_app(
            registry=new_registry,
            preview_reg=new_preview_reg,
            db=self.db,
        )
        new_client = TestClient(new_app)
        new_client.auth = ("admin", "admin")

        # Chat history is retained
        chat_resp = new_client.get("/api/studio/repos/persist-repo/messages")
        self.assertEqual(chat_resp.status_code, 200)
        messages = chat_resp.json()["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "Persisted prompt")

        # Jobs are retained
        jobs_resp = new_client.get("/api/jobs")
        self.assertEqual(jobs_resp.status_code, 200)
        jobs = jobs_resp.json()["jobs"]
        self.assertIn(job.id, [j["id"] for j in jobs])


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


class TestTrunkSynchronization(unittest.TestCase):
    """Test suite for Trunk Synchronization and in-place resync."""

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

    def _register_serving_preview(self, repo: str, branch: str = "main", preview_url: str = "https://preview.modal.host") -> tuple[PreviewState, MagicMock]:
        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        mock_process = MagicMock()
        mock_process.stdout = iter(["HEAD is now at a1b2c3d\n", "SYNC_COMMIT_SHA:a1b2c3d\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        state = PreviewState(
            repo=repo,
            branch=branch,
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url=preview_url,
            sandbox=mock_sandbox,
            sandbox_id=f"sb-{repo}",
        )
        self.preview_registry._previews[repo] = state
        return state, mock_sandbox

    def test_sync_endpoint_when_sandbox_serving(self):
        state, mock_sandbox = self._register_serving_preview("sync-active-repo", branch="main")

        resp = self.client.post(
            "/api/studio/repos/sync-active-repo/preview/sync",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["branch"], "main")
        self.assertEqual(data["commit"], "a1b2c3d")
        self.assertTrue(data["updated"])

        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertEqual(exec_args[0], "bash")
        self.assertEqual(exec_args[1], "-c")
        exec_cmd = exec_args[2]
        self.assertIn("cd /root/sync-active-repo", exec_cmd)
        self.assertIn("git fetch origin main", exec_cmd)
        self.assertIn("git reset --hard origin/main", exec_cmd)
        self.assertIn("git clean -fd", exec_cmd)

        # Dev server logs have 🔄 [SYNC] prefix
        self.assertTrue(any("🔄 [SYNC]" in log for log in state.logs))

    def test_sync_endpoint_defaults_to_active_preview_branch(self):
        state, mock_sandbox = self._register_serving_preview("sync-feature-repo", branch="factory/nav-tabs")

        resp = self.client.post(
            "/api/studio/repos/sync-feature-repo/preview/sync",
            json={},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["branch"], "factory/nav-tabs")
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertIn("git fetch origin factory/nav-tabs", exec_args[2])

    def test_sync_diff_aware_dependency_drift_triggers_pnpm_install(self):
        state, mock_sandbox = self._register_serving_preview("sync-dep-repo", branch="main")

        resp = self.client.post(
            "/api/studio/repos/sync-dep-repo/preview/sync",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 200)
        exec_args, _ = mock_sandbox.exec.call_args
        exec_cmd = exec_args[2]
        self.assertIn("package", exec_cmd)
        self.assertIn("pnpm-lock", exec_cmd)
        self.assertIn("pnpm install --prefer-offline", exec_cmd)

    def test_sync_endpoint_when_idle_persists_branch(self):
        preview = PreviewState(
            repo="idle-repo",
            status=PreviewStatus.IDLE,
            stage=PreviewStage.IDLE,
            branch="main",
        )
        self.preview_registry._previews["idle-repo"] = preview

        resp = self.client.post(
            "/api/studio/repos/idle-repo/preview/sync",
            json={"branch": "factory/new-design"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["branch"], "factory/new-design")
        self.assertIsNone(data["commit"])
        self.assertFalse(data["updated"])
        self.assertEqual(self.preview_registry.get_preview("idle-repo").branch, "factory/new-design")

    def test_sync_broadcasts_preview_refresh_sse_event(self):
        state, mock_sandbox = self._register_serving_preview("sse-sync-repo", branch="main")
        q = self.preview_registry.add_listener("sse-sync-repo")

        resp = self.client.post(
            "/api/studio/repos/sse-sync-repo/preview/sync",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 200)
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        refresh_events = [e for e in events if e.get("event") == "preview_refresh"]
        self.assertTrue(len(refresh_events) >= 1)

    def test_sync_concurrency_lock_rejects_when_job_active(self):
        state, mock_sandbox = self._register_serving_preview("locked-repo", branch="main")
        job = self.registry.create_job(
            repo="locked-repo",
            feature="v1-pipeline",
            model="deepseek-v4.1-flash",
            vm=False,
        )
        job.status = JobStatus.RUNNING

        resp = self.client.post(
            "/api/studio/repos/locked-repo/preview/sync",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("active", resp.json()["detail"].lower())
        mock_sandbox.exec.assert_not_called()

    def test_sync_non_destructive_failure_preserves_container(self):
        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = iter(["fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"])
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        state = PreviewState(
            repo="fail-repo",
            branch="main",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://preview-fail.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-fail",
        )
        self.preview_registry._previews["fail-repo"] = state

        resp = self.client.post(
            "/api/studio/repos/fail-repo/preview/sync",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("terminal prompts disabled", resp.json()["detail"])

        # Preserves container state without termination or failure!
        self.assertEqual(state.status, PreviewStatus.SERVING)
        self.assertTrue(any("❌ [SYNC ERROR]" in log for log in state.logs))

    def test_branch_switch_syncs_when_switching_to_main(self):
        state, mock_sandbox = self._register_serving_preview("switch-repo", branch="factory/feat-a")

        resp = self.client.post(
            "/api/studio/repos/switch-repo/preview/branch",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["branch"], "main")
        self.assertEqual(state.branch, "main")

        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertIn("git fetch origin main", exec_args[2])
        self.assertIn("git reset --hard origin/main", exec_args[2])

    def test_branch_switch_concurrency_lock_rejects_when_job_active(self):
        state, mock_sandbox = self._register_serving_preview("locked-switch-repo", branch="factory/feat-a")
        job = self.registry.create_job(
            repo="locked-switch-repo",
            feature="v1-pipeline",
            model="deepseek-v4.1-flash",
            vm=False,
        )
        job.status = JobStatus.RUNNING

        resp = self.client.post(
            "/api/studio/repos/locked-switch-repo/preview/branch",
            json={"branch": "main"},
        )
        self.assertEqual(resp.status_code, 409)
        mock_sandbox.exec.assert_not_called()
