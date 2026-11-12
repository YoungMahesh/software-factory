"""Unit tests for the hosted Modal sandbox control plane function and API routes."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import modal

from sandbox.cli import create_parser, validate_args
from sandbox.core import LaunchResponse, SnapshotResponse
from sandbox.function import (
    collect_control_plane_secrets,
    image as control_plane_image,
    resolve_and_validate_web_credentials,
    validate_deployment_credentials,
    web_app,
)
from sandbox.main import run_remote_request, run_sandbox_launch

AUTH_ENV = {
    "WEB_UI_USERNAME": "admin",
    "WEB_UI_PASSWORD": "secretpassword",
}
BASIC_AUTH_HEADER = {
    "Authorization": f"Basic {base64.b64encode(b'admin:secretpassword').decode('utf-8')}",
}


class TestSandboxFunctionAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web_app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("app"), "sandbox-control-plane")

    @patch.dict("os.environ", AUTH_ENV)
    def test_auth_enforcement_missing_header(self):
        response = self.client.post("/launch", json={})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Authentication required", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    def test_auth_enforcement_invalid_format(self):
        response = self.client.post(
            "/launch",
            json={},
            headers={"Authorization": "Bearer secret-test-token"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid authentication scheme; expected Basic authentication", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    def test_auth_enforcement_invalid_credentials(self):
        bad_creds = base64.b64encode(b"admin:wrongpassword").decode("utf-8")
        response = self.client.post(
            "/launch",
            json={},
            headers={"Authorization": f"Basic {bad_creds}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("Incorrect authentication credentials", response.json()["detail"])

    @patch.dict("os.environ", {}, clear=True)
    def test_auth_error_when_server_credentials_unset(self):
        headers = {"Authorization": f"Basic {base64.b64encode(b'admin:secretpassword').decode('utf-8')}"}
        response = self.client.post("/launch", json={"name": "test-app"}, headers=headers)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Server authentication misconfigured", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
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

        response = self.client.post("/launch", json={"name": "my-app", "t3": True}, headers=BASIC_AUTH_HEADER)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sandbox_id"], "sb-test-99")
        self.assertEqual(data["ssh_info"], ["ssh.modal.pub", 2222])
        self.assertEqual(data["t3_pair_url"], "https://test.modal.run/pair#token=abc")

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_value_error(self, mock_launch):
        mock_launch.side_effect = ValueError("--memory can only be used with --vm.")
        response = self.client.post("/launch", json={"memory": 4}, headers=BASIC_AUTH_HEADER)
        self.assertEqual(response.status_code, 400)
        self.assertIn("--memory can only be used with --vm", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_not_found_error(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError("Snapshot custom-snap-id not found")
        response = self.client.post("/launch", json={"repo": "my-repo"}, headers=BASIC_AUTH_HEADER)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Snapshot custom-snap-id not found", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_credentials_error_returns_500(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError(
            "GitHub credentials (GH_TOKEN) not found in environment or /root/.env."
        )
        response = self.client.post("/launch", json={"repo": "my-repo"}, headers=BASIC_AUTH_HEADER)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Control plane missing credentials", response.json()["detail"])
        self.assertIn("Ensure GH_TOKEN is present in .env and redeploy", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.web.launch_sandbox")
    def test_api_launch_fresh_credentials_error_returns_500(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError(
            "GitHub credentials (GH_TOKEN) not found in environment or /root/.env."
        )
        response = self.client.post(
            "/api/sandboxes",
            json={"mode": "repo", "repo": "sFactory0/test-repo"},
            headers=BASIC_AUTH_HEADER,
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Control plane missing credentials", response.json()["detail"])
        self.assertIn("Ensure GH_TOKEN is present in .env and redeploy", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_already_exists_error(self, mock_launch):
        mock_launch.side_effect = modal.exception.AlreadyExistsError("sandbox active")
        response = self.client.post("/launch", json={"name": "my-app"}, headers=BASIC_AUTH_HEADER)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Sandbox already exists", response.json()["detail"])

    @patch.dict("os.environ", AUTH_ENV)
    @patch("sandbox.function.capture_snapshot_core")
    def test_snapshot_endpoint_success(self, mock_snapshot):
        mock_snapshot.return_value = SnapshotResponse(
            sandbox_id="sb-active-123",
            image_id="im-snapshot-456",
            ttl_days=15,
            ttl_seconds=1296000,
            terminated=True,
        )
        response = self.client.post(
            "/snapshot",
            json={"sandbox_id": "sb-active-123", "ttl_days": 15, "terminate": True},
            headers=BASIC_AUTH_HEADER,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sandbox_id"], "sb-active-123")
        self.assertEqual(data["image_id"], "im-snapshot-456")
        self.assertTrue(data["terminated"])

    def test_missing_credentials_raises_error_when_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_root = Path(tmpdir)
            with patch.dict(
                "os.environ",
                {"WEB_UI_USERNAME": "", "WEB_UI_PASSWORD": ""},
                clear=False,
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    resolve_and_validate_web_credentials(empty_root, enforce=True)
                self.assertIn("Missing required environment variable(s)", str(ctx.exception))
                self.assertIn("WEB_UI_USERNAME", str(ctx.exception))
                self.assertIn("WEB_UI_PASSWORD", str(ctx.exception))

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
                "WEB_UI_USERNAME=file_user\nWEB_UI_PASSWORD=file_pass\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                creds = resolve_and_validate_web_credentials(tmp_root)
                self.assertEqual(creds.get("WEB_UI_USERNAME"), "file_user")
                self.assertEqual(creds.get("WEB_UI_PASSWORD"), "file_pass")

    def test_collect_control_plane_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            dotenv_file = tmp_root / ".env"
            dotenv_file.write_text(
                "WEB_UI_USERNAME=file_user\nWEB_UI_PASSWORD=file_pass\nGH_TOKEN=token123\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"MODAL_TOKENS": "[{}]"}, clear=True):
                secrets = collect_control_plane_secrets(tmp_root)
                self.assertEqual(secrets.get("WEB_UI_USERNAME"), "file_user")
                self.assertEqual(secrets.get("WEB_UI_PASSWORD"), "file_pass")
                self.assertEqual(secrets.get("GH_TOKEN"), "token123")
                self.assertEqual(secrets.get("MODAL_TOKENS"), "[{}]")

    def test_validate_deployment_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(validate_deployment_credentials(root, enforce=False))
                with self.assertRaises(RuntimeError) as ctx:
                    validate_deployment_credentials(root, enforce=True)
                self.assertIn("GH_TOKEN", str(ctx.exception))

                (root / ".env").write_text("GH_TOKEN=test-token\n")
                self.assertTrue(validate_deployment_credentials(root, enforce=True))


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

    @patch.dict("os.environ", {}, clear=True)
    def test_remote_without_credentials_errors(self):
        with patch("sandbox.main.Path.is_file", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                run_remote_request("https://custom.modal.run", "/launch", {})
            self.assertIn("WEB_UI_USERNAME and WEB_UI_PASSWORD", str(ctx.exception))

    @patch.dict("os.environ", AUTH_ENV)
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

    @patch.dict("os.environ", AUTH_ENV)
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
