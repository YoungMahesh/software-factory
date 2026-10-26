"""Subsystem tests for Herdr integration in Modal Sandbox."""

import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch


class TestHerdrIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_help_contains_herdr_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--herdr", res.stdout)
        self.assertIn("https://herdr.dev", res.stdout)

    def test_parser_parses_herdr_flag(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--name", "test-app", "--herdr"])
        self.assertTrue(args.herdr)

    def test_snapshot_cannot_be_used_with_herdr(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--herdr"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(
            "--snapshot cannot be used with launch configuration arguments",
            res.stderr,
        )

    def test_build_sandbox_image_layers_herdr(self):
        from shared.image import build_sandbox_image

        with patch("shared.image.base_image") as mock_base:
            mock_img = MagicMock()
            mock_base.run_commands.return_value = mock_img
            result = build_sandbox_image(herdr=True)
            mock_base.run_commands.assert_called_once_with(
                "curl -fsSL https://herdr.dev/install.sh | env HERDR_INSTALL_DIR=/usr/local/bin sh"
            )
            self.assertEqual(result, mock_img)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_with_herdr(
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
        mock_sandbox.object_id = "sb-herdr-123"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "herdr-app", "--herdr"])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            run_sandbox_launch(args)

        mock_build_image.assert_called_once()
        self.assertTrue(mock_build_image.call_args.kwargs["herdr"])

        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["env"]["ENABLE_HERDR"], "1")
        self.assertIn("Herdr", stdout_buf.getvalue())

    def test_startup_script_configures_herdr_path(self):
        content = self.startup_sh.read_text()
        self.assertIn('if [ "${ENABLE_HERDR:-}" = "1" ]; then', content)
        self.assertIn(
            'grep -qxF \'export PATH="/usr/local/bin:$PATH"\' ~/.bashrc', content
        )


if __name__ == "__main__":
    unittest.main()
