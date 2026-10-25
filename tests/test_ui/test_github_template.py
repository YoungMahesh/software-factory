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


class TestGrillingSystemInstructions(unittest.TestCase):
    def test_grilling_system_instruction_includes_client_side_tanstack_start_constraints(self):
        from factory.ui.grill._inference import build_system_instruction
        instruction = build_system_instruction(
            repo="test3",
            context_content="Sample CONTEXT.md",
            existing_adrs=["0001-init.md"],
            formatted_structure="src/App.tsx",
            formatted_sources="export function App() {}",
        )
        self.assertIn("client-side", instruction.lower())
        self.assertIn("tanstack start", instruction.lower())
        self.assertIn("localstorage", instruction.lower())
