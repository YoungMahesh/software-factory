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


class TestFastApiPreviewEndpoints(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

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
