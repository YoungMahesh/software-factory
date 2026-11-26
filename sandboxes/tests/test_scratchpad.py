"""Unit and API tests for the Sandbox Web Dashboard Scratchpad module."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.function import OPENCODE_INSTALL_COMMANDS, image as control_plane_image
from sandbox.scratchpad import (
    FREE_SCRATCHPAD_MODELS,
    ScratchpadNoteDetail,
    ScratchpadNoteSummary,
    ScratchpadSaveResult,
    ScratchpadSuggestion,
    commit_scratchpad_note,
    extract_title_from_markdown,
    list_scratchpad_notes,
    normalize_note_markdown,
    read_scratchpad_note,
    resolve_unique_slug,
    set_scratchpad_overrides,
    slugify_title,
    suggest_scratchpad_note,
    validate_note_filename,
)
from sandbox.web import app


class TestScratchpadHelpers(unittest.TestCase):
    """Tests slugification, collision disambiguation, and Markdown formatting."""

    def test_slugify_title_kebab_case_and_fallback(self):
        self.assertEqual(slugify_title("Auth Middleware Plan!"), "auth-middleware-plan")
        self.assertEqual(slugify_title("  Café — API v2 / Sync  "), "cafe-api-v2-sync")
        self.assertEqual(slugify_title("---"), "untitled-note")
        self.assertLessEqual(len(slugify_title("word " * 40)), 80)

    def test_resolve_unique_slug_disambiguates_collisions(self):
        self.assertEqual(resolve_unique_slug("My Idea", []), ("my-idea", "my-idea.md"))
        self.assertEqual(
            resolve_unique_slug("My Idea", ["my-idea.md"]),
            ("my-idea-2", "my-idea-2.md"),
        )
        self.assertEqual(
            resolve_unique_slug("My Idea", ["MY-IDEA.md", "my-idea-2.md"]),
            ("my-idea-3", "my-idea-3.md"),
        )

    def test_validate_note_filename_rejects_traversal(self):
        self.assertEqual(validate_note_filename("my-note-2.md"), "my-note-2.md")
        for bad in ("../secret.md", "sub/note.md", ".gitkeep", "UPPER.md", "note.txt", ""):
            with self.assertRaises(ValueError):
                validate_note_filename(bad)

    def test_normalize_note_markdown_sets_h1_heading(self):
        md = normalize_note_markdown("Auth Plan", "# Old Heading\n\n## Goals\n- Fast")
        self.assertEqual(md, "# Auth Plan\n\n## Goals\n- Fast\n")
        self.assertEqual(extract_title_from_markdown(md, "fallback.md"), "Auth Plan")
        self.assertEqual(extract_title_from_markdown("No heading here", "my-draft.md"), "My Draft")


class TestScratchpadOpenCodeBackend(unittest.TestCase):
    """Tests keyless free OpenCode CLI invocation and model fallback."""

    @patch("sandbox.scratchpad._ai.resolve_opencode_binary", return_value="/usr/local/bin/opencode")
    @patch("sandbox.scratchpad._ai.subprocess.run")
    def test_suggest_uses_isolated_home_strips_paid_keys_and_falls_back(self, mock_run, _mock_bin):
        good_ndjson = "\n".join(
            [
                json.dumps({"type": "step_start"}),
                json.dumps(
                    {
                        "type": "text",
                        "part": {
                            "text": '```json\n{"title": "Queue Worker Plan", "content": "# Duplicate\\n\\n## Summary\\nRun jobs."}\n```'
                        },
                    }
                ),
                json.dumps({"type": "step_finish"}),
            ]
        )
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, "", "rate limit"),
            subprocess.CompletedProcess([], 0, good_ndjson, ""),
        ]

        with patch.dict(
            os.environ,
            {"OPENCODE_API_KEY": "paid", "OPENCODE_GO_API_KEY": "go-paid"},
            clear=False,
        ):
            suggestion = suggest_scratchpad_note("build a queue worker for webhooks")

        self.assertEqual(suggestion.title, "Queue Worker Plan")
        self.assertEqual(suggestion.content, "## Summary\nRun jobs.")
        self.assertEqual(suggestion.model, FREE_SCRATCHPAD_MODELS[1])
        self.assertEqual(mock_run.call_count, 2)

        for call in mock_run.call_args_list:
            env = call.kwargs["env"]
            self.assertNotIn("OPENCODE_API_KEY", env)
            self.assertNotIn("OPENCODE_GO_API_KEY", env)
            self.assertEqual(env["OPENCODE_CONFIG_CONTENT"], '{"mcp":{},"lsp":false}')

    @patch("sandbox.scratchpad._ai.resolve_opencode_binary", return_value="/usr/local/bin/opencode")
    @patch("sandbox.scratchpad._ai.subprocess.run", side_effect=RuntimeError("boom"))
    def test_suggest_raises_when_all_free_models_fail(self, _mock_run, _mock_bin):
        with self.assertRaises(RuntimeError) as ctx:
            suggest_scratchpad_note("rough note")
        self.assertIn("All free OpenCode models failed", str(ctx.exception))


class TestScratchpadGitHubPersistence(unittest.TestCase):
    """Tests config/scratchpad GitHub Contents API read/list/commit helpers."""

    @patch("sandbox.config_store.github_json_request")
    def test_list_and_read_scratchpad_notes(self, mock_req):
        encoded = base64.b64encode(b"# Webhook Plan\n\n## Steps\n- Retry\n").decode("ascii")
        mock_req.side_effect = [
            (
                200,
                [
                    {"type": "file", "name": ".gitkeep", "path": "scratchpad/.gitkeep", "sha": "s0", "size": 0},
                    {"type": "file", "name": "webhook-plan.md", "path": "scratchpad/webhook-plan.md", "sha": "s1", "size": 34, "html_url": "https://github.com/org/config/blob/main/scratchpad/webhook-plan.md"},
                ],
            ),
            (
                200,
                {
                    "path": "scratchpad/webhook-plan.md",
                    "sha": "s1",
                    "content": encoded,
                    "html_url": "https://github.com/org/config/blob/main/scratchpad/webhook-plan.md",
                },
            ),
        ]

        notes = list_scratchpad_notes("sFactory0", "tok")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].filename, "webhook-plan.md")
        self.assertEqual(notes[0].title, "Webhook Plan")

        detail = read_scratchpad_note("sFactory0", "webhook-plan.md", "tok")
        self.assertEqual(detail.title, "Webhook Plan")
        self.assertIn("## Steps", detail.content)

    @patch("sandbox.config_store.github_json_request")
    def test_commit_scratchpad_note_handles_collision_and_422_retry(self, mock_req):
        mock_req.side_effect = [
            (200, [{"type": "file", "name": "my-idea.md", "path": "scratchpad/my-idea.md", "sha": "s1", "size": 10}]),
            (422, {"message": "sha wasn't supplied"}),
            (200, [
                {"type": "file", "name": "my-idea.md", "path": "scratchpad/my-idea.md", "sha": "s1", "size": 10},
                {"type": "file", "name": "my-idea-2.md", "path": "scratchpad/my-idea-2.md", "sha": "s2", "size": 10},
            ]),
            (201, {"content": {"path": "scratchpad/my-idea-3.md", "sha": "s3", "html_url": "https://gh/3"}}),
        ]

        saved = commit_scratchpad_note("sFactory0", title="My Idea", content="Body", token="tok")
        self.assertEqual(saved.filename, "my-idea-3.md")
        self.assertEqual(saved.path, "scratchpad/my-idea-3.md")
        self.assertEqual(saved.content, "# My Idea\n\nBody\n")
        self.assertGreater(saved.size, 0)

    @patch("sandbox.config_store.github_json_request")
    def test_commit_scratchpad_note_advances_taken_slugs_even_with_stale_list(self, mock_req):
        stale_list = [{"type": "file", "name": "dup.md", "path": "scratchpad/dup.md", "sha": "s1", "size": 5}]
        mock_req.side_effect = [
            (200, stale_list),
            (422, {"message": "sha wasn't supplied"}),
            (200, stale_list),
            (422, {"message": "sha wasn't supplied"}),
            (200, stale_list),
            (201, {"content": {"path": "scratchpad/dup-4.md", "sha": "s4", "size": 18, "html_url": "https://gh/4"}}),
        ]

        saved = commit_scratchpad_note("sFactory0", title="Dup", content="Body", token="tok")
        self.assertEqual(saved.filename, "dup-4.md")
        self.assertEqual(saved.size, 18)


class TestScratchpadAPI(unittest.TestCase):
    """Tests authenticated /api/scratchpad FastAPI endpoints and control plane image."""

    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {"WEB_UI_USERNAME": "testadmin", "WEB_UI_PASSWORD": "testpassword"},
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})
        self.unauth_client = TestClient(app)

    def tearDown(self):
        set_scratchpad_overrides()
        self.env_patcher.stop()

    def test_requires_basic_auth(self):
        self.assertEqual(self.unauth_client.get("/api/scratchpad/notes").status_code, 401)
        self.assertEqual(self.unauth_client.post("/api/scratchpad/suggest", json={"raw_text": "hi"}).status_code, 401)

    def test_suggest_list_read_and_commit_flow(self):
        committed: list[dict] = []

        def fake_list(_owner, _token):
            return [
                ScratchpadNoteSummary(
                    filename="queue-worker.md",
                    slug="queue-worker",
                    path="scratchpad/queue-worker.md",
                    title="Queue Worker",
                    sha="sha1",
                    size=42,
                )
            ]

        def fake_read(_owner, filename, _token):
            if filename == "queue-worker.md":
                return ScratchpadNoteDetail(
                    filename="queue-worker.md",
                    slug="queue-worker",
                    path="scratchpad/queue-worker.md",
                    title="Queue Worker",
                    content="# Queue Worker\n\n## Details\n- Process jobs\n",
                    sha="sha1",
                )
            raise FileNotFoundError("not found")

        def fake_suggest(raw_text, **_kwargs):
            return ScratchpadSuggestion(
                title="Queue Worker",
                content=f"## Overview\n{raw_text}\n",
                model="opencode/mimo-v2.6-flash-free",
            )

        def fake_commit(_owner, *, title, content, _token=None, **_kwargs):
            committed.append({"title": title, "content": content})
            return ScratchpadSaveResult(
                filename="queue-worker-2.md",
                slug="queue-worker-2",
                path="scratchpad/queue-worker-2.md",
                title=title,
                sha="sha2",
                content=normalize_note_markdown(title, content),
                html_url="https://github.com/sFactory0/config/blob/main/scratchpad/queue-worker-2.md",
            )

        set_scratchpad_overrides(
            context_fn=lambda: ("sFactory0", "ghp_test"),
            list_notes_fn=fake_list,
            read_note_fn=fake_read,
            suggest_fn=fake_suggest,
            commit_note_fn=lambda owner, *, title, content, token: fake_commit(owner, title=title, content=content),
        )

        # Empty suggest -> 400
        self.assertEqual(self.client.post("/api/scratchpad/suggest", json={"raw_text": "   "}).status_code, 400)

        # Suggest accounts for existing queue-worker.md -> queue-worker-2.md
        suggest_resp = self.client.post("/api/scratchpad/suggest", json={"raw_text": "retry queue"})
        self.assertEqual(suggest_resp.status_code, 200)
        sdata = suggest_resp.json()
        self.assertEqual(sdata["filename"], "queue-worker-2.md")
        self.assertEqual(sdata["target_path"], "scratchpad/queue-worker-2.md")
        self.assertEqual(sdata["model"], "opencode/mimo-v2.6-flash-free")

        # List & read
        list_resp = self.client.get("/api/scratchpad/notes")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.headers.get("cache-control"), "no-store")
        self.assertEqual(list_resp.json()["config_repo"], "sFactory0/config")
        self.assertEqual(len(list_resp.json()["notes"]), 1)

        read_resp = self.client.get("/api/scratchpad/notes/queue-worker.md")
        self.assertEqual(read_resp.status_code, 200)
        self.assertEqual(read_resp.json()["title"], "Queue Worker")

        self.assertEqual(self.client.get("/api/scratchpad/notes/missing.md").status_code, 404)
        self.assertEqual(self.client.get("/api/scratchpad/notes/BAD_FILE").status_code, 400)

        # Commit accepted note
        save_resp = self.client.post(
            "/api/scratchpad/notes",
            json={"title": "Queue Worker", "content": "## Overview\nRetry queue", "mode": "ai"},
        )
        self.assertEqual(save_resp.status_code, 201)
        self.assertEqual(save_resp.json()["path"], "scratchpad/queue-worker-2.md")
        self.assertEqual(len(committed), 1)

        # Commit raw note without title auto-derives title
        raw_resp = self.client.post(
            "/api/scratchpad/notes",
            json={"title": "", "content": "Quick raw brainstorm", "mode": "raw"},
        )
        self.assertEqual(raw_resp.status_code, 201)
        self.assertEqual(committed[1]["title"], "Quick raw brainstorm")

    def test_dashboard_html_exposes_scratchpad_tab_and_image_installs_opencode(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Scratchpad", resp.text)
        self.assertIn("/api/scratchpad/suggest", resp.text)
        self.assertIn("scratchpadModalOpen", resp.text)
        self.assertTrue(any("opencode.ai/v2/install" in cmd for cmd in OPENCODE_INSTALL_COMMANDS))

        def _deps(obj):
            yield obj
            if hasattr(obj, "_deps_"):
                for d in obj._deps_():
                    yield from _deps(d)

        dep_reprs = "\n".join(repr(d) for d in _deps(control_plane_image))
        self.assertIn("apt_install", dep_reprs)
        self.assertIn("run_commands", dep_reprs)
        func_source = (
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox", "function.py")
        )
        with open(func_source, encoding="utf-8") as fp:
            src_text = fp.read()
        self.assertIn("ca-certificates", src_text)
        self.assertIn("*OPENCODE_INSTALL_COMMANDS", src_text)


if __name__ == "__main__":
    unittest.main()
