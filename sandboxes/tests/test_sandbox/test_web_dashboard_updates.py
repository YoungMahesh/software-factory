"""Tests for Sandbox Web Dashboard branding, defaults, Advanced options, and snapshot rootfs_bytes."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.apps import (
    CreateAppPayload,
    FactoryStateStore,
    LaunchCoordinator,
    prime_compatibility_key,
    set_coordinator_factory,
    set_default_store,
    set_launch_dispatcher,
)
from sandbox.core import LaunchResponse
from sandbox.snapshots import capture_sandbox_snapshot
from sandbox.web import FreshSandboxLaunchPayload, app


class TestSandboxWebDashboardUpdates(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {"WEB_UI_USERNAME": "testadmin", "WEB_UI_PASSWORD": "testpassword"},
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})

    def tearDown(self):
        set_coordinator_factory(None)
        set_launch_dispatcher(None)
        set_default_store(None)
        self.env_patcher.stop()

    def test_branding_unified_to_sandbox_web_dashboard(self):
        self.assertEqual(app.title, "Sandbox Web Dashboard")
        unauth = TestClient(app).get("/api/sandboxes")
        self.assertEqual(unauth.status_code, 401)
        self.assertIn('realm="Sandbox Web Dashboard"', unauth.headers.get("www-authenticate", ""))

        repo_root = Path(__file__).resolve().parents[3]
        web_root = repo_root / "dashboard" / "apps" / "web"
        files = [
            web_root / "app" / "layout.tsx",
            web_root / "components" / "dashboard-shell.tsx",
            web_root / "lib" / "auth.ts",
            repo_root / "dashboard" / "README.md",
        ]
        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            self.assertIn("Sandbox Web Dashboard", content)
            self.assertNotIn("Modal Sandbox Runner", content)

        grid_src = (web_root / "components" / "builder" / "factory-app-grid.tsx").read_text(encoding="utf-8")
        self.assertNotIn("Delete Factory App", grid_src)
        self.assertNotIn("onDelete", grid_src)

        builder_src = (web_root / "app" / "page.tsx").read_text(encoding="utf-8")
        self.assertNotIn("openFreshLaunchModal", builder_src)
        for token in (
            "t3_usage_volume",
            "t3_port",
            "t3_ssh_host",
            "no_t3_persist",
            "no_cloudflare",
            "full_clone",
            "browser",
            "react_native",
            "xfce_port",
            "xfce_password",
        ):
            self.assertIn(token, builder_src)

    def test_fresh_sandbox_launch_defaults_to_vm_with_1gb_memory(self):
        defaults = FreshSandboxLaunchPayload()
        self.assertTrue(defaults.vm)
        self.assertEqual(defaults.memory, 1)
        self.assertTrue(defaults.t3)
        self.assertTrue(defaults.modal)
        self.assertTrue(defaults.sops)

        with patch("sandbox.web.launch_sandbox") as mock_launch:
            mock_launch.return_value = (
                MagicMock(),
                LaunchResponse(sandbox_id="sb-novm", app_name="demo", sandbox_name="demo-1"),
            )
            res = self.client.post("/api/sandboxes", json={"mode": "standalone", "name": "demo", "vm": False})
            self.assertEqual(res.status_code, 200)
            req = mock_launch.call_args[0][0]
            self.assertFalse(req.vm)
            self.assertIsNone(req.memory)

    def test_models_default_thought_level_xhigh_for_gemini_4_hydrogen_and_advanced_flags(self):
        models_res = self.client.get("/api/models")
        self.assertEqual(models_res.status_code, 200)
        models = models_res.json()
        hydrogen = next(m for m in models if m["model"] == "gemini-4-hydrogen")
        self.assertEqual(hydrogen["default_thought_level"], "xhigh")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            coord = LaunchCoordinator(store=store, env={})
            default_app, _ = coord.create_and_dispatch(CreateAppPayload(prompt="Default app"))
            self.assertEqual(default_app.thought_level, "xhigh")
            self.assertTrue(default_app.vm)
            self.assertEqual(default_app.memory, 1)
            self.assertTrue(default_app.modal)
            self.assertTrue(default_app.sops)

            custom_app, _ = coord.create_and_dispatch(
                CreateAppPayload(
                    prompt="Custom desktop app",
                    thought_level="medium",
                    memory=4,
                    testing=True,
                    browser=True,
                    no_t3_persist=True,
                    modal=False,
                    sops=False,
                    xfce=True,
                    xfce_port=3005,
                    t3_port=3779,
                )
            )
            self.assertEqual(custom_app.thought_level, "medium")
            self.assertEqual(custom_app.memory, 4)
            self.assertTrue(custom_app.vm)
            self.assertTrue(custom_app.xfce)
            self.assertEqual(custom_app.xfce_port, 3005)
            self.assertNotEqual(custom_app.prime_key, prime_compatibility_key(None, True, False))

    @patch("sandbox.snapshots.record_snapshot")
    @patch("modal.Sandbox.from_id")
    def test_capture_snapshot_measures_and_persists_rootfs_bytes(self, mock_from_id, mock_record):
        mock_sb = MagicMock()
        mock_from_id.return_value = mock_sb

        def _exec(*cmd, **_kwargs):
            proc = MagicMock()
            proc.wait.return_value = 0
            if cmd and cmd[0] == "sh" and "df -B1 /" in cmd[-1]:
                proc.stdout.read.return_value = "2147483648\n"
            elif cmd and cmd[0] == "sh" and "/var/run/docker.sock" in cmd[-1]:
                proc.wait.return_value = 0
                proc.stdout.read.return_value = ""
            else:
                proc.stdout.read.return_value = ""
            return proc

        mock_sb.exec.side_effect = _exec
        mock_sb.snapshot_filesystem.return_value = MagicMock(object_id="im-size-123")
        mock_record.return_value = {"image_id": "im-size-123", "name": "sized", "rootfs_bytes": 2147483648}

        res = capture_sandbox_snapshot("sb-sized", ttl_days=7, name="sized", store_name="test-snaps")
        self.assertEqual(res.rootfs_bytes, 2147483648)
        self.assertEqual(res.to_response().rootfs_bytes, 2147483648)
        self.assertEqual(mock_record.call_args.kwargs["rootfs_bytes"], 2147483648)
