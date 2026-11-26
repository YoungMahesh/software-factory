"""Tests for Factory App HTTP routes and Modal worker wiring."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.apps import (
    FactoryAppRecord,
    FactoryStateStore,
    LaunchCoordinator,
    set_coordinator_factory,
    set_launch_dispatcher,
)
from sandbox.function import app as control_plane_modal_app, run_launch_request, web_app
from sandbox.web import app as web_router_app


class TestAppRoutes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = FactoryStateStore(root_dir=Path(self.tmpdir.name))
        self.env_patcher = patch.dict(
            os.environ,
            {
                "WEB_UI_USERNAME": "testadmin",
                "WEB_UI_PASSWORD": "testpassword",
            },
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(web_router_app, headers={"Authorization": f"Basic {auth_bytes}"})
        self.unauth_client = TestClient(web_router_app)
        self.dispatched: list[str] = []
        self.fake_sandbox = MagicMock()
        self.fake_sandbox.poll.return_value = None
        self.coordinator = LaunchCoordinator(
            store=self.store,
            sandbox_from_id_fn=MagicMock(return_value=self.fake_sandbox),
            terminate_fn=MagicMock(return_value={"status": "terminated"}),
            list_snapshots_fn=MagicMock(
                return_value=[{"image_id": "im-snap-9", "sandbox_id": "sb-stopped", "name": "snap-9"}]
            ),
            env={},
        )
        set_coordinator_factory(lambda: self.coordinator)
        set_launch_dispatcher(lambda req_id: self.dispatched.append(req_id))

    def tearDown(self):
        set_coordinator_factory(None)
        set_launch_dispatcher(None)
        self.env_patcher.stop()
        self.tmpdir.cleanup()

    def test_apps_and_models_require_authentication(self):
        self.assertEqual(self.unauth_client.get("/api/apps").status_code, 401)
        self.assertEqual(self.unauth_client.get("/api/models").status_code, 401)
        self.assertEqual(self.unauth_client.post("/api/apps", json={"prompt": "hi"}).status_code, 401)

    def test_list_models_includes_gemini_4_hydrogen_default(self):
        res = self.client.get("/api/models")
        self.assertEqual(res.status_code, 200)
        models = res.json()
        self.assertGreaterEqual(len(models), 1)
        default_model = next(m for m in models if m["is_default"])
        self.assertEqual(default_model["provider"], "antigravity")
        self.assertEqual(default_model["model"], "gemini-4-hydrogen")

    def test_create_app_and_poll_launch_status(self):
        res = self.client.post(
            "/api/apps",
            json={"prompt": "Build a markdown notes app", "template": "nextjs", "thought_level": "high"},
        )
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(data["request_id"], self.dispatched[0])
        self.assertEqual(data["status_url"], f"/api/launches/{data['request_id']}")

        poll_res = self.client.get(data["status_url"])
        self.assertEqual(poll_res.status_code, 200)
        poll_body = poll_res.json()
        self.assertEqual(poll_body["request"]["status"], "queued")
        self.assertEqual(poll_body["app"]["slug"], "build-a-markdown-notes-app")

        apps_res = self.client.get("/api/apps")
        self.assertEqual(apps_res.status_code, 200)
        self.assertEqual(len(apps_res.json()), 1)
        self.assertEqual(apps_res.json()[0]["runtime_status"], "provisioning")

        single_res = self.client.get(f"/api/apps/{data['app_id']}")
        self.assertEqual(single_res.status_code, 200)
        self.assertEqual(single_res.json()["app_id"], data["app_id"])

        self.assertEqual(self.client.get("/api/launches/req_missing").status_code, 404)

    def test_open_stopped_relaunch_and_delete_routes(self):
        app_rec = FactoryAppRecord(
            app_id="app_xyz",
            slug="xyz-app",
            title="XYZ App",
            prompt="Build XYZ",
            status="ready",
            sandbox_id="sb-stopped",
            environment_id="env-1",
            thread_id="thread:9",
            t3_url="https://ta-xyz-3775.w.modal.host",
            chat_url="https://ta-xyz-3775.w.modal.host/env-1/thread%3A9",
        )
        self.store.save_app(app_rec)

        proc = MagicMock()
        proc.wait.return_value = 0
        proc.stdout.read.return_value = '{"credential": "fresh-tok"}'
        proc.stderr.read.return_value = ""
        self.fake_sandbox.exec.return_value = proc
        open_ok = self.client.post("/api/apps/app_xyz/open")
        self.assertEqual(open_ok.status_code, 200)
        self.assertEqual(
            open_ok.json()["handoff_url"],
            "https://ta-xyz-3775.w.modal.host/env-1/thread%3A9#token=fresh-tok",
        )

        self.fake_sandbox.poll.return_value = 137
        open_stopped = self.client.post("/api/apps/app_xyz/open")
        self.assertEqual(open_stopped.status_code, 409)
        self.assertEqual(open_stopped.json()["detail"]["snapshot_image_id"], "im-snap-9")

        relaunch = self.client.post("/api/apps/app_xyz/relaunch")
        self.assertEqual(relaunch.status_code, 202)
        self.assertEqual(len(self.dispatched), 1)

        # Resume query preserves failed sandbox when active
        self.fake_sandbox.poll.return_value = None
        self.store.save_app(
            app_rec.model_copy(
                update={"status": "failed", "failed_step": "waiting_t3", "workspace_ready": True}
            )
        )
        resumed = self.client.post("/api/apps/app_xyz/relaunch?resume=true")
        self.assertEqual(resumed.status_code, 202)
        self.assertEqual(resumed.json()["request"]["resume_from_step"], "waiting_t3")
        self.assertEqual(resumed.json()["app"]["sandbox_id"], "sb-stopped")

        deleted = self.client.delete("/api/apps/app_xyz?terminate_sandbox=true")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
        self.assertEqual(self.client.get("/api/apps/app_xyz").status_code, 404)

    def test_modal_function_and_web_app_include_worker_and_routes(self):
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        fn_client = TestClient(web_app, headers={"Authorization": f"Basic {auth_bytes}"})
        res = fn_client.get("/api/apps")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(run_launch_request)
        self.assertEqual(control_plane_modal_app.name, "sandbox-control-plane")

    def test_homepage_serves_status_page_and_nextjs_builder_exposes_operator_flows(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Modal Sandbox Control Plane API", res.text)

        web_root = Path(__file__).resolve().parents[3] / "dashboard" / "apps" / "web"
        builder_tsx = (web_root / "app" / "page.tsx").read_text(encoding="utf-8")
        provider_tsx = (web_root / "components" / "dashboard-provider.tsx").read_text(encoding="utf-8")
        grid_tsx = (web_root / "components" / "builder" / "factory-app-grid.tsx").read_text(encoding="utf-8")
        observer_ts = (web_root / "hooks" / "use-launch-observer.ts").read_text(encoding="utf-8")

        self.assertIn("builder-prompt-input", builder_tsx)
        self.assertIn("/api/apps", provider_tsx)
        self.assertIn("/api/launches/", observer_ts)
        self.assertIn("/api/models", provider_tsx)
        self.assertIn("Relaunch", grid_tsx)
        self.assertIn("Resume Snapshot", grid_tsx)
