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
