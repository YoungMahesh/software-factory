"""Unit and Integration Tests for Factory Testing Console."""

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

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
)
from factory.ui.guard import (
    evaluate_prompt_intent,
    IntentGuardResult,
)
from factory.ui.registry import (
    JobRegistry,
    JobStage,
    JobStatus,
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
    def test_create_repo_endpoint_success(self, mock_instantiate):
        mock_instantiate.return_value = {
            "name": "my-portfolio",
            "full_name": "software-factory-09-test/my-portfolio",
            "html_url": "https://github.com/software-factory-09-test/my-portfolio",
            "description": "Portfolio frontend",
            "private": False,
            "is_tanstack_compatible": True,
            "template_repository": "software-factory-09-test/tanstack-start-template",
        }
        resp = self.client.post("/api/repos", json={"name": "my-portfolio", "description": "Portfolio frontend"})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "my-portfolio")
        self.assertTrue(data["is_tanstack_compatible"])
        self.assertEqual(data["template_repository"], "software-factory-09-test/tanstack-start-template")
        mock_instantiate.assert_called_once_with(
            repo_name="my-portfolio",
            description="Portfolio frontend",
            private=False,
        )

    @patch("factory.ui.app.instantiate_repo_from_template")
    def test_create_repo_endpoint_studio_alias(self, mock_instantiate):
        mock_instantiate.return_value = {
            "name": "studio-app",
            "full_name": "software-factory-09-test/studio-app",
            "html_url": "https://github.com/software-factory-09-test/studio-app",
            "description": None,
            "private": False,
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
            private=False,
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
        resp = unauth_client.get("/api/studio/repos/test3/preview")
        self.assertEqual(resp.status_code, 401)
        resp_post = unauth_client.post("/api/studio/repos/test3/preview")
        self.assertEqual(resp_post.status_code, 401)
        resp_del = unauth_client.delete("/api/studio/repos/test3/preview")
        self.assertEqual(resp_del.status_code, 401)

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
        mock_sandbox.terminate.side_effect = lambda: stop_event.set()
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
        mock_sandbox.terminate.assert_called_once()

        # 5. Subsequent DELETE returns 400 or 404
        resp_del_again = self.client.delete("/api/studio/repos/test3/preview")
        self.assertIn(resp_del_again.status_code, (400, 404))




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
            },
            {
                "name": "todo-app",
                "html_url": "https://github.com/software-factory-09-test/todo-app",
                "description": "Generated from TanStack Start",
                "template_repository": {"name": "tanstack-start-template"},
                "topics": ["tanstack-start"],
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
            self.assertEqual(repos[1]["name"], "todo-app")
            self.assertTrue(repos[1]["is_tanstack_compatible"])

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
            "private": False,
            "template_repository": {
                "name": "tanstack-start-template",
            },
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            result = instantiate_repo_from_template(
                repo_name="new-portfolio",
                description="TanStack Start portfolio app",
                token="test-secret-token",
            )
            self.assertEqual(result["name"], "new-portfolio")
            self.assertEqual(result["full_name"], "software-factory-09-test/new-portfolio")
            self.assertEqual(result["html_url"], "https://github.com/software-factory-09-test/new-portfolio")
            self.assertTrue(result["is_tanstack_compatible"])
            self.assertEqual(result["template_repository"], "software-factory-09-test/tanstack-start-template")

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
        self.app = create_app(registry=self.registry)
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

        with patch.object(self.registry, "start_job") as mock_start_job:
            resp = self.client.post(
                "/api/studio/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build a responsive calculator app with arithmetic history and dark mode",
                    "model": "deepseek-v4.1-flash",
                    "vm": False,
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
            self.assertEqual(data["job"]["preview_url"], "https://3000.mahesh0.dev")
            self.assertEqual(data["preview_url"], "https://3000.mahesh0.dev")
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
        with patch.object(self.registry, "start_job"):
            resp = self.client.post(
                "/api/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build a simple weather dashboard",
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["accepted"])

    def test_prompt_endpoint_unauthenticated_returns_401(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.post(
            "/api/studio/prompt",
            json={"repo": "test3", "prompt": "Build a calculator"},
        )
        self.assertEqual(resp.status_code, 401)


class TestStudioSplitPaneAndDualView(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_top_navigation_view_toggle(self):
        resp_studio = self.client.get("/")
        self.assertEqual(resp_studio.status_code, 200)
        self.assertIn('<div id="root"></div>', resp_studio.text)

        resp_console = self.client.get("/console")
        self.assertEqual(resp_console.status_code, 200)
        self.assertIn('<div id="root"></div>', resp_console.text)

    def test_studio_view_left_sidebar_components(self):
        # API contracts powering the Studio left sidebar (repos and prompt dispatch)
        resp_repos = self.client.get("/api/studio/repos")
        self.assertEqual(resp_repos.status_code, 200)
        self.assertIn("repos", resp_repos.json())

        # Prompt endpoint validation
        resp_invalid = self.client.post("/api/studio/prompt", json={"repo": "", "prompt": ""})
        self.assertEqual(resp_invalid.status_code, 400)

    def test_studio_view_right_workspace_preview_iframe(self):
        # Dev preview jobs populate preview_url for iframe integration
        job = self.registry.create_job(repo="my-cool-app", feature="studio-feat", dev=True)
        self.assertEqual(job.preview_url, "https://3000.mahesh0.dev")
        job_data = self.registry.get_job(job.id)
        self.assertIsNotNone(job_data)
        self.assertEqual(job_data.to_dict()["preview_url"], "https://3000.mahesh0.dev")

    def test_compact_floating_status_badge_and_inspect_logs(self):
        job = self.registry.create_job(repo="my-cool-app", feature="studio-feat")
        resp = self.client.get(f"/api/jobs/{job.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], job.id)
        self.assertEqual(data["stage"], "IDLE")

    def test_console_view_maintains_full_functionality(self):
        resp_repos = self.client.get("/api/repos")
        self.assertEqual(resp_repos.status_code, 200)

        resp_jobs = self.client.get("/api/jobs")
        self.assertEqual(resp_jobs.status_code, 200)
        self.assertIn("jobs", resp_jobs.json())

    def test_repo_options_rendered_in_both_views(self):
        resp1 = self.client.get("/api/repos")
        resp2 = self.client.get("/api/studio/repos")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json()["org"], DEFAULT_TEST_ORG)
        self.assertEqual(resp2.json()["org"], DEFAULT_TEST_ORG)

    def test_recent_runs_rendered_in_console_view(self):
        job = self.registry.create_job(repo="my-cool-app", feature="v1-init", issue="1", model="deepseek-v4.1-flash")
        job.status = JobStatus.SUCCESS
        job.started_at = 100.0
        job.ended_at = 142.0

        resp = self.client.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)
        jobs = resp.json()["jobs"]
        matching = [j for j in jobs if j["id"] == job.id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["repo"], "my-cool-app")
        self.assertEqual(matching[0]["feature"], "v1-init")
        self.assertEqual(matching[0]["duration"], 42.0)

    def test_studio_authentication_compatibility(self):
        unauth_client = TestClient(self.app)
        self.assertEqual(unauth_client.get("/").status_code, 401)
        self.assertEqual(unauth_client.get("/api/studio/repos").status_code, 401)
        self.assertEqual(unauth_client.post("/api/studio/repos", json={"name": "test"}).status_code, 401)
        self.assertEqual(unauth_client.post("/api/studio/prompt", json={"repo": "test", "prompt": "build"}).status_code, 401)

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/studio/repos").status_code, 200)











