"""Unit and REST API tests for Scratchpad Idea/Raw note deletion."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.apps import CachedScratchpadNote, FactoryStateStore
from sandbox.scratchpad import delete_scratchpad_note, set_scratchpad_overrides
from sandbox.web import app


class TestScratchpadDelete(unittest.TestCase):
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

    @patch("sandbox.config_store.github_json_request")
    def test_delete_scratchpad_note_github_helper(self, mock_req):
        mock_req.side_effect = [
            (200, {"type": "file", "sha": "sha-del-1"}),
            (200, {"commit": {"sha": "commit-1"}}),
        ]
        deleted_path = delete_scratchpad_note("sFactory0", filename="my-note.md", token="tok", section="raw")
        self.assertEqual(deleted_path, "raw/my-note.md")
        del_call = mock_req.call_args_list[1]
        self.assertEqual(del_call.kwargs["method"], "DELETE")
        self.assertEqual(del_call.kwargs["payload"]["sha"], "sha-del-1")

        mock_req.side_effect = [(404, {"message": "Not Found"})]
        with self.assertRaises(FileNotFoundError):
            delete_scratchpad_note("sFactory0", filename="missing.md", token="tok", section="ideas")

    def test_delete_scratchpad_route_updates_cache_and_enforces_auth(self):
        self.assertEqual(self.unauth_client.delete("/api/scratchpad/notes/idea.md?section=ideas").status_code, 401)

        self.store.record_scratchpad_commit(
            "sFactory0/config",
            CachedScratchpadNote(
                section="ideas",
                filename="idea.md",
                slug="idea",
                path="scratchpad/idea.md",
                title="Idea",
                sha="s1",
                size=10,
            ),
            "# Idea\n\nBody\n",
        )
        self.store.record_scratchpad_commit(
            "sFactory0/config",
            CachedScratchpadNote(
                section="raw",
                filename="dump.md",
                slug="dump",
                path="raw/dump.md",
                title="Dump",
                sha="r1",
                size=5,
            ),
            "hello",
        )

        deleted_calls = []

        def fake_delete(owner, *, filename, token, section="ideas"):
            if filename == "missing.md":
                raise FileNotFoundError("not found")
            deleted_calls.append((owner, filename, section))
            return f"{'scratchpad' if section == 'ideas' else 'raw'}/{filename}"

        set_scratchpad_overrides(
            delete_note_fn=fake_delete,
            context_fn=lambda: ("sFactory0", "tok"),
            store_fn=lambda: self.store,
        )

        res = self.client.delete("/api/scratchpad/notes/raw.md?section=bad")
        self.assertEqual(res.status_code, 422)

        res_bad_name = self.client.delete("/api/scratchpad/notes/UPPER.md?section=ideas")
        self.assertEqual(res_bad_name.status_code, 400)

        res_404 = self.client.delete("/api/scratchpad/notes/missing.md?section=ideas")
        self.assertEqual(res_404.status_code, 404)

        res_ok = self.client.delete("/api/scratchpad/notes/idea.md?section=ideas")
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json(), {"section": "ideas", "filename": "idea.md", "path": "scratchpad/idea.md", "deleted": True})
        self.assertEqual(deleted_calls, [("sFactory0", "idea.md", "ideas")])

        cat = self.store.get_scratchpad_catalog()
        self.assertEqual(cat.ideas, [])
        self.assertNotIn("scratchpad/idea.md", cat.bodies)
        self.assertEqual([n.filename for n in cat.raw], ["dump.md"])

        scratchpad_tsx = (
            Path(__file__).resolve().parents[2] / "dashboard" / "apps" / "web" / "app" / "scratchpad" / "page.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("deleteScratchpadNote", scratchpad_tsx)
