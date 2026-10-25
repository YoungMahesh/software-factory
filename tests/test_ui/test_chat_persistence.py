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
        resp = self.client.get("/api/repos/empty-repo/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "empty-repo")
        self.assertEqual(data["messages"], [])

    def test_prompt_submission_with_backend_prompt_recorded_in_db(self):
        resp = self.client.post(
            "/api/prompt",
            json={
                "repo": "test-repo",
                "prompt": "Set up a PostgreSQL database with schema migrations",
                "grill": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])

        # Check recorded messages in DB via endpoint
        get_resp = self.client.get("/api/repos/test-repo/messages")
        self.assertEqual(get_resp.status_code, 200)
        messages = get_resp.json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Set up a PostgreSQL database with schema migrations")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIsNotNone(messages[1]["turn_data"])

    def test_prompt_submission_grill_turn_recorded(self):
        history = [
            {"role": "user", "text": "Build an interactive analytics chart dashboard"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Route Placement**: Where should this route go?\n➡️ app/routes/analytics.tsx",
            },
        ]
        resp = self.client.post(
            "/api/prompt",
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
        get_resp = self.client.get("/api/repos/auth-app/messages")
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
                "/api/approve",
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
            get_resp = self.client.get("/api/repos/auth-app/messages")
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

        resp = self.client.delete("/api/repos/clean-repo/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repo"], "clean-repo")
        self.assertEqual(data["deleted"], 1)
        self.assertTrue(data["success"])

        # Verify clean-repo messages are gone
        get_resp = self.client.get("/api/repos/clean-repo/messages")
        self.assertEqual(len(get_resp.json()["messages"]), 0)

        # Verify other-repo messages remain
        other_resp = self.client.get("/api/repos/other-repo/messages")
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
        chat_resp = new_client.get("/api/repos/persist-repo/messages")
        self.assertEqual(chat_resp.status_code, 200)
        messages = chat_resp.json()["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "Persisted prompt")

        # Jobs are retained
        jobs_resp = new_client.get("/api/jobs")
        self.assertEqual(jobs_resp.status_code, 200)
        jobs = jobs_resp.json()["jobs"]
        self.assertIn(job.id, [j["id"] for j in jobs])

    def test_mark_chat_message_reverted(self):
        msg = self.db.save_chat_message(
            repo="rollback-repo",
            role="assistant",
            content="Built feature",
            issue_number=10,
            turn_data={"job_id": "j-123", "sha": "abc1234"},
        )
        updated = self.db.mark_chat_message_reverted(
            message_id=msg["id"],
            revert_commit="def5678",
        )
        self.assertIsNotNone(updated)
        self.assertTrue(updated["turn_data"]["reverted"])
        self.assertEqual(updated["turn_data"]["revert_commit"], "def5678")
        self.assertEqual(updated["turn_data"]["sha"], "abc1234")
        self.assertIn("reverted_at", updated["turn_data"])

        # Re-fetch from db
        messages = self.db.get_chat_messages("rollback-repo")
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0]["turn_data"]["reverted"])
        self.assertEqual(messages[0]["turn_data"]["revert_commit"], "def5678")

        # Non-existent message returns None
        self.assertIsNone(self.db.mark_chat_message_reverted("non-existent-id"))

    def test_save_rollback_message(self):
        rb_msg = self.db.save_rollback_message(
            repo="rollback-repo",
            original_message_id="msg-orig-1",
            original_commit_sha="abc1234",
            revert_commit_sha="def5678",
            issue_number=10,
            branch="factory/v1-feature",
        )
        self.assertEqual(rb_msg["role"], "assistant")
        self.assertEqual(rb_msg["repo"], "rollback-repo")
        self.assertEqual(rb_msg["issue_number"], 10)
        self.assertIn("Rolled back", rb_msg["content"])
        self.assertIn("abc1234", rb_msg["content"])
        self.assertIn("def5678", rb_msg["content"])
        self.assertEqual(rb_msg["turn_data"]["type"], "turn_rollback")
        self.assertEqual(rb_msg["turn_data"]["original_message_id"], "msg-orig-1")
        self.assertEqual(rb_msg["turn_data"]["original_commit_sha"], "abc1234")
        self.assertEqual(rb_msg["turn_data"]["revert_commit_sha"], "def5678")
        self.assertEqual(rb_msg["turn_data"]["branch"], "factory/v1-feature")

        # Re-fetch
        messages = self.db.get_chat_messages("rollback-repo")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["turn_data"]["type"], "turn_rollback")
