"""Unit tests for the hosted Modal sandbox control plane function and API routes."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import modal

from sandbox.cli import create_parser, validate_args
from sandbox.core import LaunchResponse, SnapshotResponse
from sandbox.function import resolve_and_validate_web_credentials, web_app
from sandbox.main import run_sandbox_launch


class TestSandboxFunctionAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web_app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("app"), "sandbox-control-plane")

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "secret-test-token"})
    def test_auth_enforcement_missing_header(self):
        response = self.client.post("/launch", json={})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing Authorization header", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "secret-test-token"})
    def test_auth_enforcement_invalid_format(self):
        response = self.client.post(
            "/launch",
            json={},
            headers={"Authorization": "Token secret-test-token"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid Authorization header format", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "secret-test-token"})
    def test_auth_enforcement_invalid_token(self):
        response = self.client.post(
            "/launch",
            json={},
            headers={"Authorization": "Bearer wrong-token"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid bearer authentication token", response.json()["detail"])

    @patch.dict("os.environ", {}, clear=True)
    @patch("sandbox.function.launch_sandbox")
    def test_auth_permissive_when_token_unset(self, mock_launch):
        mock_sandbox = MagicMock()
        mock_resp = LaunchResponse(
            sandbox_id="sb-test-1",
            app_name="test-app",
            sandbox_name="test-app-12345678",
        )
        mock_launch.return_value = (mock_sandbox, mock_resp)

        response = self.client.post("/launch", json={"name": "test-app"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sandbox_id"], "sb-test-1")

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_success(self, mock_launch):
        mock_sandbox = MagicMock()
        mock_resp = LaunchResponse(
            sandbox_id="sb-test-99",
            app_name="my-app",
            sandbox_name="my-app-abcdef12",
            ssh_info=("ssh.modal.pub", 2222),
            t3_url="https://test.modal.run",
            t3_pair_url="https://test.modal.run/pair#token=abc",
        )
        mock_launch.return_value = (mock_sandbox, mock_resp)

        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"name": "my-app", "t3": True}, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sandbox_id"], "sb-test-99")
        self.assertEqual(data["ssh_info"], ["ssh.modal.pub", 2222])
        self.assertEqual(data["t3_pair_url"], "https://test.modal.run/pair#token=abc")

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_value_error(self, mock_launch):
        mock_launch.side_effect = ValueError("--memory can only be used with --vm.")
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"memory": 4}, headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn("--memory can only be used with --vm", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_not_found_error(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError("Organization credentials file not found")
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"repo": "my-repo"}, headers=headers)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Organization credentials file not found", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_already_exists_error(self, mock_launch):
        mock_launch.side_effect = modal.exception.AlreadyExistsError("sandbox active")
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"name": "my-app"}, headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Sandbox already exists", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.capture_snapshot_core")
    def test_snapshot_endpoint_success(self, mock_snapshot):
        mock_snapshot.return_value = SnapshotResponse(
            sandbox_id="sb-active-123",
            image_id="im-snapshot-456",
            ttl_days=15,
            ttl_seconds=1296000,
            terminated=True,
        )
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post(
            "/snapshot",
            json={"sandbox_id": "sb-active-123", "ttl_days": 15, "terminate": True},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sandbox_id"], "sb-active-123")
        self.assertEqual(data["image_id"], "im-snapshot-456")
        self.assertTrue(data["terminated"])


class TestWebCredentialValidation(unittest.TestCase):
    def test_missing_credentials_raises_error_when_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_root = Path(tmpdir)
            env = {}
            with patch.dict("os.environ", env, clear=True):
                with self.assertRaises(RuntimeError) as cm:
                    resolve_and_validate_web_credentials(empty_root, enforce=True)
                self.assertIn("WEB_UI_USERNAME", str(cm.exception))
                self.assertIn("WEB_UI_PASSWORD", str(cm.exception))

    def test_credentials_resolved_from_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_root = Path(tmpdir)
            env = {
                "WEB_UI_USERNAME": "env_user",
                "WEB_UI_PASSWORD": "env_password",
            }
            with patch.dict("os.environ", env, clear=True):
                creds = resolve_and_validate_web_credentials(empty_root)
                self.assertEqual(creds.get("WEB_UI_USERNAME"), "env_user")
                self.assertEqual(creds.get("WEB_UI_PASSWORD"), "env_password")

    def test_credentials_resolved_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            dotenv_file = tmp_root / ".env"
            dotenv_file.write_text(
                "WEB_UI_USERNAME=file_user\nWEB_UI_PASSWORD=file_pass\nMODAL_SANDBOX_AUTH_TOKEN=file_tok\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                creds = resolve_and_validate_web_credentials(tmp_root)
                self.assertEqual(creds.get("WEB_UI_USERNAME"), "file_user")
                self.assertEqual(creds.get("WEB_UI_PASSWORD"), "file_pass")
                self.assertEqual(creds.get("MODAL_SANDBOX_AUTH_TOKEN"), "file_tok")

    def test_no_modal_sandbox_auth_token_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_root = Path(tmpdir)
            env = {
                "WEB_UI_USERNAME": "u",
                "WEB_UI_PASSWORD": "p",
            }
            with patch.dict("os.environ", env, clear=True):
                creds = resolve_and_validate_web_credentials(empty_root, enforce=True)
                self.assertNotIn("MODAL_SANDBOX_AUTH_TOKEN", creds)


class TestSandboxCliRemoteIntegration(unittest.TestCase):
    def test_parser_accepts_remote_and_endpoint_url(self):
        parser = create_parser()
        args = parser.parse_args(["--remote", "--endpoint-url", "https://modal.run", "--name", "app1"])
        validate_args(parser, args)
        self.assertTrue(args.remote)
        self.assertEqual(args.endpoint_url, "https://modal.run")

    def test_endpoint_url_without_remote_rejected(self):
        parser = create_parser()
        args = parser.parse_args(["--endpoint-url", "https://modal.run", "--name", "app1"])
        with self.assertRaises(SystemExit):
            validate_args(parser, args)

    @patch.dict("os.environ", {}, clear=True)
    def test_remote_without_endpoint_url_errors(self):
        parser = create_parser()
        args = parser.parse_args(["--remote", "--name", "app1"])
        with self.assertRaises(SystemExit):
            run_sandbox_launch(args, parser=parser)

    @patch("sandbox.main.print_access_info")
    @patch("sandbox.main.run_remote_request")
    def test_remote_launch_delegation(self, mock_request, mock_print):
        mock_request.return_value = {
            "sandbox_id": "sb-remote-1",
            "app_name": "remote-app",
            "sandbox_name": "remote-app-12345678",
            "ssh_info": ["ssh.modal.pub", 2200],
            "cloudflare_enabled": True,
        }
        parser = create_parser()
        args = parser.parse_args([
            "--remote",
            "--endpoint-url", "https://custom.modal.run",
            "--name", "remote-app",
        ])
        run_sandbox_launch(args, parser=parser)

        mock_request.assert_called_once()
        endpoint, path, payload = mock_request.call_args[0]
        self.assertEqual(endpoint, "https://custom.modal.run")
        self.assertEqual(path, "/launch")
        self.assertEqual(payload["name"], "remote-app")
        mock_print.assert_called_once()
        self.assertEqual(mock_print.call_args.kwargs["sandbox_id"], "sb-remote-1")

    @patch("sandbox.main.print_snapshot_info")
    @patch("sandbox.main.run_remote_request")
    def test_remote_snapshot_delegation(self, mock_request, mock_print_snapshot):
        mock_request.return_value = {
            "sandbox_id": "sb-target-42",
            "image_id": "im-snap-42",
            "ttl_days": 30,
            "ttl_seconds": 2592000,
            "terminated": False,
        }
        parser = create_parser()
        args = parser.parse_args([
            "--remote",
            "--endpoint-url", "https://custom.modal.run",
            "--snapshot", "sb-target-42",
        ])
        run_sandbox_launch(args, parser=parser)

        mock_request.assert_called_once()
        endpoint, path, payload = mock_request.call_args[0]
        self.assertEqual(endpoint, "https://custom.modal.run")
        self.assertEqual(path, "/snapshot")
        self.assertEqual(payload["sandbox_id"], "sb-target-42")
        mock_print_snapshot.assert_called_once()
        self.assertEqual(mock_print_snapshot.call_args.kwargs["image_id"], "im-snap-42")


if __name__ == "__main__":
    unittest.main()
