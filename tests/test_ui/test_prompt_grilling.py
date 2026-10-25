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


class TestConversationalPromptGrilling(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.preview_registry = PreviewRegistry()
        self.app = create_app(registry=self.registry, preview_reg=self.preview_registry)
        self.client = TestClient(
            self.app,
            headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
        )
        self.client.auth = ("admin", "admin")

    def test_prompt_endpoint_grill_mode_default_returns_grill_round_without_sandbox(self):
        resp = self.client.post(
            "/api/prompt",
            json={
                "repo": "test3",
                "prompt": "Build an interactive analytics chart dashboard",
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["refusal"])
        self.assertIsNone(data["job"])
        self.assertIsNone(data["issue"])
        self.assertIsNone(data["milestone"])

        # Turn payload structure
        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertEqual(turn["type"], "grill_round")
        self.assertEqual(turn["round"], 1)
        self.assertGreaterEqual(len(turn["questions"]), 2)
        self.assertIn("❓ **Q1**", turn["formatted_text"])
        self.assertIn("➡️", turn["formatted_text"])
        self.assertIsNone(turn["draft_adr"])

        # Verify no job dispatched in registry and no sandbox auto-provisioned
        self.assertEqual(len(self.registry.list_jobs()), 0)
        self.assertIsNone(self.preview_registry.get_preview("test3"))

    def test_prompt_endpoint_grill_mode_with_history_reaches_ready_for_approval(self):
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
                "repo": "test3",
                "prompt": "Accept recommended defaults and build the feature",
                "grill": True,
                "history": history,
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["job"])

        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertEqual(turn["type"], "ready_for_approval")
        self.assertEqual(turn["round"], 2)
        self.assertIsNotNone(turn["plan"])
        self.assertIn("Implementation Plan", turn["plan"])

        draft_adr = turn["draft_adr"]
        self.assertIsNotNone(draft_adr)
        self.assertIn("docs/adr/", draft_adr["filename"])
        self.assertTrue(draft_adr["filename"].endswith(".md"))
        self.assertIn("Status**: Proposed", draft_adr["content"])

        # No container or job dispatched yet
        self.assertEqual(len(self.registry.list_jobs()), 0)

    def test_prompt_endpoint_grill_mode_sharpens_domain_terms(self):
        resp = self.client.post(
            "/api/prompt",
            json={
                "repo": "test3",
                "prompt": "Add a customer orders list with a redux store",
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        turn = data["turn"]
        self.assertIsNotNone(turn)
        self.assertTrue(any(s["canonical_term"] == "Client State" for s in turn["sharpened_terms"]))

    def test_prompt_endpoint_inference_failure_returns_structured_error_turn_and_saves_to_db(self):
        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection failed to opencode.ai")):
            resp = self.client.post(
                "/api/prompt",
                json={
                    "repo": "test3",
                    "prompt": "Build an interactive analytics chart dashboard",
                    "grill": True,
                    "mock": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            turn = data["turn"]
            self.assertIsNotNone(turn)
            self.assertEqual(turn["type"], "error")
            self.assertIn("Connection failed", turn["error_message"])
            self.assertIn("OpenCode Go", turn["error_details"])

            # Verify persisted in Studio Chat History (Studio Database)
            get_resp = self.client.get("/api/repos/test3/messages")
            self.assertEqual(get_resp.status_code, 200)
            messages = get_resp.json()["messages"]
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[1]["role"], "assistant")
            self.assertEqual(messages[1]["turn_data"]["type"], "error")
            self.assertEqual(messages[1]["turn_data"]["error_message"], turn["error_message"])

    def test_prompt_endpoint_grill_mode_conducts_codebase_grounding_and_passes_milestone_slug(self):
        remote_resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Clarifying social link removal in Footer",
                            "questions": [
                                {
                                    "id": "Q1",
                                    "title": "Social Links Scope",
                                    "question": "Should all social links in Footer.tsx be removed?",
                                    "recommended": "Remove GitHub, X, and Discord from Footer.tsx.",
                                    "options": ["Remove all links (Recommended)"],
                                }
                            ],
                        })
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_resp
        mock_resp.raise_for_status = MagicMock()

        fake_branches = MagicMock()
        fake_branches.status_code = 200
        fake_branches.json.return_value = [{"name": "factory/v1-initial-app"}]

        fake_tree = MagicMock()
        fake_tree.status_code = 200
        fake_tree.json.return_value = {
            "tree": [
                {"path": "app/routes/index.tsx", "type": "blob"},
                {"path": "app/components/Footer.tsx", "type": "blob"},
            ]
        }

        fake_footer = MagicMock()
        fake_footer.status_code = 200
        fake_footer.text = "export function Footer() { return <div><a href='https://x.com'>X</a></div>; }"

        def fake_async_get(url, headers=None):
            if "branches" in url:
                return fake_branches
            if "git/trees" in url:
                return fake_tree
            return fake_footer

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"), \
             patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_async_get), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:

            resp = self.client.post(
                "/api/prompt",
                json={
                    "repo": "test3",
                    "prompt": "remove social media links like github, x.com, etc",
                    "milestone_title": "v1: Initial App",
                    "grill": True,
                    "mock": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["accepted"])
            turn = data["turn"]
            self.assertIsNotNone(turn)
            self.assertEqual(turn["type"], "grill_round")

            # Check that OpenCode Go received grounded prompt
            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            system_instruction = called_payload["messages"][0]["content"]

            self.assertIn("Repository Codebase Structure", system_instruction)
            self.assertIn("factory/v1-initial-app", system_instruction)
            self.assertIn("app/components/Footer.tsx", system_instruction)
            self.assertIn("Relevant Candidate Component Source Code", system_instruction)
            self.assertIn("https://x.com", system_instruction)
            self.assertIn("forbid proposing new route", system_instruction.lower())

    def test_prompt_endpoint_mock_mode_archetype_aware_questions_and_conditional_adr(self):
        # Round 1: Deletion prompt in mock mode
        resp1 = self.client.post(
            "/api/prompt",
            json={
                "repo": "test3",
                "prompt": "remove social media links like github, x.com, etc",
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1["accepted"])
        turn1 = data1["turn"]
        self.assertEqual(turn1["type"], "grill_round")
        self.assertEqual(turn1["round"], 1)
        self.assertGreaterEqual(len(turn1["questions"]), 2)

        # Questions should be component-scoped, no new route proposed
        q_titles = [q["title"].lower() for q in turn1["questions"]]
        self.assertTrue(any("component" in t or "scope" in t for t in q_titles))
        for q in turn1["questions"]:
            self.assertNotIn("app/routes/", q["recommended"])

        # Round 2: Accept recommended defaults / proceed
        resp2 = self.client.post(
            "/api/prompt",
            json={
                "repo": "test3",
                "prompt": "/proceed",
                "history": [
                    {"role": "user", "text": "remove social media links like github, x.com, etc"},
                    {"role": "assistant", "text": "❓ **Q1** - Component Scope..."},
                ],
                "grill": True,
                "mock": True,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["accepted"])
        turn2 = data2["turn"]
        self.assertEqual(turn2["type"], "ready_for_approval")
        self.assertIsNotNone(turn2["plan"])
        # Conditional ADR: draft_adr is None for deletion
        self.assertIsNone(turn2["draft_adr"])
        self.assertNotIn("Draft ADR Ready", turn2["formatted_text"])

    def test_prompt_endpoint_grill_mode_accepts_database_prompts(self):
        resp = self.client.post(
            "/api/prompt",
            json={
                "repo": "test3",
                "prompt": "Create a backend PostgreSQL database with custom SQL tables",
                "grill": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertIsNone(data["refusal"])
        self.assertIsNotNone(data["turn"])
