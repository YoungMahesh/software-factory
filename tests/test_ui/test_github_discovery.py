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
