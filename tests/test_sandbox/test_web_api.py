"""Subsystem tests for Modal Sandbox Runner Web UI and REST API."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.core import LaunchResponse, SnapshotResponse
from sandbox.web import app


class TestWebAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("sandbox.web.get_sandboxes")
    def test_list_sandboxes(self, mock_get_sandboxes):
        mock_get_sandboxes.return_value = [
            {"id": "sb-1", "name": "inst-1", "running": True, "exit_code": None, "app_name": "app-1", "profile": "prof-1"},
            {"id": "sb-2", "name": None, "running": False, "exit_code": 0, "app_name": "app-2", "profile": "prof-2"},
        ]

        response = self.client.get("/api/sandboxes?all_apps=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], "sb-1")
        self.assertEqual(data[0]["profile"], "prof-1")
        self.assertTrue(data[0]["running"])
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
        mock_get_sandboxes.assert_called_once_with(app_name=None, all_apps=False, profile="team-a")

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
        response = self.client.get("/favicon.ico")
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

    def test_index_page_returns_html(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Modal Sandbox Runner", response.text)
        self.assertIn("Sandboxes", response.text)
        self.assertIn("Snapshots", response.text)
        self.assertIn("Workspace Profiles", response.text)


class TestWebAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_auth_enforced_when_credentials_set(self):
        env = {
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "secretpassword",
        }
        with patch.dict(os.environ, env):
            # Unauthorized request
            res_unauth = self.client.get("/")
            self.assertEqual(res_unauth.status_code, 401)
            self.assertIn("WWW-Authenticate", res_unauth.headers)

            # Wrong password
            bad_auth = base64.b64encode(b"superadmin:wrongpass").decode()
            res_bad = self.client.get("/", headers={"Authorization": f"Basic {bad_auth}"})
            self.assertEqual(res_bad.status_code, 401)

            # Correct Basic Auth
            good_auth = base64.b64encode(b"superadmin:secretpassword").decode()
            res_good = self.client.get("/", headers={"Authorization": f"Basic {good_auth}"})
            self.assertEqual(res_good.status_code, 200)

            # Favicon remains public
            res_fav = self.client.get("/favicon.ico")
            self.assertEqual(res_fav.status_code, 204)

    def test_token_auth_fallback(self):
        env = {
            "MODAL_SANDBOX_AUTH_TOKEN": "token-xyz-123",
        }
        with patch.dict(os.environ, env, clear=True):
            # Bearer token
            res_bearer = self.client.get("/", headers={"Authorization": "Bearer token-xyz-123"})
            self.assertEqual(res_bearer.status_code, 200)

            # Basic Auth using token as password
            basic_tok = base64.b64encode(b"admin:token-xyz-123").decode()
            res_basic = self.client.get("/", headers={"Authorization": f"Basic {basic_tok}"})
            self.assertEqual(res_basic.status_code, 200)

            # Invalid Bearer token
            res_invalid = self.client.get("/", headers={"Authorization": "Bearer badtoken"})
            self.assertEqual(res_invalid.status_code, 401)
