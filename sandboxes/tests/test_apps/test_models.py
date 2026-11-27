"""Tests for Factory App domain models, slugging, URL building, and prompt framing."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from sandbox.apps import (
    DEFAULT_BUILDER_MODEL,
    DEFAULT_BUILDER_PROVIDER,
    CreateAppPayload,
    build_direct_chat_url,
    build_initial_thread_prompt,
    derive_app_slug,
    derive_app_title,
)


class TestAppModels(unittest.TestCase):
    def test_create_app_payload_defaults_and_blank_prompt_rejected(self):
        payload = CreateAppPayload(prompt="  Build a personal expense tracker  ")
        self.assertEqual(payload.prompt, "Build a personal expense tracker")
        self.assertEqual(payload.template, "nextjs")
        self.assertFalse(payload.mobile_app)
        self.assertTrue(payload.vm)
        self.assertEqual(payload.memory, 1)
        self.assertTrue(payload.t3)
        self.assertTrue(payload.modal)
        self.assertTrue(payload.sops)
        self.assertTrue(payload.no_cloudflare)
        self.assertEqual(payload.provider, DEFAULT_BUILDER_PROVIDER)
        self.assertEqual(payload.model, DEFAULT_BUILDER_MODEL)
        self.assertIsNone(payload.thought_level)

        with self.assertRaises(ValidationError):
            CreateAppPayload(prompt="   \n  ")

    def test_derive_app_slug_from_prompt_and_explicit_name(self):
        self.assertEqual(
            derive_app_slug("Build a Kanban board with drag & drop!"),
            "build-a-kanban-board-with",
        )
        self.assertEqual(
            derive_app_slug("anything", explicit_name="My Cool App 2!"),
            "my-cool-app-2",
        )
        self.assertEqual(
            derive_app_slug("123 numbers first"),
            "app-123-numbers-first",
        )

    def test_derive_app_slug_disambiguates_collisions(self):
        slug = derive_app_slug(
            "Build a todo app",
            explicit_name="todo-app",
            existing_slugs={"todo-app", "todo-app-2"},
        )
        self.assertEqual(slug, "todo-app-3")
        self.assertLessEqual(len(slug), 42)

    def test_derive_app_title_uses_first_line_and_truncates(self):
        self.assertEqual(
            derive_app_title("Habit tracker\nWith daily streaks"),
            "Habit tracker",
        )
        long_prompt = "A " + ("very " * 20) + "long prompt"
        title = derive_app_title(long_prompt)
        self.assertLessEqual(len(title), 60)
        self.assertTrue(title.endswith("..."))

    def test_build_initial_thread_prompt_appends_run_app_without_mutating_raw(self):
        raw = "Build a Pomodoro timer"
        nextjs_msg = build_initial_thread_prompt(raw, template="nextjs", app_dir="/root/pomodoro")
        self.assertTrue(nextjs_msg.startswith(raw))
        self.assertIn("pnpm run dev", nextjs_msg)
        self.assertIn("T3 Code browser", nextjs_msg)
        self.assertIn("/root/pomodoro", nextjs_msg)

        blank_msg = build_initial_thread_prompt(raw, template="blank", app_dir="/root/pomodoro")
        self.assertTrue(blank_msg.startswith(raw))
        self.assertIn("T3 Code browser", blank_msg)
        self.assertNotIn("pnpm run dev", blank_msg)

    def test_build_direct_chat_url_percent_encodes_thread_id_and_attaches_token(self):
        url = build_direct_chat_url(
            "https://ta-xyz-3775.w.modal.host/",
            "env:abc/1",
            "thread:2d2e115c-1ee0",
            token="tok_123+abc",
        )
        self.assertEqual(
            url,
            "https://ta-xyz-3775.w.modal.host/env%3Aabc%2F1/thread%3A2d2e115c-1ee0#token=tok_123%2Babc",
        )

        no_tok = build_direct_chat_url(
            "https://ta-xyz-3775.w.modal.host",
            "local-env",
            "thread:123",
        )
        self.assertEqual(no_tok, "https://ta-xyz-3775.w.modal.host/local-env/thread%3A123")
