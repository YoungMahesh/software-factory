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
    image as control_plane_image,
    resolve_and_validate_web_credentials,
    validate_deployment_credentials,
    web_app,
)
from sandbox.main import run_sandbox_launch
from shared.image import resolve_secret_path


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
        mock_launch.side_effect = FileNotFoundError("Snapshot custom-snap-id not found")
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"repo": "my-repo"}, headers=headers)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Snapshot custom-snap-id not found", response.json()["detail"])

    @patch.dict("os.environ", {"MODAL_SANDBOX_AUTH_TOKEN": "valid-token"})
    @patch("sandbox.function.launch_sandbox")
    def test_launch_endpoint_credentials_error_returns_500(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError(
            "Organization credentials file not found: /root/secrets/github-orgs.env (expected .secrets/github-orgs.env or secrets/github-orgs.env)."
        )
        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.post("/launch", json={"repo": "my-repo"}, headers=headers)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Control plane missing credentials", response.json()["detail"])
        self.assertIn("Ensure secrets/github-orgs.env is present and redeploy", response.json()["detail"])

    @patch.dict("os.environ", {"WEB_UI_USERNAME": "admin", "WEB_UI_PASSWORD": "secretpassword"})
    @patch("sandbox.web.launch_sandbox")
    def test_api_launch_fresh_credentials_error_returns_500(self, mock_launch):
        mock_launch.side_effect = FileNotFoundError(
            "Organization credentials file not found: /root/secrets/github-orgs.env (expected .secrets/github-orgs.env or secrets/github-orgs.env)."
        )
        creds = base64.b64encode(b"admin:secretpassword").decode("utf-8")
        headers = {"Authorization": f"Basic {creds}"}
        response = self.client.post(
            "/api/sandboxes",
            json={"mode": "repo", "repo": "sFactory0/test-repo"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Control plane missing credentials", response.json()["detail"])
        self.assertIn("Ensure secrets/github-orgs.env is present and redeploy", response.json()["detail"])

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

    def test_missing_credentials_raises_error_when_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_root = Path(tmpdir)
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
                "MODAL_SANDBOX_AUTH_TOKEN": "env_tok",
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

    def test_validate_deployment_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertFalse(validate_deployment_credentials(root, enforce=False))
            with self.assertRaises(RuntimeError) as ctx:
                validate_deployment_credentials(root, enforce=True)
            self.assertIn("github-orgs.env", str(ctx.exception))

            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            (secrets_dir / "github-orgs.env").write_text("SFACTORY0_GH_TOKEN=test")
            self.assertTrue(validate_deployment_credentials(root, enforce=True))

    def test_resolve_secret_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertIsNone(resolve_secret_path("custom.env", repo_root=root))

            dot_secrets = root / ".secrets"
            dot_secrets.mkdir()
            (dot_secrets / "custom.env").write_text("TEST=1")
            found = resolve_secret_path("custom.env", repo_root=root)
            self.assertIsNotNone(found)
            self.assertEqual(found, dot_secrets / "custom.env")

    def test_control_plane_image_stages_both_secret_dirs(self):
        mount_reprs = []
        curr = control_plane_image
        while curr and hasattr(curr, "_deps_"):
            deps = curr._deps_()
            for d in deps:
                mount_reprs.append(repr(d))
            curr = deps[0] if deps else None
        mount_str = " ".join(mount_reprs)
        self.assertIn("/root/secrets", mount_str)
        self.assertIn("/root/.secrets", mount_str)


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
