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


class TestStudioApproveEndpoint(unittest.TestCase):
    """Test suite for POST /api/approve endpoint."""

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
            "/api/approve",
            json={"repo": "test3", "prompt": "Build dark mode"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_approve_endpoint_missing_repo_returns_400(self):
        resp = self.client.post(
            "/api/approve",
            json={"repo": "", "prompt": "Build dark mode"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Repository name is required", resp.json()["detail"])

    def test_approve_endpoint_missing_prompt_returns_400(self):
        resp = self.client.post(
            "/api/approve",
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
                "/api/approve",
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
                "/api/approve",
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

    def test_legacy_studio_approve_returns_404(self):
        resp = self.client.post(
            "/api/studio/approve",
            json={"repo": "test3", "prompt": "Build dark mode"},
        )
        self.assertEqual(resp.status_code, 404)


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

