"""Subsystem tests for XFCE desktop environment and Google Chrome integration."""

import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from sandbox.cli import create_parser
from sandbox.config import DEFAULT_WEB_PORT
from sandbox.core import LaunchRequest, validate_launch_request
from sandbox.formatting import print_access_info
from sandbox.launcher import SandboxLauncher


class TestXfceIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_parser_parses_xfce_flag_defaults(self):
        parser = create_parser()
        args = parser.parse_args(["--name", "xfce-box", "--xfce"])
        self.assertTrue(args.xfce)
        self.assertEqual(args.xfce_port, 3000)
        self.assertIsNone(args.xfce_password)

    def test_parser_parses_xfce_custom_port_and_password(self):
        parser = create_parser()
        args = parser.parse_args([
            "--name", "xfce-box",
            "--xfce",
            "--xfce-port", "6080",
            "--xfce-password", "secret123"
        ])
        self.assertTrue(args.xfce)
        self.assertEqual(args.xfce_port, 6080)
        self.assertEqual(args.xfce_password, "secret123")

    def test_validate_launch_request_xfce_auto_enables_vm(self):
        req = LaunchRequest(name="xfce-box", xfce=True, vm=False)
        validate_launch_request(req)
        self.assertTrue(req.vm, "--xfce should automatically imply and enable --vm")

    def test_validate_launch_request_xfce_port_collision(self):
        req = LaunchRequest(
            name="xfce-box",
            xfce=True,
            xfce_port=4096,
            opencode=True,
            opencode_port=4096,
        )
        with self.assertRaises(ValueError) as ctx:
            validate_launch_request(req)
        self.assertIn("must differ", str(ctx.exception))

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_xfce_builds_image_and_sets_env(self, mock_app_lookup, mock_sandbox_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-xfce-1"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        mock_image = MagicMock()
        mock_build_image = MagicMock(return_value=mock_image)

        req = LaunchRequest(
            name="xfce-app",
            xfce=True,
            xfce_password="test-password-123",
        )

        running = SandboxLauncher.run(
            req=req,
            repo_root=self.repo_root,
            build_image_fn=mock_build_image,
            load_pubkey_fn=lambda: "ssh-ed25519 dummy",
        )

        mock_build_image.assert_called_once()
        self.assertTrue(mock_build_image.call_args.kwargs.get("xfce"))

        create_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(create_kwargs["runtime"], "vm")
        env = create_kwargs["env"]
        self.assertEqual(env["ENABLE_XFCE"], "1")
        self.assertEqual(env["XFCE_PORT"], "3000")
        self.assertEqual(env["XFCE_PASSWORD"], "test-password-123")

        self.assertIsNotNone(running.response.xfce_url)
        self.assertEqual(running.response.xfce_port, 3000)
        self.assertEqual(running.response.xfce_password, "test-password-123")

    def test_print_access_info_displays_xfce_desktop(self):
        captured_output = io.StringIO()
        with patch("sys.stdout", captured_output):
            print_access_info(
                app_name="xfce-test",
                sandbox_name="xfce-test-sandbox",
                xfce_url="https://3000.mahesh0.dev/vnc.html?autoconnect=true&resize=remote",
                xfce_port=3000,
                xfce_password="mypassword",
            )
        output = captured_output.getvalue()
        self.assertIn("XFCE Desktop: https://3000.mahesh0.dev", output)
        self.assertIn("VNC Password: mypassword", output)

    def test_startup_script_contains_xfce_support(self):
        startup_sh = self.repo_root / "shared" / "startup.sh"
        content = startup_sh.read_text(encoding="utf-8")
        self.assertIn('ENABLE_XFCE', content)
        self.assertIn('desktop-service start', content)
