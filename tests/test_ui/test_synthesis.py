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
        self.assertIn("Replace default starter template placeholder markup in src/routes/index.tsx with the new application UI.", body)
        self.assertIn("Update the header brand in src/components/Header.tsx to display the application title.", body)

    def test_synthesize_ticket_content_sequential_ticket(self):
        prompt = "Add CSV export for calculation history with a download button."
        title, body = synthesize_ticket_content(prompt, seq_num=2, previous_issue_number=1)

        self.assertTrue(title.startswith("02: "))
        self.assertIn("CSV", title)
        self.assertIn("**Blocked by:** #1", body)
        self.assertIn("**Status:** ready-for-agent", body)
        self.assertIn("- [ ]", body)
        self.assertNotIn("starter template placeholder markup", body)
        self.assertNotIn("Update the header brand in src/components/Header.tsx", body)

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


class TestCleanCanvasPromptInvariants(unittest.TestCase):
    def setUp(self):
        self.prompts_dir = Path(__file__).resolve().parent.parent.parent / "sandbox" / "factory" / "harness" / "prompts"

    def test_planner_system_prompt_clean_canvas_invariant(self):
        planner_path = self.prompts_dir / "planner_system.md"
        self.assertTrue(planner_path.exists())
        content = planner_path.read_text(encoding="utf-8")
        self.assertIn("Clean Canvas Invariant", content)
        self.assertIn("src/routes/index.tsx", content)
        self.assertIn("src/components/Header.tsx", content)

    def test_coder_system_prompt_clean_canvas_instructions(self):
        coder_path = self.prompts_dir / "coder_system.md"
        self.assertTrue(coder_path.exists())
        content = coder_path.read_text(encoding="utf-8")
        self.assertIn("src/routes/index.tsx", content)
        self.assertIn("src/components/Header.tsx", content)

    def test_reviewer_system_prompt_template_boilerplate_rejection(self):
        reviewer_path = self.prompts_dir / "reviewer_system.md"
        self.assertTrue(reviewer_path.exists())
        content = reviewer_path.read_text(encoding="utf-8")
        self.assertIn("Application Workspace", content)
        self.assertIn("Ready for development", content)
        self.assertIn("blocker", content.lower())

