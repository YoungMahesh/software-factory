"""Unit and API tests for the Sandbox Web Dashboard Scratchpad module."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.apps import FactoryStateStore
from sandbox.function import OPENCODE_INSTALL_COMMANDS, image as control_plane_image
from sandbox.scratchpad import (
    FREE_SCRATCHPAD_MODELS,
    ScratchpadNoteDetail,
    ScratchpadNoteSummary,
    ScratchpadSaveResult,
    ScratchpadSuggestion,
    commit_scratchpad_note,
    derive_title_from_body,
    extract_title_from_markdown,
    list_all_scratchpad_notes,
    list_scratchpad_notes,
    normalize_note_markdown,
    read_scratchpad_note,
    resolve_section_dir,
    resolve_unique_slug,
    set_scratchpad_overrides,
    slugify_title,
    suggest_scratchpad_note,
    validate_note_filename,
)
from sandbox.web import app


class TestScratchpadHelpers(unittest.TestCase):
    """Tests slugification, section validation, collision disambiguation, and Markdown formatting."""

    def test_slugify_title_kebab_case_and_fallback(self):
        self.assertEqual(slugify_title("Auth Middleware Plan!"), "auth-middleware-plan")
        self.assertEqual(slugify_title("  Café — API v2 / Sync  "), "cafe-api-v2-sync")
        self.assertEqual(slugify_title("---"), "untitled-note")
        self.assertLessEqual(len(slugify_title("word " * 40)), 80)

    def test_resolve_section_dir_and_derive_title(self):
        self.assertEqual(resolve_section_dir("ideas"), ("ideas", "scratchpad"))
        self.assertEqual(resolve_section_dir("raw"), ("raw", "raw"))
        with self.assertRaises(ValueError):
            resolve_section_dir("other")
        self.assertEqual(derive_title_from_body("\n# Quick   Draft   Line one two three four five six"), "Quick Draft Line one two three four")
        self.assertEqual(derive_title_from_body("   \n  "), "Untitled Note")

    def test_resolve_unique_slug_disambiguates_collisions(self):
        self.assertEqual(resolve_unique_slug("My Idea", []), ("my-idea", "my-idea.md"))
        self.assertEqual(resolve_unique_slug("My Idea", ["my-idea.md"]), ("my-idea-2", "my-idea-2.md"))
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
    """Tests config/scratchpad and config/raw GitHub Contents API read/list/commit helpers."""

    @patch("sandbox.config_store.github_json_request")
    def test_list_and_read_ideas_and_raw_sections(self, mock_req):
        idea_b64 = base64.b64encode(b"# Webhook Plan\n\n## Steps\n- Retry\n").decode("ascii")
        raw_text = "# Raw Heading Inside Paste\n  indented line\n"
        raw_b64 = base64.b64encode(raw_text.encode("utf-8")).decode("ascii")
        mock_req.side_effect = [
            (200, [{"type": "file", "name": "webhook-plan.md", "path": "scratchpad/webhook-plan.md", "sha": "s1", "size": 34}]),
            (200, [{"type": "file", "name": "raw-log.md", "path": "raw/raw-log.md", "sha": "r1", "size": 42}]),
            (200, {"path": "scratchpad/webhook-plan.md", "sha": "s1", "content": idea_b64}),
            (200, {"path": "raw/raw-log.md", "sha": "r1", "content": raw_b64}),
        ]

        ideas, raw = list_all_scratchpad_notes("sFactory0", "tok")
        self.assertEqual(ideas[0].section, "ideas")
        self.assertEqual(ideas[0].path, "scratchpad/webhook-plan.md")
        self.assertEqual(raw[0].section, "raw")
        self.assertEqual(raw[0].path, "raw/raw-log.md")

        idea_detail = read_scratchpad_note("sFactory0", "webhook-plan.md", "tok", section="ideas")
        self.assertEqual(idea_detail.title, "Webhook Plan")

        raw_detail = read_scratchpad_note("sFactory0", "raw-log.md", "tok", section="raw")
        self.assertEqual(raw_detail.title, "Raw Log")
        self.assertEqual(raw_detail.content, raw_text)

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
        self.assertEqual(saved.section, "ideas")
        self.assertEqual(saved.filename, "my-idea-3.md")
        self.assertEqual(saved.path, "scratchpad/my-idea-3.md")
        self.assertEqual(saved.content, "# My Idea\n\nBody\n")

    @patch("sandbox.config_store.github_json_request")
    def test_commit_raw_note_writes_verbatim_utf8_to_raw_dir(self, mock_req):
        raw_payload = "\n# Keep Exact Heading\n  line 2 without trailing newline"
        mock_req.side_effect = [
            (200, []),
            (201, {"content": {"path": "raw/my-raw-note.md", "sha": "r9", "size": len(raw_payload), "html_url": "https://gh/raw"}}),
        ]

        saved = commit_scratchpad_note("sFactory0", title="My Raw Note", content=raw_payload, token="tok", section="raw")
        self.assertEqual(saved.section, "raw")
        self.assertEqual(saved.path, "raw/my-raw-note.md")
        self.assertEqual(saved.content, raw_payload)

        put_url, _token = mock_req.call_args_list[1].args
        put_payload = mock_req.call_args_list[1].kwargs["payload"]
        self.assertIn("/contents/raw/my-raw-note.md", put_url)
        self.assertEqual(put_payload["message"], "chore(raw): add my-raw-note.md")
        self.assertEqual(base64.b64decode(put_payload["content"]).decode("utf-8"), raw_payload)


class TestScratchpadAPI(unittest.TestCase):
    """Tests authenticated /api/scratchpad endpoints, Volume caching, and UI markers."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = FactoryStateStore(root_dir=Path(self.tmpdir.name))
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
        self.tmpdir.cleanup()

    def test_requires_basic_auth(self):
        self.assertEqual(self.unauth_client.get("/api/scratchpad/notes").status_code, 401)
        self.assertEqual(self.unauth_client.post("/api/scratchpad/notes/refresh").status_code, 401)
        self.assertEqual(self.unauth_client.post("/api/scratchpad/suggest", json={"raw_text": "hi"}).status_code, 401)

    def test_cached_catalog_manual_refresh_lazy_reads_and_direct_raw_commit(self):
        remote_ideas = {
            "queue-worker.md": ("sha1", "# Queue Worker\n\n## Details\n- Process jobs\n"),
        }
        remote_raw = {
            "vps-dump.md": ("raw-sha1", "  raw line 1\n# raw h1 untouched"),
        }
        list_mock = MagicMock()
        read_mock = MagicMock()
        suggest_mock = MagicMock(
            return_value=ScratchpadSuggestion(
                title="Queue Worker",
                content="## Overview\nRetry queue\n",
                model="opencode/mimo-v2.6-flash-free",
            )
        )
        commit_calls: list[dict] = []

        def fake_list(_owner, _token, *, section="ideas"):
            if section == "ideas":
                return [
                    ScratchpadNoteSummary(
                        section="ideas",
                        filename=fname,
                        slug=fname[:-3],
                        path=f"scratchpad/{fname}",
                        title="Queue Worker",
                        sha=sha,
                        size=len(body),
                    )
                    for fname, (sha, body) in remote_ideas.items()
                ]
            return [
                ScratchpadNoteSummary(
                    section="raw",
                    filename=fname,
                    slug=fname[:-3],
                    path=f"raw/{fname}",
                    title="Vps Dump",
                    sha=sha,
                    size=len(body),
                )
                for fname, (sha, body) in remote_raw.items()
            ]

        def fake_read(_owner, filename, _token, *, section="ideas"):
            store_map = remote_ideas if section == "ideas" else remote_raw
            directory = "scratchpad" if section == "ideas" else "raw"
            if filename not in store_map:
                raise FileNotFoundError("not found")
            sha, body = store_map[filename]
            title = "Queue Worker" if section == "ideas" else "Vps Dump"
            return ScratchpadNoteDetail(
                section=section,
                filename=filename,
                slug=filename[:-3],
                path=f"{directory}/{filename}",
                title=title,
                content=body,
                sha=sha,
            )

        def fake_commit(_owner, *, title, content, token, section="ideas"):
            commit_calls.append({"title": title, "content": content, "section": section})
            if section == "ideas":
                return ScratchpadSaveResult(
                    section="ideas",
                    filename="queue-worker-2.md",
                    slug="queue-worker-2",
                    path="scratchpad/queue-worker-2.md",
                    title=title,
                    sha="sha2",
                    content=normalize_note_markdown(title, content),
                    html_url="https://github.com/sFactory0/config/blob/main/scratchpad/queue-worker-2.md",
                )
            return ScratchpadSaveResult(
                section="raw",
                filename="quick-raw-brainstorm.md",
                slug="quick-raw-brainstorm",
                path="raw/quick-raw-brainstorm.md",
                title=title,
                sha="raw-sha2",
                content=content,
                html_url="https://github.com/sFactory0/config/blob/main/raw/quick-raw-brainstorm.md",
            )

        list_mock.side_effect = fake_list
        read_mock.side_effect = fake_read

        set_scratchpad_overrides(
            context_fn=lambda: ("sFactory0", "ghp_test"),
            store_fn=lambda: self.store,
            list_notes_fn=list_mock,
            read_note_fn=read_mock,
            suggest_fn=suggest_mock,
            commit_note_fn=fake_commit,
        )

        # 1. GET never calls GitHub when cache is empty
        empty_resp = self.client.get("/api/scratchpad/notes")
        self.assertEqual(empty_resp.status_code, 200)
        self.assertEqual(empty_resp.headers.get("cache-control"), "no-store")
        self.assertEqual(empty_resp.json()["config_repo"], "sFactory0/config")
        self.assertIsNone(empty_resp.json()["refreshed_at"])
        self.assertEqual(empty_resp.json()["ideas"], [])
        self.assertEqual(empty_resp.json()["raw"], [])
        list_mock.assert_not_called()

        # 2. POST /notes/refresh fetches both sections and persists cache
        refresh_resp = self.client.post("/api/scratchpad/notes/refresh")
        self.assertEqual(refresh_resp.status_code, 200)
        rdata = refresh_resp.json()
        self.assertIsNotNone(rdata["refreshed_at"])
        self.assertEqual([n["path"] for n in rdata["ideas"]], ["scratchpad/queue-worker.md"])
        self.assertEqual([n["path"] for n in rdata["raw"]], ["raw/vps-dump.md"])
        self.assertEqual(list_mock.call_count, 2)

        # 3. Subsequent GET serves strictly from cache (0 GitHub calls)
        cached_resp = self.client.get("/api/scratchpad/notes")
        self.assertEqual(len(cached_resp.json()["ideas"]), 1)
        self.assertEqual(len(cached_resp.json()["raw"]), 1)
        self.assertEqual(list_mock.call_count, 2)

        # 4. Reading a note fetches once on cache miss, then serves cached body on repeat clicks
        first_read = self.client.get("/api/scratchpad/notes/vps-dump.md?section=raw")
        self.assertEqual(first_read.status_code, 200)
        self.assertEqual(first_read.json()["content"], "  raw line 1\n# raw h1 untouched")
        self.assertEqual(read_mock.call_count, 1)

        second_read = self.client.get("/api/scratchpad/notes/vps-dump.md?section=raw")
        self.assertEqual(second_read.status_code, 200)
        self.assertEqual(read_mock.call_count, 1)

        # 5. Refresh with unchanged SHA keeps cached body; changed SHA invalidates & re-fetches
        self.client.post("/api/scratchpad/notes/refresh")
        self.client.get("/api/scratchpad/notes/vps-dump.md?section=raw")
        self.assertEqual(read_mock.call_count, 1)

        remote_raw["vps-dump.md"] = ("raw-sha1-v2", "updated raw content")
        self.client.post("/api/scratchpad/notes/refresh")
        updated_read = self.client.get("/api/scratchpad/notes/vps-dump.md?section=raw")
        self.assertEqual(updated_read.json()["content"], "updated raw content")
        self.assertEqual(read_mock.call_count, 2)

        # 6. Validation errors
        self.assertEqual(self.client.get("/api/scratchpad/notes/missing.md?section=ideas").status_code, 404)
        self.assertEqual(self.client.get("/api/scratchpad/notes/BAD_FILE").status_code, 400)
        self.assertEqual(self.client.post("/api/scratchpad/suggest", json={"raw_text": "   "}).status_code, 400)

        # 7. Suggest (Ideas only) detects collision from list
        suggest_resp = self.client.post("/api/scratchpad/suggest", json={"raw_text": "retry queue"})
        self.assertEqual(suggest_resp.status_code, 200)
        self.assertEqual(suggest_resp.json()["filename"], "queue-worker-2.md")
        self.assertEqual(suggest_resp.json()["target_path"], "scratchpad/queue-worker-2.md")

        # 8. Commit Idea updates cache immediately (0 extra GitHub reads needed to read it back)
        save_idea = self.client.post(
            "/api/scratchpad/notes",
            json={"title": "Queue Worker", "content": "## Overview\nRetry queue", "section": "ideas", "mode": "ai"},
        )
        self.assertEqual(save_idea.status_code, 201)
        self.assertEqual(save_idea.json()["path"], "scratchpad/queue-worker-2.md")
        reads_before = read_mock.call_count
        self.assertEqual(self.client.get("/api/scratchpad/notes/queue-worker-2.md?section=ideas").status_code, 200)
        self.assertEqual(read_mock.call_count, reads_before)

        # 9. Commit Raw never touches AI suggest, preserves exact text verbatim, and updates cache
        suggest_calls_before = suggest_mock.call_count
        verbatim_raw = "  Quick raw brainstorm\n  keep exact indent"
        save_raw = self.client.post(
            "/api/scratchpad/notes",
            json={"title": "", "content": verbatim_raw, "section": "raw", "mode": "raw"},
        )
        self.assertEqual(save_raw.status_code, 201)
        self.assertEqual(suggest_mock.call_count, suggest_calls_before)
        self.assertEqual(commit_calls[-1]["section"], "raw")
        self.assertEqual(commit_calls[-1]["title"], "Quick raw brainstorm")
        self.assertEqual(commit_calls[-1]["content"], verbatim_raw)
        self.assertEqual(save_raw.json()["path"], "raw/quick-raw-brainstorm.md")
        self.assertEqual(save_raw.json()["content"], verbatim_raw)

        cached_raw_read = self.client.get("/api/scratchpad/notes/quick-raw-brainstorm.md?section=raw")
        self.assertEqual(cached_raw_read.status_code, 200)
        self.assertEqual(cached_raw_read.json()["content"], verbatim_raw)
        self.assertEqual(read_mock.call_count, reads_before)

    def test_dashboard_html_exposes_ideas_and_raw_sections_and_image_installs_opencode(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

        web_root = Path(__file__).resolve().parents[2] / "dashboard" / "apps" / "web"
        scratchpad_tsx = (web_root / "app" / "scratchpad" / "page.tsx").read_text(encoding="utf-8")
        provider_tsx = (web_root / "components" / "dashboard-provider.tsx").read_text(encoding="utf-8")
        combined = scratchpad_tsx + "\n" + provider_tsx
        for marker in (
            "Scratchpad",
            "scratchpad-subtab-ideas",
            "scratchpad-subtab-raw",
            "scratchpad-ideas-composer",
            "scratchpad-raw-composer",
            "scratchpad-raw-submit-btn",
            "/api/scratchpad/notes/refresh",
            "/api/scratchpad/suggest",
        ):
            self.assertIn(marker, combined)
        self.assertIn("ScratchpadSuggestionModal", scratchpad_tsx)
        self.assertNotIn("scratchpad-save-raw-btn", combined)
        self.assertNotIn("scratchpad-modal-save-raw-btn", combined)
        self.assertTrue(any("opencode.ai/v2/install" in cmd for cmd in OPENCODE_INSTALL_COMMANDS))

        def _deps(obj):
            yield obj
            if hasattr(obj, "_deps_"):
                for d in obj._deps_():
                    yield from _deps(d)

        dep_reprs = "\n".join(repr(d) for d in _deps(control_plane_image))
        self.assertIn("apt_install", dep_reprs)
        self.assertIn("run_commands", dep_reprs)
        func_source = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox", "function.py")
        with open(func_source, encoding="utf-8") as fp:
            src_text = fp.read()
        self.assertIn("ca-certificates", src_text)
        self.assertIn("*OPENCODE_INSTALL_COMMANDS", src_text)


if __name__ == "__main__":
    unittest.main()
