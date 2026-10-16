"""Unit tests for GrillingAssistant and Conversational Grilling Service."""

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


class TestGrillCredentials(unittest.TestCase):
    """Test resolution of OpenCode Go credentials across env, config files, and sops."""

    def test_resolve_from_options(self):
        key = resolve_opencode_go_api_key(options={"api_key": "custom-key-123"})
        self.assertEqual(key, "custom-key-123")

    def test_resolve_from_environment_opencode_go(self):
        with patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "env-go-key-456"}, clear=True):
            key = resolve_opencode_go_api_key()
            self.assertEqual(key, "env-go-key-456")

    def test_resolve_from_environment_opencode_api_key(self):
        with patch.dict("os.environ", {"OPENCODE_API_KEY": "env-std-key-789"}, clear=True):
            key = resolve_opencode_go_api_key()
            self.assertEqual(key, "env-std-key-789")

    def test_resolve_from_config_file(self):
        fake_config = Path("/tmp/fake_opencode.env")
        fake_config.write_text("OPENCODE_GO_API_KEY=file-key-999\n", encoding="utf-8")
        try:
            with patch.dict("os.environ", {}, clear=True):
                key = resolve_opencode_go_api_key(options={"env_path": str(fake_config)})
                self.assertEqual(key, "file-key-999")
        finally:
            if fake_config.exists():
                fake_config.unlink()

    def test_resolve_none_when_no_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("pathlib.Path.is_file", return_value=False):
                with patch("pathlib.Path.exists", return_value=False):
                    key = resolve_opencode_go_api_key(options={"env_path": "/nonexistent/path"})
                    self.assertIsNone(key)


class TestDomainSharpening(unittest.TestCase):
    """Test domain term sharpening against CONTEXT.md."""

    def test_sharpen_fuzzy_redux_to_client_state(self):
        context = """# Target App
## Language
**Client State**:
Local and shared component state managed through React state primitives and TanStack Query cache.
_Avoid_: Redux store, MobX store
"""
        sharpened = sharpen_domain_terms("Build a dashboard with a redux store", context_content=context)
        self.assertTrue(any(s["canonical_term"] == "Client State" for s in sharpened))
        matched = next(s for s in sharpened if s["canonical_term"] == "Client State")
        self.assertIn("Redux store", matched["fuzzy_term"])

    def test_sharpen_nextjs_to_tanstack_start_spa(self):
        context = """# Target App
## Language
**TanStack Start SPA**:
A modern single-page frontend application powered by TanStack Start router, Vite bundler, and React 19.
_Avoid_: Next.js app, Remix app, Vue app
"""
        sharpened = sharpen_domain_terms("Migrate this into a Next.js app with server components", context_content=context)
        self.assertTrue(any(s["canonical_term"] == "TanStack Start SPA" for s in sharpened))


class TestPromptArchetypeClassification(unittest.TestCase):
    """Test classification of user prompts into archetypes."""

    def test_classify_deletion_prompts(self):
        prompts = [
            "remove social media links like github, x.com, etc",
            "Delete the footer copyright banner",
            "strip out unused navigation items",
            "clean up dead links in sidebar",
            "prune external analytics script",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertEqual(classify_prompt_archetype(p), "deletion")

    def test_classify_styling_prompts(self):
        prompts = [
            "adjust dark mode colors for header",
            "update theme styling and padding",
            "change tailwind spacing on product cards",
            "fix mobile responsive layout",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertEqual(classify_prompt_archetype(p), "styling")

    def test_classify_component_modification_prompts(self):
        prompts = [
            "update footer copyright text",
            "modify Header title to Software Factory",
            "tweak user avatar display size",
            "replace search icon in navbar",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertEqual(classify_prompt_archetype(p), "component_modification")

    def test_classify_new_feature_prompts(self):
        prompts = [
            "build an inventory analytics overview dashboard",
            "create new route for checkout flow",
            "add user management page",
            "implement audit log table with pagination",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertEqual(classify_prompt_archetype(p), "new_feature")


class TestGrillingAssistantTurnProgression(unittest.IsolatedAsyncioTestCase):
    """Test GrillingAssistant turn handling in deterministic mock mode."""

    async def test_initial_turn_produces_grill_round_with_structured_questions(self):
        assistant = GrillingAssistant(mock=True)
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="Add an inventory analytics overview dashboard",
            history=[],
        )

        self.assertEqual(turn.type, "grill_round")
        self.assertEqual(turn.round, 1)
        self.assertGreaterEqual(len(turn.questions), 2)

        # Check structured question properties
        q1 = turn.questions[0]
        self.assertTrue(q1.id.startswith("Q"))
        self.assertTrue(len(q1.title) > 0)
        self.assertTrue(len(q1.question) > 0)
        self.assertTrue(len(q1.recommended) > 0)

        # Verify formatted markdown representation has question and recommended answer
        self.assertIn(f"❓ **{q1.id}**", turn.formatted_text)
        self.assertIn("➡️", turn.formatted_text)
        self.assertIn(q1.recommended, turn.formatted_text)

        # No draft ADR should be finalized in round 1
        self.assertIsNone(turn.draft_adr)

    async def test_subsequent_turn_with_answers_reaches_ready_for_approval_and_drafts_adr(self):
        assistant = GrillingAssistant(mock=True)
        history = [
            {"role": "user", "text": "Add an inventory analytics overview dashboard"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Route Placement**: Where should this route go?\n➡️ app/routes/analytics.tsx",
            },
        ]
        user_reply = "Accept recommended defaults and use local TanStack Query cache"

        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt=user_reply,
            history=history,
        )

        self.assertEqual(turn.type, "ready_for_approval")
        self.assertEqual(turn.round, 2)
        self.assertIsNotNone(turn.plan)
        self.assertIn("Implementation Plan", turn.plan)
        self.assertIsNotNone(turn.draft_adr)

        adr = turn.draft_adr
        self.assertIn("docs/adr/", adr.filename)
        self.assertTrue(adr.filename.endswith(".md"))
        self.assertTrue(len(adr.title) > 0)
        self.assertIn("Status**: Proposed", adr.content)
        self.assertIn("Considered Options", adr.content)
        self.assertIn("Consequences", adr.content)

    async def test_text_shortcut_proceed_immediately_reaches_ready_for_approval(self):
        assistant = GrillingAssistant(mock=True)
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="/proceed",
            history=[{"role": "user", "text": "Add simple status tag"}],
        )

        self.assertEqual(turn.type, "ready_for_approval")
        self.assertIsNotNone(turn.draft_adr)
        self.assertIsNotNone(turn.plan)

    async def test_deletion_prompt_generates_component_scoped_questions_without_routes(self):
        assistant = GrillingAssistant(mock=True)
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="remove social media links like github, x.com, etc",
            history=[],
        )

        self.assertEqual(turn.type, "grill_round")
        self.assertEqual(turn.round, 1)
        self.assertGreaterEqual(len(turn.questions), 2)
        question_titles = [q.title.lower() for q in turn.questions]
        self.assertTrue(any("component" in t or "scope" in t for t in question_titles))
        self.assertTrue(any("layout" in t or "spacing" in t or "reflow" in t for t in question_titles))
        for q in turn.questions:
            self.assertNotIn("app/routes/", q.recommended)
            self.assertNotIn("route tree", q.question.lower())

    async def test_deletion_prompt_ready_for_approval_omits_draft_adr(self):
        assistant = GrillingAssistant(mock=True)
        history = [
            {"role": "user", "text": "remove social media links like github, x.com, etc"},
            {
                "role": "assistant",
                "text": "❓ **Q1** - **Component Scope**: Which component contains the links?\n➡️ Target existing component.",
            },
        ]
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="Accept recommended defaults",
            history=history,
        )

        self.assertEqual(turn.type, "ready_for_approval")
        self.assertEqual(turn.round, 2)
        self.assertIsNotNone(turn.plan)
        self.assertIsNone(turn.draft_adr)
        self.assertNotIn("Draft ADR Ready", turn.formatted_text)

    async def test_component_modification_ready_for_approval_omits_draft_adr(self):
        assistant = GrillingAssistant(mock=True)
        history = [
            {"role": "user", "text": "update footer copyright year and company name"},
        ]
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="/proceed",
            history=history,
        )

        self.assertEqual(turn.type, "ready_for_approval")
        self.assertIsNotNone(turn.plan)
        self.assertIsNone(turn.draft_adr)
        self.assertNotIn("Draft ADR Ready", turn.formatted_text)

    async def test_styling_ready_for_approval_omits_draft_adr(self):
        assistant = GrillingAssistant(mock=True)
        history = [
            {"role": "user", "text": "adjust header padding and dark mode colors"},
        ]
        turn = await assistant.handle_turn(
            repo="inventory-tracker",
            prompt="/proceed",
            history=history,
        )

        self.assertEqual(turn.type, "ready_for_approval")
        self.assertIsNotNone(turn.plan)
        self.assertIsNone(turn.draft_adr)
        self.assertNotIn("Draft ADR Ready", turn.formatted_text)


class TestLiveOpenCodeGoInteraction(unittest.IsolatedAsyncioTestCase):
    """Test GrillingAssistant remote interaction with OpenCode Go inference API."""

    async def test_live_turn_parses_remote_json_grill_round(self):
        remote_response_json = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Clarifying data model",
                            "questions": [
                                {
                                    "id": "Q1",
                                    "title": "Data Schema",
                                    "question": "What fields are required for inventory items?",
                                    "recommended": "SKU, title, quantity, and unit price",
                                    "options": ["SKU, title, quantity", "SKU, title, quantity, and unit price"],
                                }
                            ],
                        })
                    }
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_response_json
        mock_resp.raise_for_status = MagicMock()

        assistant = GrillingAssistant(api_key="live-opencode-key", mock=False)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )

            self.assertEqual(turn.type, "grill_round")
            self.assertEqual(turn.round, 1)
            self.assertEqual(len(turn.questions), 1)
            self.assertEqual(turn.questions[0].id, "Q1")
            self.assertEqual(turn.questions[0].recommended, "SKU, title, quantity, and unit price")
            self.assertIn("❓ **Q1**", turn.formatted_text)

    async def test_live_turn_handles_markdown_wrapped_json(self):
        wrapped_content = "```json\n" + json.dumps({
            "type": "ready_for_approval",
            "round": 2,
            "summary": "Plan ready",
            "plan": "# Final Plan\nBuild the features.",
            "draft_adr": {
                "title": "0002: In-Memory Client Inventory Cache",
                "filename": "docs/adr/0002-in-memory-client-inventory-cache.md",
                "content": "# 0002...",
            },
        }) + "\n```"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": wrapped_content}}]}
        mock_resp.raise_for_status = MagicMock()

        assistant = GrillingAssistant(api_key="live-opencode-key", mock=False)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Looks good",
                history=[{"role": "user", "text": "create items"}],
            )

            self.assertEqual(turn.type, "ready_for_approval")
            self.assertIsNotNone(turn.draft_adr)
            self.assertEqual(turn.draft_adr.filename, "docs/adr/0002-in-memory-client-inventory-cache.md")

    async def test_live_turn_supports_null_draft_adr_during_ready_for_approval(self):
        remote_response_json = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "ready_for_approval",
                            "round": 2,
                            "summary": "Plan ready for removing social media links",
                            "plan": "# Final Plan\nRemove social links from Footer.tsx.",
                            "draft_adr": None,
                        })
                    }
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_response_json
        mock_resp.raise_for_status = MagicMock()

        assistant = GrillingAssistant(api_key="live-opencode-key", mock=False)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Accept defaults",
                history=[{"role": "user", "text": "remove social media links like github, x.com, etc"}],
            )

            self.assertEqual(turn.type, "ready_for_approval")
            self.assertIsNotNone(turn.plan)
            self.assertIsNone(turn.draft_adr)
            self.assertNotIn("Draft ADR Ready", turn.formatted_text)
            self.assertNotIn("docs/adr/", turn.formatted_text)
            serialized = turn.to_dict()
            self.assertIsNone(serialized["draft_adr"])

    async def test_live_turn_system_instruction_enforces_conditional_adr_policy(self):
        assistant = GrillingAssistant(api_key="live-opencode-key", mock=False)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Round 1",
                            "questions": [],
                        })
                    }
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="remove social media links",
                history=[],
            )

            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            system_instruction = called_payload["messages"][0]["content"]

            # Must instruct conditional ADR policy
            self.assertIn("Offer ADRs sparingly", system_instruction)
            self.assertIn("draft_adr", system_instruction)
            self.assertIn("null", system_instruction.lower())

    async def test_live_turn_targets_canonical_endpoint_and_headers(self):
        remote_response_json = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Clarifying scope",
                            "questions": [],
                        })
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_response_json
        mock_resp.raise_for_status = MagicMock()

        assistant = GrillingAssistant(api_key="test-key-abc", mock=False)
        self.assertEqual(assistant.base_url, "https://opencode.ai/zen/go/v1")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )

            mock_post.assert_called_once()
            called_url = mock_post.call_args[0][0]
            called_headers = mock_post.call_args[1]["headers"]
            self.assertEqual(called_url, "https://opencode.ai/zen/go/v1/chat/completions")
            self.assertEqual(called_headers["Authorization"], "Bearer test-key-abc")
            self.assertEqual(called_headers["Content-Type"], "application/json")
            self.assertEqual(called_headers["x-opencode-session"], "studio-inventory-tracker")

    async def test_remote_failure_returns_error_turn_instead_of_silent_mock(self):
        assistant = GrillingAssistant(api_key="live-opencode-key", mock=False)

        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused to opencode.ai")):
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )

            self.assertEqual(turn.type, "error")
            self.assertEqual(turn.round, 1)
            self.assertIn("Connection refused", turn.error_message)
            self.assertIsNotNone(turn.error_details)
            self.assertIn("OpenCode Go", turn.error_details)

    async def test_http_status_error_returns_error_turn_with_diagnostics(self):
        assistant = GrillingAssistant(api_key="invalid_test_key_1234", mock=False)

        fake_req = httpx.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions")
        fake_resp = httpx.Response(status_code=401, text="Unauthorized: Invalid API key", request=fake_req)
        err = httpx.HTTPStatusError("Client error 401", request=fake_req, response=fake_resp)

        with patch("httpx.AsyncClient.post", side_effect=err):
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )

            self.assertEqual(turn.type, "error")
            self.assertIn("401", turn.error_message)
            self.assertIn("Unauthorized", turn.error_message)
            self.assertIn("Endpoint:", turn.error_details)

    async def test_missing_api_key_without_explicit_mock_returns_error_turn(self):
        with patch("factory.ui.grill.resolve_opencode_go_api_key", return_value=None):
            assistant = GrillingAssistant(api_key=None, mock=False)
            self.assertFalse(assistant.is_mock_mode)

            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )

            self.assertEqual(turn.type, "error")
            self.assertIn("OpenCode Credentials", turn.error_message)
            self.assertIn("not configured", turn.error_message)

    async def test_invalid_token_format_returns_error_turn_before_network_call(self):
        assistant = GrillingAssistant(api_key="bad key with spaces", mock=False)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )
            mock_post.assert_not_called()
            self.assertEqual(turn.type, "error")
            self.assertIn("Invalid OpenCode Credentials format", turn.error_message)

    async def test_error_turns_in_history_do_not_increment_round_counter_or_pollute_llm_messages(self):
        assistant = GrillingAssistant(api_key="oc_live_valid_token_123", mock=False)

        history = [
            {"role": "user", "text": "Add inventory CRUD"},
            {"role": "assistant", "text": "⚠️ **Inference Error**: Connection refused", "type": "error"},
        ]

        remote_resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "type": "grill_round",
                            "round": 1,
                            "summary": "Round 1 questions",
                            "questions": [],
                        })
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_resp
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Retry adding inventory CRUD",
                history=history,
            )

            self.assertEqual(turn.type, "grill_round")
            self.assertEqual(turn.round, 1)

            # Check that the error message was excluded from the payload sent to OpenCode Go
            called_payload = mock_post.call_args[1]["json"]
            sent_contents = [m["content"] for m in called_payload["messages"]]
            self.assertFalse(any("⚠️ **Inference Error**" in c for c in sent_contents))

    async def test_explicit_mock_mode_does_not_call_remote_endpoint(self):
        assistant = GrillingAssistant(api_key=None, mock=True)
        self.assertTrue(assistant.is_mock_mode)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            turn = await assistant.handle_turn(
                repo="inventory-tracker",
                prompt="Add inventory CRUD",
                history=[],
            )
            mock_post.assert_not_called()
            self.assertEqual(turn.type, "grill_round")


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






