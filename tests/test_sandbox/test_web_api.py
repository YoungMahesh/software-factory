"""Subsystem tests for Modal Sandbox Runner Web UI and REST API."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.core import LaunchResponse, SnapshotResponse
from sandbox.web import SnapshotLaunchPayload, app


class TestWebAPI(unittest.TestCase):
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

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = [
            {
                "id": "sb-1",
                "name": "inst-1",
                "running": True,
                "exit_code": None,
                "app_name": "app-1",
                "profile": "prof-1",
                "ssh_command": "ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p 36511 root@r479.modal.host",
                "t3_pair_url": "https://ta-123-3775-xyz.w.modal.host/pair#token=LDF3EM8HZ4G8",
            },
            {
                "id": "sb-2",
                "name": None,
                "running": False,
                "exit_code": 0,
                "app_name": "app-2",
                "profile": "prof-2",
                "ssh_command": None,
                "t3_pair_url": None,
            },
        ]

        response = self.client.get("/api/sandboxes?all_apps=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], "sb-1")
        self.assertEqual(data[0]["profile"], "prof-1")
        self.assertTrue(data[0]["running"])
        self.assertEqual(
            data[0]["ssh_command"],
            "ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p 36511 root@r479.modal.host",
        )
        self.assertEqual(
            data[0]["t3_pair_url"],
            "https://ta-123-3775-xyz.w.modal.host/pair#token=LDF3EM8HZ4G8",
        )
        mock_get_sandboxes.assert_called_once_with(app_name=None, all_apps=True, profile=None)

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes_with_profile(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = [
            {"id": "sb-1", "name": "inst-1", "running": True, "exit_code": None, "app_name": "app-1", "profile": "team-a"},
        ]

        response = self.client.get("/api/sandboxes?profile=team-a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["profile"], "team-a")
        mock_get_sandboxes.assert_called_once_with(app_name=None, all_apps=True, profile="team-a")

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes_aggregated_all_profiles(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = [
            {"id": "sb-1", "name": "inst-1", "running": True, "exit_code": None, "app_name": "app-1", "profile": "team-a"},
            {"id": "sb-2", "name": "inst-2", "running": True, "exit_code": None, "app_name": "app-1", "profile": "mahesh471978"},
        ]

        response = self.client.get("/api/sandboxes?profile=all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[1]["profile"], "mahesh471978")
        mock_get_sandboxes.assert_called_once_with(app_name=None, all_apps=True, profile="all")

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes_with_explicit_app_name(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = [
            {"id": "sb-1", "name": "inst-1", "running": True, "exit_code": None, "app_name": "custom-app", "profile": "prof-1"},
        ]

        response = self.client.get("/api/sandboxes?app_name=custom-app")
        self.assertEqual(response.status_code, 200)
        mock_get_sandboxes.assert_called_once_with(app_name="custom-app", all_apps=False, profile=None)

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes_with_explicit_all_apps_false(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = []
        response = self.client.get("/api/sandboxes?all_apps=false")
        self.assertEqual(response.status_code, 200)
        mock_get_sandboxes.assert_called_once_with(app_name=None, all_apps=False, profile=None)

    @patch("sandbox.web.get_available_profiles")
    def test_list_profiles(self, mock_get_profiles):
        mock_get_profiles.return_value = [
            {"name": "p1", "active": False, "environment": "main"},
            {"name": "p2", "active": True, "environment": "dev"},
        ]

        response = self.client.get("/api/profiles")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["name"], "p1")
        self.assertEqual(data[1]["name"], "p2")
        self.assertTrue(data[1]["active"])

    def test_favicon(self):
        # Favicon remains unauthenticated
        unauth_client = TestClient(app)
        response = unauth_client.get("/favicon.ico")
        self.assertEqual(response.status_code, 204)

    @patch("sandbox.web.terminate_sandbox")
    def test_terminate_sandbox_success(self, mock_terminate):
        mock_terminate.return_value = {
            "id": "sb-123",
            "status": "terminated",
            "exit_code": 0,
            "profile": "prof-1",
        }

        response = self.client.post("/api/sandboxes/sb-123/terminate?profile=prof-1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "sb-123")
        self.assertEqual(data["status"], "terminated")
        self.assertEqual(data["profile"], "prof-1")
        mock_terminate.assert_called_once_with("sb-123", profile="prof-1")

    @patch("sandbox.web.terminate_sandbox")
    def test_terminate_sandbox_failure(self, mock_terminate):
        mock_terminate.return_value = {
            "id": "sb-123",
            "status": "error",
            "error": "Sandbox not found",
        }

        response = self.client.post("/api/sandboxes/sb-123/terminate")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Sandbox not found", response.json()["detail"])

    @patch("sandbox.web.capture_snapshot_core")
    def test_create_snapshot(self, mock_capture):
        mock_capture.return_value = SnapshotResponse(
            sandbox_id="sb-abc",
            image_id="im-xyz",
            ttl_days=14,
            ttl_seconds=1209600,
            terminated=False,
        )

        payload = {"name": "test-snap", "ttl_days": 14, "terminate": False, "profile": "prof-x"}
        response = self.client.post("/api/sandboxes/sb-abc/snapshot", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["image_id"], "im-xyz")
        self.assertEqual(data["sandbox_id"], "sb-abc")
        self.assertEqual(data["ttl_days"], 14)
        mock_capture.assert_called_once_with(
            sandbox_id="sb-abc",
            ttl_days=14,
            terminate=False,
            name="test-snap",
            profile="prof-x",
        )

    @patch("sandbox.web.list_snapshots")
    def test_list_snapshots(self, mock_list):
        mock_list.return_value = [
            {
                "image_id": "im-1",
                "sandbox_id": "sb-1",
                "name": "snap-1",
                "created_at": "2026-11-07T08:00:00Z",
                "ttl_days": 30,
                "is_vm": False,
                "profile": "team-a",
            }
        ]

        response = self.client.get("/api/snapshots?profile=team-a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["image_id"], "im-1")
        self.assertEqual(data[0]["name"], "snap-1")
        self.assertEqual(data[0]["profile"], "team-a")
        mock_list.assert_called_once_with(profile="team-a")

    @patch("sandbox.web.delete_snapshot")
    def test_delete_snapshot(self, mock_delete):
        mock_delete.return_value = True
        response = self.client.delete("/api/snapshots/im-123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"image_id": "im-123", "deleted": True})

        mock_delete.return_value = False
        response404 = self.client.delete("/api/snapshots/im-missing")
        self.assertEqual(response404.status_code, 404)

    @patch("sandbox.web.get_client_for_profile")
    @patch("sandbox.web.launch_sandbox")
    def test_launch_from_snapshot_with_profile(self, mock_launch, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = LaunchResponse(
            sandbox_id="sb-new",
            app_name="resumed-app",
            sandbox_name="resumed-sandbox-01",
            ssh_info=("modal.internal", 2222),
            opencode_url="https://opencode.modal.run",
            opencode_password="pass",
            is_vm=False,
        )
        mock_launch.return_value = (MagicMock(), mock_response)

        payload = {
            "name": "resumed-app",
            "vm": False,
            "opencode": True,
            "profile": "prod-profile",
        }
        response = self.client.post("/api/snapshots/im-snap1/launch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sandbox_id"], "sb-new")
        self.assertEqual(data["app_name"], "resumed-app")
        self.assertEqual(data["opencode_url"], "https://opencode.modal.run")

        mock_get_client.assert_called_once_with("prod-profile")
        mock_launch.assert_called_once()
        _, kwargs = mock_launch.call_args
        self.assertEqual(kwargs.get("client"), mock_client)

    @patch("sandbox.web.launch_sandbox")
    def test_launch_from_snapshot_default_payload(self, mock_launch):
        mock_response = LaunchResponse(
            sandbox_id="sb-default",
            app_name="resumed-sandbox",
            sandbox_name="resumed-sandbox-01",
            ssh_info=("modal.internal", 2222),
            is_vm=False,
        )
        mock_launch.return_value = (MagicMock(), mock_response)

        payload_obj = SnapshotLaunchPayload()
        self.assertTrue(payload_obj.t3)
        self.assertFalse(payload_obj.opencode)
        self.assertFalse(payload_obj.agy)
        self.assertFalse(payload_obj.modal)

        response = self.client.post("/api/snapshots/im-snap1/launch", json={})
        self.assertEqual(response.status_code, 200)
        mock_launch.assert_called_once()
        req = mock_launch.call_args[0][0]
        self.assertTrue(req.t3)
        self.assertFalse(req.opencode)
        self.assertFalse(req.agy)
        self.assertFalse(req.modal)
        self.assertFalse(req.vm)
        self.assertIsNone(req.memory)

    def test_index_page_returns_html(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Modal Sandbox Runner", response.text)
        self.assertIn("Sandboxes", response.text)
        self.assertIn("Snapshots", response.text)
        self.assertIn("Workspace Profiles", response.text)
        self.assertIn("overflow-x-auto", response.text)

    def test_index_page_contains_updated_launch_defaults(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("this.launchForm.t3 = true;", html)
        self.assertIn("this.launchForm.memory = snap.is_vm ? 1 : null;", html)
        self.assertIn("replace(/[-_ ]*snapshot$/i, '')", html)

    def test_index_page_contains_actions_section_elements(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("copySshCommand(sb)", html)
        self.assertIn("sb.t3_pair_url", html)
        self.assertIn("T3Code", html)


class TestWebAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unconfigured_credentials_raises_500(self):
        # When WEB_UI_USERNAME / WEB_UI_PASSWORD are not set, permissive access is gone; returns 500
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 500)
            self.assertIn("Server authentication misconfigured", response.json()["detail"])

    def test_auth_enforced_when_credentials_set(self):
        env = {
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "secretpassword",
        }
        with patch.dict(os.environ, env, clear=True):
            # Unauthorized request (missing header)
            res_unauth = self.client.get("/")
            self.assertEqual(res_unauth.status_code, 401)
            self.assertIn("WWW-Authenticate", res_unauth.headers)
            self.assertIn("Authentication required", res_unauth.json()["detail"])

            # Wrong scheme
            res_scheme = self.client.get("/", headers={"Authorization": "Bearer some-token"})
            self.assertEqual(res_scheme.status_code, 401)
            self.assertIn("Invalid authentication scheme", res_scheme.json()["detail"])

            # Wrong password
            bad_auth = base64.b64encode(b"superadmin:wrongpass").decode()
            res_bad = self.client.get("/", headers={"Authorization": f"Basic {bad_auth}"})
            self.assertEqual(res_bad.status_code, 401)
            self.assertIn("Incorrect authentication credentials", res_bad.json()["detail"])

            # Correct Basic Auth
            good_auth = base64.b64encode(b"superadmin:secretpassword").decode()
            res_good = self.client.get("/", headers={"Authorization": f"Basic {good_auth}"})
            self.assertEqual(res_good.status_code, 200)

            # Favicon remains public
            res_fav = self.client.get("/favicon.ico")
            self.assertEqual(res_fav.status_code, 204)

    def test_modal_sandbox_auth_token_not_accepted_for_web_ui(self):
        env = {
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "secretpassword",
            "MODAL_SANDBOX_AUTH_TOKEN": "token-xyz-123",
        }
        with patch.dict(os.environ, env, clear=True):
            # Bearer token is rejected on Web UI
            res_bearer = self.client.get("/", headers={"Authorization": "Bearer token-xyz-123"})
            self.assertEqual(res_bearer.status_code, 401)

            # Basic Auth using token as password is rejected if it doesn't match WEB_UI_PASSWORD
            basic_tok = base64.b64encode(b"superadmin:token-xyz-123").decode()
            res_basic = self.client.get("/", headers={"Authorization": f"Basic {basic_tok}"})
            self.assertEqual(res_basic.status_code, 401)
