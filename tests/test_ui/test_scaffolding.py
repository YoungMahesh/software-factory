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


class TestTargetRepoScaffolding(unittest.TestCase):
    def test_get_scaffold_files(self):
        from factory.ui.scaffold import get_scaffold_files

        files = get_scaffold_files()
        self.assertIn("CONTEXT.md", files)
        self.assertIn("docs/adr/0001-tanstack-start-spa-architecture.md", files)
        self.assertIn("docs/agents/domain.md", files)
        self.assertIn("docs/agents/issue-tracker.md", files)
        self.assertIn("docs/agents/triage-labels.md", files)

        # Check core skills are included in .agents/skills/
        skill_files = [f for f in files if f.startswith(".agents/skills/")]
        self.assertTrue(len(skill_files) > 0)
        self.assertTrue(any("code-review" in f for f in skill_files))
        self.assertTrue(any("tdd" in f for f in skill_files))
        self.assertTrue(any("domain-modeling" in f for f in skill_files))

        # Check routing conventions reference src/routes/ instead of legacy app/routes/
        self.assertIn("src/routes/", files["CONTEXT.md"])
        self.assertNotIn("app/routes/", files["CONTEXT.md"])
        self.assertIn("src/routes/", files["docs/adr/0001-tanstack-start-spa-architecture.md"])
        self.assertNotIn("app/routes/", files["docs/adr/0001-tanstack-start-spa-architecture.md"])

    def test_scaffold_target_repo_success(self):
        from factory.ui.scaffold import scaffold_target_repo

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "base123commit"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "basetree123"}}
            elif method == "post" and "/git/trees" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)):
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            self.assertTrue(res["files_count"] > 0)

    def test_scaffold_target_repo_transient_delay_polling_success(self):
        from factory.ui.scaffold import scaffold_target_repo

        call_counts = {"ref_calls": 0, "tree_payloads": []}

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                call_counts["ref_calls"] += 1
                if call_counts["ref_calls"] == 1:
                    resp.status_code = 404
                    resp.text = "Not Found"
                else:
                    resp.status_code = 200
                    resp.json.return_value = {"object": {"sha": "base123commit"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "basetree123"}}
            elif method == "post" and "/git/trees" in url:
                call_counts["tree_payloads"].append(kwargs.get("json"))
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)), \
             patch("factory.ui.scaffold.sleep", return_value=None):
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
                timeout_secs=5.0,
                poll_interval_secs=0.1,
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            self.assertGreaterEqual(call_counts["ref_calls"], 2)
            self.assertEqual(len(call_counts["tree_payloads"]), 1)
            self.assertEqual(call_counts["tree_payloads"][0].get("base_tree"), "basetree123")

    def test_scaffold_target_repo_initialization_timeout_raises_504(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        post_calls = []

        def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 404
            resp.text = "Not Found"
            return resp

        def mock_post(url, *args, **kwargs):
            post_calls.append(url)
            resp = MagicMock()
            resp.status_code = 201
            return resp

        with patch("httpx.Client.get", side_effect=mock_get), \
             patch("httpx.Client.post", side_effect=mock_post), \
             patch("factory.ui.scaffold.sleep", return_value=None):
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token="test-token",
                    org="software-factory-09-test",
                    timeout_secs=0.5,
                    poll_interval_secs=0.1,
                )
            self.assertEqual(ctx.exception.status_code, 504)
            self.assertIn("Timed out waiting for repository template replication", str(ctx.exception))
            # Verify POST /git/trees was never invoked
            self.assertFalse(any("/git/trees" in call_url for call_url in post_calls))

    def test_scaffold_target_repo_immediate_readiness_fast_path(self):
        from factory.ui.scaffold import scaffold_target_repo

        def mock_client_call(method, url, *args, **kwargs):
            resp = MagicMock()
            if method == "get" and "/git/ref/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "fastcommit1"}}
            elif method == "get" and "/git/commits/" in url:
                resp.status_code = 200
                resp.json.return_value = {"tree": {"sha": "fasttree1"}}
            elif method == "post" and "/git/trees" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newtree456"}
            elif method == "post" and "/git/commits" in url:
                resp.status_code = 201
                resp.json.return_value = {"sha": "newcommit789"}
            elif method == "patch" and "/git/refs/heads/" in url:
                resp.status_code = 200
                resp.json.return_value = {"object": {"sha": "newcommit789"}}
            else:
                resp.status_code = 404
                resp.text = "Not found"
            return resp

        with patch("httpx.Client.get", side_effect=lambda url, **kw: mock_client_call("get", url, **kw)), \
             patch("httpx.Client.post", side_effect=lambda url, **kw: mock_client_call("post", url, **kw)), \
             patch("httpx.Client.patch", side_effect=lambda url, **kw: mock_client_call("patch", url, **kw)), \
             patch("factory.ui.scaffold.sleep") as mock_sleep:
            res = scaffold_target_repo(
                repo_name="demo-target-app",
                token="test-token",
                org="software-factory-09-test",
                timeout_secs=5.0,
            )
            self.assertEqual(res["status"], "scaffolded")
            self.assertEqual(res["commit_sha"], "newcommit789")
            mock_sleep.assert_not_called()

    def test_scaffold_target_repo_fatal_http_error_fails_fast(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 401
            resp.text = "Unauthorized: Bad credentials"
            return resp

        with patch("httpx.Client.get", side_effect=mock_get), \
             patch("factory.ui.scaffold.sleep") as mock_sleep:
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token="bad-token",
                    org="software-factory-09-test",
                    timeout_secs=10.0,
                    poll_interval_secs=1.0,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Failed to check branch reference", str(ctx.exception))
            mock_sleep.assert_not_called()

    def test_scaffold_target_repo_missing_token_raises_error(self):
        from factory.ui.scaffold import scaffold_target_repo, RepoScaffoldingError

        with patch("factory.ui.scaffold.get_test_org_token", return_value=None):
            with self.assertRaises(RepoScaffoldingError) as ctx:
                scaffold_target_repo(
                    repo_name="demo-target-app",
                    token=None,
                    org="software-factory-09-test",
                )
            self.assertIn("Missing GitHub organization credentials", str(ctx.exception))

    def test_instantiate_repo_from_template_invokes_scaffolding(self):
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "new-app",
            "full_name": "software-factory-09-test/new-app",
            "html_url": "https://github.com/software-factory-09-test/new-app",
            "description": "App description",
            "private": False,
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {"status": "scaffolded", "commit_sha": "abc1234"}
            result = instantiate_repo_from_template(
                repo_name="new-app",
                token="valid-mock-token",
            )
            self.assertEqual(result["name"], "new-app")
            self.assertTrue(result["is_tanstack_compatible"])
            self.assertTrue(result["scaffolded"])
            mock_scaffold.assert_called_once_with(
                repo_name="new-app",
                token="valid-mock-token",
                org="software-factory-09-test",
                timeout_secs=20.0,
                poll_interval_secs=1.0,
            )

    def test_instantiate_repo_from_template_scaffolding_failure_raises_repo_creation_error(self):
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "failing-app",
            "full_name": "software-factory-09-test/failing-app",
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo", side_effect=RuntimeError("GitHub Git API timeout")):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template(
                    repo_name="failing-app",
                    token="valid-mock-token",
                )
            self.assertIn("failed to scaffold skills and ADRs", str(ctx.exception))

    def test_instantiate_repo_from_template_scaffolding_timeout_raises_504_creation_error(self):
        from factory.ui.scaffold import RepoScaffoldingError
        mock_generate_resp = MagicMock()
        mock_generate_resp.status_code = 201
        mock_generate_resp.json.return_value = {
            "name": "timeout-app",
            "full_name": "software-factory-09-test/timeout-app",
        }

        with patch("httpx.Client.post", return_value=mock_generate_resp), \
             patch("factory.ui.github.fetch_test_org_repos", return_value=[]), \
             patch("factory.ui.scaffold.scaffold_target_repo", side_effect=RepoScaffoldingError("Timed out waiting for repository template replication on 'software-factory-09-test/timeout-app' after 15.0s. Template Provisioning Readiness was not established (default branch reference or base tree SHA unavailable).", status_code=504)):
            with self.assertRaises(RepoCreationError) as ctx:
                instantiate_repo_from_template(
                    repo_name="timeout-app",
                    token="valid-mock-token",
                )
            self.assertEqual(ctx.exception.status_code, 504)
            self.assertIn("failed to scaffold skills and ADRs", str(ctx.exception))
            self.assertIn("Timed out waiting for repository template replication", str(ctx.exception))




class TestSyncTargetRepoSkills(unittest.TestCase):
    def test_sync_target_repo_skills_sync_repos(self):
        import scripts.sync_target_repo_skills as sync_script

        with patch("scripts.sync_target_repo_skills.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {
                "status": "scaffolded",
                "commit_sha": "abcdef1234",
                "files_count": 31,
            }
            code = sync_script.sync_repos(
                repos=["test1", "test2"],
                token="mock-token",
                org="software-factory-09-test",
            )
            self.assertEqual(code, 0)
            self.assertEqual(mock_scaffold.call_count, 2)

    def test_sync_target_repo_skills_main_repo_arg(self):
        import scripts.sync_target_repo_skills as sync_script

        with patch("scripts.sync_target_repo_skills.get_test_org_token", return_value="mock-token"), \
             patch("scripts.sync_target_repo_skills.scaffold_target_repo") as mock_scaffold:
            mock_scaffold.return_value = {
                "status": "scaffolded",
                "commit_sha": "abcdef1234",
                "files_count": 31,
            }
            code = sync_script.main(["--repo", "test2"])
            self.assertEqual(code, 0)
            mock_scaffold.assert_called_once()
