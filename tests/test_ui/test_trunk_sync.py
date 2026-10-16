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
