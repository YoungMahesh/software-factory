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



