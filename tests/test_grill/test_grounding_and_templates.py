"""Subsystem tests for GrillingAssistant and Conversational Grilling Service."""

import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from factory.ui.grill import (
    DraftADR,
    GrillQuestion,
    GrillTurnResult,
    GrillingAssistant,
    classify_prompt_archetype,
    resolve_opencode_go_api_key,
    sharpen_domain_terms,
)


class TestCodebaseGrounding(unittest.IsolatedAsyncioTestCase):
    """Test autonomous codebase fact-finding and context ingestion before grilling."""

    async def test_resolve_active_branch_prefers_milestone_branch_if_present(self):
        assistant = GrillingAssistant(mock=False)
        fake_branches_resp = MagicMock()
        fake_branches_resp.status_code = 200
        fake_branches_resp.json.return_value = [
            {"name": "main"},
            {"name": "factory/v1-initial-app"},
            {"name": "factory/v2-analytics"},
        ]

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = fake_branches_resp

                branch = await assistant.resolve_active_branch("inventory-tracker", milestone_slug="v2-analytics")
                self.assertEqual(branch, "factory/v2-analytics")

    async def test_resolve_active_branch_falls_back_to_main_when_no_milestone_branch(self):
        assistant = GrillingAssistant(mock=False)
        fake_branches_resp = MagicMock()
        fake_branches_resp.status_code = 200
        fake_branches_resp.json.return_value = [
            {"name": "main"},
        ]

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = fake_branches_resp

                branch = await assistant.resolve_active_branch("inventory-tracker", milestone_slug="nonexistent-ms")
                self.assertEqual(branch, "main")

    async def test_get_repo_file_tree_retrieves_recursive_tree_and_extracts_routes_and_components(self):
        assistant = GrillingAssistant(mock=False)
        fake_tree_resp = MagicMock()
        fake_tree_resp.status_code = 200
        fake_tree_resp.json.return_value = {
            "tree": [
                {"path": "app/routes/__root.tsx", "type": "blob"},
                {"path": "app/routes/index.tsx", "type": "blob"},
                {"path": "app/components/Header.tsx", "type": "blob"},
                {"path": "app/components/Footer.tsx", "type": "blob"},
                {"path": "package.json", "type": "blob"},
                {"path": "app/components", "type": "tree"},
            ]
        }

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = fake_tree_resp

                paths = await assistant.get_repo_file_tree("inventory-tracker", branch="main")
                self.assertIn("app/routes/index.tsx", paths)
                self.assertIn("app/components/Footer.tsx", paths)
                self.assertNotIn("app/components", paths)

    def test_score_candidate_files_matches_footer_for_social_media_links(self):
        assistant = GrillingAssistant(mock=False)
        file_paths = [
            "app/routes/__root.tsx",
            "app/routes/index.tsx",
            "app/routes/analytics.tsx",
            "app/components/Header.tsx",
            "app/components/Footer.tsx",
            "package.json",
        ]

        prompt = "remove social media links like github, x.com, etc"
        candidates = assistant.score_candidate_files(file_paths, prompt=prompt)

        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0], "app/components/Footer.tsx")

    async def test_fetch_candidate_file_contents_respects_count_and_25kb_budget(self):
        assistant = GrillingAssistant(mock=False)
        candidate_paths = [
            "app/components/Footer.tsx",
            "app/components/Header.tsx",
            "app/routes/index.tsx",
            "app/routes/analytics.tsx",
        ]

        def fake_get_side_effect(url, headers=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "// " + url + "\n" + ("x" * 10000)
            return resp

        with patch("factory.ui.grill.get_test_org_token", return_value="gh-token-123"):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = fake_get_side_effect

                contents = await assistant.fetch_candidate_file_contents(
                    "inventory-tracker",
                    file_paths=candidate_paths,
                    branch="main",
                    max_total_bytes=25000,
                )

                self.assertLessEqual(len(contents), 3)
                total_bytes = sum(len(c.encode("utf-8")) for c in contents.values())
                self.assertLessEqual(total_bytes, 25000)

    async def test_live_turn_injects_codebase_structure_and_candidate_source_into_prompt(self):
        assistant = GrillingAssistant(api_key="oc_live_valid_token_123", mock=False)

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

        with patch.object(assistant, "resolve_active_branch", new_callable=AsyncMock, return_value="factory/v1-initial-app"), \
             patch.object(assistant, "get_repo_file_tree", new_callable=AsyncMock, return_value=["app/routes/index.tsx", "app/components/Footer.tsx"]), \
             patch.object(assistant, "fetch_candidate_file_contents", new_callable=AsyncMock, return_value={"app/components/Footer.tsx": "export function Footer() { return <div>GitHub</div>; }"}), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:

            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="remove social media links like github, x.com, etc",
                history=[],
            )

            self.assertEqual(turn.type, "grill_round")
            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            system_instruction = called_payload["messages"][0]["content"]

            self.assertIn("Repository Codebase Structure", system_instruction)
            self.assertIn("factory/v1-initial-app", system_instruction)
            self.assertIn("app/components/Footer.tsx", system_instruction)
            self.assertIn("Relevant Candidate Component Source Code", system_instruction)
            self.assertIn("export function Footer()", system_instruction)
            self.assertIn("forbid proposing new route", system_instruction.lower())

    async def test_mock_mode_does_not_make_github_network_calls(self):
        assistant = GrillingAssistant(mock=True)
        self.assertTrue(assistant.is_mock_mode)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="remove social media links like github, x.com, etc",
                history=[],
            )
            self.assertEqual(turn.type, "grill_round")
            mock_get.assert_not_called()

    async def test_multiturn_grounding_retains_component_context_from_initial_prompt(self):
        assistant = GrillingAssistant(api_key="oc_live_valid_token_123", mock=False)

        history = [
            {"role": "user", "text": "remove social media links like github, x.com, etc"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Social Links Scope**: Should all links in Footer.tsx be removed?\n➡️ Remove all links.",
            },
        ]

        remote_resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "ready_for_approval",
                            "round": 2,
                            "summary": "Plan ready for approval",
                            "plan": "Update Footer.tsx to remove social links",
                            "draft_adr": {
                                "title": "0002: Social Links",
                                "filename": "docs/adr/0002-social-links.md",
                                "content": "ADR content",
                            },
                        })
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_resp
        mock_resp.raise_for_status = MagicMock()

        with patch.object(assistant, "resolve_active_branch", new_callable=AsyncMock, return_value="main"), \
             patch.object(assistant, "get_repo_file_tree", new_callable=AsyncMock, return_value=["app/routes/index.tsx", "app/components/Footer.tsx"]), \
             patch.object(assistant, "fetch_candidate_file_contents", new_callable=AsyncMock, return_value={"app/components/Footer.tsx": "export function Footer() {}"}), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:

            # Developer replies with short confirmation
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Accept recommended defaults",
                history=history,
            )

            self.assertEqual(turn.type, "ready_for_approval")
            called_payload = mock_post.call_args[1]["json"]
            system_instruction = called_payload["messages"][0]["content"]

            # Grounding retained Footer.tsx even though current prompt was "Accept recommended defaults"
            self.assertIn("app/components/Footer.tsx", system_instruction)
            self.assertIn("export function Footer()", system_instruction)


class TestPromptTemplates(unittest.TestCase):
    """Test loading and rendering of externalized Markdown prompt templates."""

    def test_load_prompt_template_success(self):
        from factory.ui.grill._prompts import load_prompt_template

        template = load_prompt_template("grilling_assistant", reload=True)
        self.assertIn("Factory Studio Grilling Assistant", template)
        self.assertIn("{{repo}}", template)
        self.assertIn("{{context_content}}", template)
        self.assertIn("{{existing_adrs}}", template)
        self.assertIn("{{formatted_structure}}", template)
        self.assertIn("{{formatted_sources}}", template)
        # Ensure raw JSON schemas have unescaped single braces
        self.assertIn('{\n  "type": "grill_round"', template)

    def test_load_prompt_template_cached(self):
        from factory.ui.grill._prompts import load_prompt_template

        tmpl1 = load_prompt_template("grilling_assistant", reload=True)
        with patch("pathlib.Path.read_text") as mock_read:
            tmpl2 = load_prompt_template("grilling_assistant")
            mock_read.assert_not_called()
            self.assertEqual(tmpl1, tmpl2)

    def test_load_prompt_template_reload_bypasses_cache(self):
        from factory.ui.grill._prompts import load_prompt_template

        load_prompt_template("grilling_assistant", reload=True)
        with patch("pathlib.Path.read_text", return_value="Reloaded template {{repo}}") as mock_read:
            reloaded = load_prompt_template("grilling_assistant", reload=True)
            mock_read.assert_called_once()
            self.assertEqual(reloaded, "Reloaded template {{repo}}")

    def test_load_prompt_template_missing_file_raises_filenotfound(self):
        from factory.ui.grill._prompts import load_prompt_template

        with self.assertRaises(FileNotFoundError) as ctx:
            load_prompt_template("non_existent_prompt_template_xyz", reload=True)
        self.assertIn("non_existent_prompt_template_xyz", str(ctx.exception))

    def test_render_prompt_template(self):
        from factory.ui.grill._prompts import render_prompt_template

        rendered = render_prompt_template(
            "grilling_assistant",
            {
                "repo": "sample-repo",
                "context_content": "Context information",
                "existing_adrs": '["0001-init.md"]',
                "formatted_structure": "src/index.ts",
                "formatted_sources": "console.log('hello');",
            },
            reload=True,
        )
        self.assertIn("Factory Studio Grilling Assistant for the repository 'sample-repo'", rendered)
        self.assertIn("Context information", rendered)
        self.assertIn('["0001-init.md"]', rendered)
        self.assertIn("src/index.ts", rendered)
        self.assertIn("console.log('hello');", rendered)
        # Unescaped JSON schemas remain valid
        self.assertIn('{\n  "type": "grill_round"', rendered)
        self.assertNotIn("{{repo}}", rendered)

    def test_build_system_instruction_uses_rendered_template(self):
        from factory.ui.grill._inference import build_system_instruction

        instruction = build_system_instruction(
            repo="my-custom-app",
            context_content="Custom app context",
            existing_adrs=["0001-setup.md", "0002-feature.md"],
            formatted_structure="app/routes/index.tsx",
            formatted_sources="export function Route() {}",
        )
        self.assertIn("Factory Studio Grilling Assistant for the repository 'my-custom-app'", instruction)
        self.assertIn("Custom app context", instruction)
        self.assertIn('["0001-setup.md", "0002-feature.md"]', instruction)
        self.assertIn("app/routes/index.tsx", instruction)
        self.assertIn("export function Route() {}", instruction)
        self.assertIn('{\n  "type": "grill_round"', instruction)
        self.assertNotIn("{{repo}}", instruction)

    def test_build_system_instruction_caches_appropriately(self):
        from factory.ui.grill._inference import build_system_instruction
        from factory.ui.grill._prompts import load_prompt_template

        load_prompt_template("grilling_assistant", reload=True)
        with patch("pathlib.Path.read_text") as mock_read:
            instruction = build_system_instruction(
                repo="cached-app",
                context_content="ctx",
                existing_adrs=[],
                formatted_structure="",
                formatted_sources="",
            )
            mock_read.assert_not_called()
            self.assertIn("cached-app", instruction)

    def test_build_system_instruction_missing_template_raises_filenotfound(self):
        from factory.ui.grill._inference import build_system_instruction

        with patch("factory.ui.grill._prompts.PROMPTS_DIR", Path("/nonexistent/directory/prompts")), \
             patch("factory.ui.grill._prompts._PROMPT_CACHE", {}):
            with self.assertRaises(FileNotFoundError) as ctx:
                build_system_instruction(
                    repo="my-app",
                    context_content="ctx",
                    existing_adrs=[],
                    formatted_structure="",
                    formatted_sources="",
                )
            self.assertIn("grilling_assistant", str(ctx.exception))
