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
    fetch_repo_scratch_metadata,
    fetch_test_org_repos,
    get_test_org_token,
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


class TestFastApiApp(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Software Factory", resp.text)
        self.assertIn("Testing Console", resp.text)
        self.assertIn(DEFAULT_TEST_ORG, resp.text)

    def test_get_repos_endpoint(self):
        resp = self.client.get("/api/repos")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["org"], DEFAULT_TEST_ORG)
        self.assertTrue(isinstance(data["repos"], list))

    def test_get_repo_scratch_endpoint(self):
        resp = self.client.get("/api/repos/test3/scratch")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "test3")
        self.assertIn("features", data)

    def test_launch_job_validation(self):
        # Missing feature
        resp1 = self.client.post("/api/jobs", json={"repo": "test3", "feature": ""})
        self.assertEqual(resp1.status_code, 400)

        # Missing repo
        resp2 = self.client.post("/api/jobs", json={"repo": "", "feature": "feat"})
        self.assertEqual(resp2.status_code, 400)

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


class TestCliDispatcherUiFlag(unittest.TestCase):
    def test_parse_args_ui_flags(self):
        args1 = parse_args(["--ui"])
        self.assertTrue(args1.ui)
        self.assertEqual(args1.port, 3000)
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
            self.assertEqual(get_default_port(), 3000)

    def test_get_default_port_env(self):
        with patch.dict("os.environ", {"PORT": "4000"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 4000)

    def test_get_default_port_invalid_env(self):
        with patch.dict("os.environ", {"PORT": "invalid"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 3000)

    @patch("factory.ui.server.start_server")
    def test_server_main_defaults(self, mock_start_server):
        from factory.ui.server import main as server_main
        with patch.dict("os.environ", {}, clear=True):
            server_main([])
            mock_start_server.assert_called_once_with(host="127.0.0.1", port=3000, open_browser=False)

    @patch("factory.ui.server.start_server")
    def test_server_main_custom_args(self, mock_start_server):
        from factory.ui.server import main as server_main
        server_main(["--host", "0.0.0.0", "-p", "5000", "--open"])
        mock_start_server.assert_called_once_with(host="0.0.0.0", port=5000, open_browser=True)

