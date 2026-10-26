"""Subsystem tests for Pi coding agent integration in Modal Sandbox."""

import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch


class TestPiIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"
        self.startup_sh = self.repo_root / "shared" / "startup.sh"
        self.setup_sh = self.repo_root / "scripts" / "setup.sh"

    def test_help_contains_pi_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--pi", res.stdout)
        self.assertIn("https://pi.dev", res.stdout)
        self.assertIn("DeepSeek V4.1 Flash", res.stdout)

    def test_parser_parses_pi_flag(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--name", "test-app", "--pi"])
        self.assertTrue(args.pi)

    def test_snapshot_cannot_be_used_with_pi(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--pi"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(
            "--snapshot cannot be used with launch configuration arguments",
            res.stderr,
        )

    def test_build_sandbox_image_layers_pi(self):
        from shared.image import (
            LOCAL_OPENCODE_SECRET,
            LOCAL_PI_MODELS,
            LOCAL_PI_SETTINGS,
            REMOTE_OPENCODE_SECRET,
            REMOTE_PI_MODELS,
            REMOTE_PI_SETTINGS,
            build_sandbox_image,
        )

        with patch("shared.image.base_image") as mock_base, patch(
            "shared.image.add_local_files_if_present"
        ) as mock_add_files:
            mock_img = MagicMock()
            mock_base.run_commands.return_value = mock_img
            mock_add_files.return_value = mock_img

            result = build_sandbox_image(pi=True)

            mock_base.run_commands.assert_called_once_with(
                "npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
            )
            mock_add_files.assert_called_once_with(
                mock_img,
                [
                    (LOCAL_PI_SETTINGS, REMOTE_PI_SETTINGS),
                    (LOCAL_PI_MODELS, REMOTE_PI_MODELS),
                    (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
                ],
            )
            self.assertEqual(result, mock_img)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_with_pi(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-pi-123"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "pi-app", "--pi"])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            run_sandbox_launch(args)

        mock_build_image.assert_called_once()
        self.assertTrue(mock_build_image.call_args.kwargs["pi"])

        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["env"]["ENABLE_PI"], "1")
        self.assertIn("Pi", stdout_buf.getvalue())

    def test_startup_script_configures_pi(self):
        content = self.startup_sh.read_text()
        self.assertIn('ENABLE_PI:-}', content)
        self.assertIn('setup_args+=("--pi")', content)

    def test_setup_script_supports_pi(self):
        content = self.setup_sh.read_text()
        self.assertIn("--pi)", content)
        self.assertIn("DECRYPT_PI=true", content)


if __name__ == "__main__":
    unittest.main()
