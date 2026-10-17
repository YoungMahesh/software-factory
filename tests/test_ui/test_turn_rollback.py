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


class TestStudioTurnRollback(unittest.TestCase):
    """Test suite for Turn Rollback and in-place container git reversion (ADR 0050)."""

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

    def _register_serving_preview(
        self,
        repo: str,
        branch: str = "factory/feat-1",
        preview_url: str = "https://preview.modal.host",
        stdout_chunks: list[str] | None = None,
        stderr_chunks: list[str] | None = None,
        exit_code: int = 0,
    ) -> tuple[PreviewState, MagicMock]:
        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        mock_process = MagicMock()
        mock_process.stdout = iter(stdout_chunks or ["ORIGINAL_COMMIT_SHA:abc1111\nREVERT_COMMIT_SHA:def2222\n"])
        mock_process.stderr = iter(stderr_chunks or [])
        mock_process.wait.return_value = exit_code
        mock_process.returncode = exit_code
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

    def test_rollback_concurrency_guard_rejects_active_job(self):
        state, mock_sandbox = self._register_serving_preview("active-repo", branch="factory/feat-1")
        job = self.registry.create_job(repo="active-repo", feature="feat-1")
        with self.registry._lock:
            job.status = JobStatus.RUNNING

        resp = self.client.post("/api/repos/active-repo/rollback", json={})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("active or queued", resp.json()["detail"].lower())
        mock_sandbox.exec.assert_not_called()

    def test_rollback_concurrency_guard_rejects_queued_job(self):
        state, mock_sandbox = self._register_serving_preview("queued-repo", branch="factory/feat-1")
        job = self.registry.create_job(repo="queued-repo", feature="feat-1")
        with self.registry._lock:
            job.status = JobStatus.QUEUED

        resp = self.client.post("/api/repos/queued-repo/rollback", json={})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("active or queued", resp.json()["detail"].lower())
        mock_sandbox.exec.assert_not_called()

    @patch("factory.ui.app.fetch_repo_pull_requests")
    def test_rollback_merge_guard_rejects_merged_pull_request(self, mock_fetch_prs):
        state, mock_sandbox = self._register_serving_preview("merged-repo", branch="factory/feat-1")
        mock_fetch_prs.return_value = [
            {
                "id": 101,
                "number": 1,
                "head_branch": "factory/feat-1",
                "base_branch": "main",
                "merged": True,
                "status": "merged",
            }
        ]

        resp = self.client.post(
            "/api/repos/merged-repo/rollback",
            json={"branch": "factory/feat-1"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("merged into main", resp.json()["detail"].lower())
        mock_sandbox.exec.assert_not_called()

    @patch("factory.ui.app.fetch_repo_pull_requests", return_value=[])
    def test_rollback_git_revert_conflict_aborts_and_returns_400(self, mock_fetch_prs):
        self.db.save_chat_message(
            repo="conflict-repo",
            role="assistant",
            content="Built feature with conflict",
            issue_number=11,
            turn_data={"commit_sha": "abc1111", "branch": "factory/feat-1"},
        )
        state, mock_sandbox = self._register_serving_preview(
            "conflict-repo",
            branch="factory/feat-1",
            stdout_chunks=["error: could not revert abc1111... auto-merging failed\n"],
            stderr_chunks=["CONFLICT (content): Merge conflict in src/App.tsx\n"],
            exit_code=1,
        )

        resp = self.client.post(
            "/api/repos/conflict-repo/rollback",
            json={"branch": "factory/feat-1"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("conflict", resp.json()["detail"].lower())

        # Verify git revert --abort was in the script executed
        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertIn("git revert --abort", exec_args[2])
        self.assertTrue(any("❌ [ROLLBACK ERROR]" in log for log in state.logs))

    @patch("factory.ui.app.fetch_repo_pull_requests", return_value=[])
    @patch("factory.ui.app.reopen_repo_issue_for_rollback")
    def test_rollback_happy_path_with_message_id(self, mock_reopen, mock_fetch_prs):
        # 1. Setup original assistant message in DB
        orig_msg = self.db.save_chat_message(
            repo="happy-repo",
            role="assistant",
            content="Built feature v1",
            issue_number=12,
            turn_data={
                "job_id": "job-12",
                "commit_sha": "abc1111",
                "branch": "factory/feat-1",
            },
        )

        # 2. Setup running sandbox
        state, mock_sandbox = self._register_serving_preview(
            "happy-repo",
            branch="factory/feat-1",
            stdout_chunks=[
                "ORIGINAL_COMMIT_SHA:abc1111\n",
                "REVERT_COMMIT_SHA:def2222\n",
            ],
            exit_code=0,
        )

        # 3. Call rollback
        resp = self.client.post(
            "/api/repos/happy-repo/rollback",
            json={
                "message_id": orig_msg["id"],
                "branch": "factory/feat-1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["branch"], "factory/feat-1")
        self.assertEqual(data["original_commit"], "abc1111")
        self.assertEqual(data["revert_commit"], "def2222")
        self.assertEqual(data["issue_number"], 12)
        self.assertIn("Rolled back", data["message"])

        # 4. Verify in-container execution details
        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        cmd = exec_args[2]
        self.assertIn("cd /root/happy-repo", cmd)
        self.assertIn("git fetch origin factory/feat-1", cmd)
        self.assertIn("git checkout factory/feat-1", cmd)
        self.assertIn("git revert --no-edit", cmd)
        self.assertIn("git push origin factory/feat-1", cmd)
        self.assertIn("pnpm install --prefer-offline", cmd)

        # 5. Verify GitHub issue tracker sync call
        mock_reopen.assert_called_once_with(
            repo_name="happy-repo",
            issue_number=12,
            original_commit_sha="abc1111",
            revert_commit_sha="def2222",
        )

        # 6. Verify SQLite chat history updates
        messages = self.db.get_chat_messages("happy-repo")
        self.assertEqual(len(messages), 2)
        # Original message marked reverted
        orig_updated = messages[0]
        self.assertTrue(orig_updated["turn_data"]["reverted"])
        self.assertEqual(orig_updated["turn_data"]["revert_commit"], "def2222")
        self.assertIn("reverted_at", orig_updated["turn_data"])
        # Append-only rollback message
        rb_card = messages[1]
        self.assertEqual(rb_card["role"], "assistant")
        self.assertEqual(rb_card["turn_data"]["type"], "turn_rollback")
        self.assertEqual(rb_card["turn_data"]["original_message_id"], orig_msg["id"])
        self.assertEqual(rb_card["turn_data"]["original_commit_sha"], "abc1111")
        self.assertEqual(rb_card["turn_data"]["revert_commit_sha"], "def2222")

    @patch("factory.ui.app.fetch_repo_pull_requests", return_value=[])
    @patch("factory.ui.app.reopen_repo_issue_for_rollback")
    def test_rollback_defaults_to_latest_completed_turn_when_message_id_omitted(self, mock_reopen, mock_fetch_prs):
        # Multiple messages
        self.db.save_chat_message(repo="auto-repo", role="user", content="First prompt")
        msg1 = self.db.save_chat_message(
            repo="auto-repo",
            role="assistant",
            content="First completed turn",
            issue_number=1,
            turn_data={"commit_sha": "sha001", "job_id": "j-1"},
        )
        self.db.save_chat_message(repo="auto-repo", role="user", content="Second prompt")
        msg2 = self.db.save_chat_message(
            repo="auto-repo",
            role="assistant",
            content="Second completed turn",
            issue_number=2,
            turn_data={"commit_sha": "sha002", "job_id": "j-2"},
        )

        state, mock_sandbox = self._register_serving_preview(
            "auto-repo",
            branch="factory/v1",
            stdout_chunks=["ORIGINAL_COMMIT_SHA:sha002\nREVERT_COMMIT_SHA:rev002\n"],
            exit_code=0,
        )

        resp = self.client.post("/api/repos/auto-repo/rollback", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["original_commit"], "sha002")
        self.assertEqual(data["revert_commit"], "rev002")
        self.assertEqual(data["issue_number"], 2)

        # Message 2 is marked reverted, message 1 is still un-reverted
        messages = self.db.get_chat_messages("auto-repo")
        msg1_fetched = [m for m in messages if m["id"] == msg1["id"]][0]
        msg2_fetched = [m for m in messages if m["id"] == msg2["id"]][0]
        self.assertFalse(msg1_fetched["turn_data"].get("reverted", False))
        self.assertTrue(msg2_fetched["turn_data"].get("reverted", False))

    def test_rollback_rejects_already_reverted_message(self):
        msg = self.db.save_chat_message(
            repo="re-rollback-repo",
            role="assistant",
            content="Turn",
            turn_data={"commit_sha": "c1", "reverted": True},
        )
        state, _ = self._register_serving_preview("re-rollback-repo")

        resp = self.client.post(
            "/api/repos/re-rollback-repo/rollback",
            json={"message_id": msg["id"]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already been reverted", resp.json()["detail"].lower())

    @patch("factory.ui.app.fetch_repo_pull_requests", return_value=[])
    def test_rollback_auto_boots_stopped_sandbox(self, mock_fetch_prs):
        # 1. Setup completed turn and stopped preview state
        self.db.save_chat_message(
            repo="stopped-repo",
            role="assistant",
            content="Built feature in stopped sandbox",
            turn_data={"commit_sha": "sha999", "branch": "factory/feat-stopped"},
        )
        state = PreviewState(
            repo="stopped-repo",
            branch="factory/feat-stopped",
            status=PreviewStatus.STOPPED,
            stage=PreviewStage.IDLE,
        )
        self.preview_registry._previews["stopped-repo"] = state

        # 2. Mock sandbox that becomes serving
        mock_sandbox = MagicMock()
        mock_sandbox.poll.return_value = None
        mock_process = MagicMock()
        mock_process.stdout = iter(["ORIGINAL_COMMIT_SHA:sha999\nREVERT_COMMIT_SHA:rev999\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        async def fake_wait_for_serving(repo):
            serving_state = PreviewState(
                repo=repo,
                branch="factory/feat-stopped",
                status=PreviewStatus.SERVING,
                stage=PreviewStage.SERVING,
                sandbox=mock_sandbox,
                preview_url="https://preview.modal.host",
            )
            self.preview_registry._previews[repo] = serving_state
            return mock_sandbox, "https://preview.modal.host"

        def fake_launch_preview(repo, branch=None):
            init_state = PreviewState(
                repo=repo,
                branch=branch or "factory/feat-stopped",
                status=PreviewStatus.PROVISIONING,
                stage=PreviewStage.PROVISIONING,
            )
            self.preview_registry._previews[repo] = init_state
            return init_state

        with patch.object(self.preview_registry, "wait_for_serving", side_effect=fake_wait_for_serving) as mock_wait, \
             patch.object(self.preview_registry, "launch_preview", side_effect=fake_launch_preview) as mock_launch:
            resp = self.client.post(
                "/api/repos/stopped-repo/rollback",
                json={"branch": "factory/feat-stopped"},
            )
            self.assertEqual(resp.status_code, 200)
            mock_launch.assert_called_once()
            mock_wait.assert_called_once()
            mock_sandbox.exec.assert_called_once()

    def test_legacy_studio_rollback_returns_404(self):
        resp = self.client.post(
            "/api/studio/repos/any-repo/turns/rollback",
            json={"branch": "factory/feat-stopped"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_update_local_markdown_issue_for_rollback(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            issue_dir = tmproot / ".scratch" / "feat-x" / "issues"
            issue_dir.mkdir(parents=True, exist_ok=True)
            ticket_file = issue_dir / "01-test-feature.md"
            ticket_file.write_text(
                "# 01: Test Feature\n\n**Status:** resolved\n**Commit:** abc1234\n\n- Task 1\n",
                encoding="utf-8",
            )

            updated = update_local_markdown_issue_for_rollback(
                repo_name="test-repo",
                feature="feat-x",
                issue_number=1,
                repo_root=tmproot,
            )
            self.assertTrue(updated)

            content = ticket_file.read_text(encoding="utf-8")
            self.assertIn("**Status:** ready-for-agent", content)
            self.assertNotIn("Commit:", content)
            self.assertNotIn("abc1234", content)
