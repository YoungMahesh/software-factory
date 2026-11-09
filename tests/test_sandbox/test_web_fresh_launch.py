"""Tests for Modal Sandbox Runner Web UI Fresh Sandbox Launch enhancements."""

from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.core import LaunchRequest, LaunchResponse
from sandbox.web import FreshSandboxLaunchPayload, SnapshotLaunchPayload, app


class TestWebFreshLaunch(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {
                "WEB_UI_USERNAME": "testadmin",
                "WEB_UI_PASSWORD": "testpassword",
            },
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})

    def tearDown(self):
        self.env_patcher.stop()

    def test_payload_model_defaults(self):
        fresh = FreshSandboxLaunchPayload()
        self.assertTrue(fresh.sops)
        self.assertTrue(fresh.modal)
        self.assertTrue(fresh.t3)
        self.assertFalse(fresh.opencode)
        self.assertFalse(fresh.agy)

        snap = SnapshotLaunchPayload()
        self.assertFalse(snap.sops)
        self.assertFalse(snap.modal)
        self.assertTrue(snap.t3)
        self.assertFalse(snap.opencode)
        self.assertFalse(snap.agy)

    @patch("sandbox.web.launch_sandbox")
    def test_launch_fresh_sandbox_propagates_sops(self, mock_launch):
        mock_response = LaunchResponse(
            sandbox_id="sb-sops-test",
            app_name="software-factory",
            sandbox_name="software-factory-1234",
            is_vm=False,
            sops_enabled=True,
        )
        mock_launch.return_value = (MagicMock(), mock_response)

        payload = {
            "mode": "repo",
            "repo": "software-factory",
            "sops": True,
            "modal": True,
            "t3": True,
        }
        res = self.client.post("/api/sandboxes", json=payload)
        self.assertEqual(res.status_code, 200)
        mock_launch.assert_called_once()
        req: LaunchRequest = mock_launch.call_args[0][0]
        self.assertTrue(req.sops)
        self.assertTrue(req.modal)
        self.assertTrue(req.t3)

    @patch("sandbox.web.launch_sandbox")
    def test_launch_stream_success(self, mock_launch):
        def fake_launch(req, client=None, log_cb=None):
            if log_cb:
                log_cb("▶ Launching container...")
                log_cb("✓ Services online.")
            return MagicMock(), LaunchResponse(
                sandbox_id="sb-stream-ok",
                app_name="software-factory",
                sandbox_name="software-factory-abcd",
                is_vm=False,
            )

        mock_launch.side_effect = fake_launch

        payload = {
            "mode": "repo",
            "repo": "software-factory",
            "sops": True,
            "modal": True,
            "t3": True,
        }
        res = self.client.post("/api/sandboxes/stream", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers["content-type"])

        raw_events = [line for line in res.text.split("\n\n") if line.strip()]
        events = []
        for raw in raw_events:
            for l in raw.split("\n"):
                if l.startswith("data: "):
                    events.append(json.loads(l[6:]))

        types = [e["type"] for e in events]
        self.assertIn("log", types)
        self.assertIn("done", types)
        done_evt = next(e for e in events if e["type"] == "done")
        self.assertEqual(done_evt["response"]["sandbox_id"], "sb-stream-ok")

    def test_launch_stream_validation_error(self):
        res = self.client.post("/api/sandboxes/stream", json={"mode": "repo", "repo": ""})
        self.assertEqual(res.status_code, 200)
        raw_events = [line for line in res.text.split("\n\n") if line.strip()]
        events = [json.loads(l[6:]) for raw in raw_events for l in raw.split("\n") if l.startswith("data: ")]
        err_evt = next(e for e in events if e["type"] == "error")
        self.assertIn("Target repository is required", err_evt["detail"])

    @patch("sandbox.web.launch_sandbox")
    def test_launch_stream_exception_handling(self, mock_launch):
        mock_launch.side_effect = RuntimeError("Failed to clone repository")
        payload = {"mode": "repo", "repo": "broken-repo"}
        res = self.client.post("/api/sandboxes/stream", json=payload)
        self.assertEqual(res.status_code, 200)
        raw_events = [line for line in res.text.split("\n\n") if line.strip()]
        events = [json.loads(l[6:]) for raw in raw_events for l in raw.split("\n") if l.startswith("data: ")]
        err_evt = next(e for e in events if e["type"] == "error")
        self.assertIn("Failed to clone repository", err_evt["detail"])

    def test_index_html_has_software_factory_and_sops(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        self.assertIn("software-factory", html)
        self.assertIn("SOPS", html)
        self.assertIn("/api/sandboxes/stream", html)
        self.assertIn("fresh-launch-log-box", html)
