"""Unit tests for automatic SSH configuration appending and CLI options."""

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.cli import (
    append_ssh_config,
    create_parser,
    generate_ssh_config_snippet,
    validate_args,
)
from sandbox.core import LaunchResponse
from sandbox.main import run_remote_launch, run_sandbox_launch


class TestSSHConfigSnippet(unittest.TestCase):
    def test_generate_ssh_config_snippet(self):
        snippet = generate_ssh_config_snippet("test-sandbox", "192.0.2.1", 2222)
        expected = (
            "Host test-sandbox\n"
            "  HostName 192.0.2.1\n"
            "  Port 2222\n"
            "  User root\n"
            "  IdentityFile ~/.ssh/modal-sandbox\n"
            "  StrictHostKeyChecking no\n"
            "  UserKnownHostsFile /dev/null\n"
        )
        self.assertEqual(snippet, expected)


class TestAppendSSHConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "subdir" / "config"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_append_to_new_file_creates_directory_and_writes_snippet(self):
        self.assertFalse(self.config_path.exists())
        success = append_ssh_config("sb-1", "10.0.0.1", 10022, self.config_path)
        self.assertTrue(success)
        self.assertTrue(self.config_path.is_file())

        content = self.config_path.read_text(encoding="utf-8")
        expected = generate_ssh_config_snippet("sb-1", "10.0.0.1", 10022)
        self.assertEqual(content, expected)

    def test_append_to_existing_file_ending_with_single_newline(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text("Host existing\n  HostName 1.1.1.1\n", encoding="utf-8")

        success = append_ssh_config("sb-2", "10.0.0.2", 10023, self.config_path)
        self.assertTrue(success)

        content = self.config_path.read_text(encoding="utf-8")
        expected = (
            "Host existing\n"
            "  HostName 1.1.1.1\n\n"
            + generate_ssh_config_snippet("sb-2", "10.0.0.2", 10023)
        )
        self.assertEqual(content, expected)

    def test_append_to_existing_file_ending_with_double_newline(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text("Host existing\n  HostName 1.1.1.1\n\n", encoding="utf-8")

        success = append_ssh_config("sb-3", "10.0.0.3", 10024, self.config_path)
        self.assertTrue(success)

        content = self.config_path.read_text(encoding="utf-8")
        expected = (
            "Host existing\n"
            "  HostName 1.1.1.1\n\n"
            + generate_ssh_config_snippet("sb-3", "10.0.0.3", 10024)
        )
        self.assertEqual(content, expected)

    def test_append_to_existing_file_without_trailing_newline(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text("Host existing", encoding="utf-8")

        success = append_ssh_config("sb-4", "10.0.0.4", 10025, self.config_path)
        self.assertTrue(success)

        content = self.config_path.read_text(encoding="utf-8")
        expected = (
            "Host existing\n\n"
            + generate_ssh_config_snippet("sb-4", "10.0.0.4", 10025)
        )
        self.assertEqual(content, expected)

    def test_append_failure_logs_warning_and_returns_false(self):
        stderr_buf = io.StringIO()
        # Point config_path to an existing directory so opening it in 'a' mode raises IsADirectoryError
        invalid_path = Path(self.temp_dir.name)
        with patch("sys.stderr", stderr_buf):
            success = append_ssh_config("sb-err", "10.0.0.5", 10026, invalid_path)

        self.assertFalse(success)
        self.assertIn("Warning: Failed to append SSH connection details", stderr_buf.getvalue())


class TestSSHConfigCLI(unittest.TestCase):
    def test_no_ssh_config_flag_default(self):
        parser = create_parser()
        args = parser.parse_args(["--name", "demo-app"])
        self.assertFalse(args.no_ssh_config)

    def test_no_ssh_config_flag_set(self):
        parser = create_parser()
        args = parser.parse_args(["--name", "demo-app", "--no-ssh-config"])
        self.assertTrue(args.no_ssh_config)

    def test_no_ssh_config_rejected_with_snapshot(self):
        parser = create_parser()
        args = parser.parse_args(["--snapshot", "sb-12345", "--no-ssh-config"])
        with self.assertRaises(SystemExit):
            validate_args(parser, args)


class TestSSHConfigLaunchIntegration(unittest.TestCase):
    @patch("sandbox.main.append_ssh_config")
    @patch("sandbox.main.print_access_info")
    @patch("sandbox.main.launch_sandbox")
    def test_run_sandbox_launch_appends_ssh_config_by_default(
        self,
        mock_launch,
        mock_print,
        mock_append,
    ):
        mock_resp = LaunchResponse(
            sandbox_id="sb-test",
            app_name="app-test",
            sandbox_name="sb-instance",
            ssh_info=("192.0.2.10", 2222),
        )
        mock_launch.return_value = (MagicMock(), mock_resp)

        parser = create_parser()
        args = parser.parse_args(["--name", "app-test"])
        run_sandbox_launch(args, parser=parser)

        mock_append.assert_called_once_with(
            instance_name="sb-instance",
            ssh_host="192.0.2.10",
            ssh_port=2222,
        )

    @patch("sandbox.main.append_ssh_config")
    @patch("sandbox.main.print_access_info")
    @patch("sandbox.main.launch_sandbox")
    def test_run_sandbox_launch_with_no_ssh_config_skips_append(
        self,
        mock_launch,
        mock_print,
        mock_append,
    ):
        mock_resp = LaunchResponse(
            sandbox_id="sb-test",
            app_name="app-test",
            sandbox_name="sb-instance",
            ssh_info=("192.0.2.10", 2222),
        )
        mock_launch.return_value = (MagicMock(), mock_resp)

        parser = create_parser()
        args = parser.parse_args(["--name", "app-test", "--no-ssh-config"])
        run_sandbox_launch(args, parser=parser)

        mock_append.assert_not_called()

    @patch("sandbox.main.append_ssh_config")
    @patch("sandbox.main.print_access_info")
    @patch("sandbox.main.run_remote_request")
    def test_run_remote_launch_appends_ssh_config_by_default(
        self,
        mock_request,
        mock_print,
        mock_append,
    ):
        mock_request.return_value = {
            "sandbox_id": "sb-remote",
            "app_name": "app-remote",
            "sandbox_name": "remote-instance",
            "ssh_info": ["198.51.100.2", 2200],
        }

        parser = create_parser()
        args = parser.parse_args([
            "--remote",
            "--endpoint-url",
            "https://control-plane.modal.run",
            "--name",
            "app-remote",
        ])
        run_remote_launch(args, parser=parser)

        mock_append.assert_called_once_with(
            instance_name="remote-instance",
            ssh_host="198.51.100.2",
            ssh_port=2200,
        )

    @patch("sandbox.main.append_ssh_config")
    @patch("sandbox.main.print_access_info")
    @patch("sandbox.main.run_remote_request")
    def test_run_remote_launch_with_no_ssh_config_skips_append(
        self,
        mock_request,
        mock_print,
        mock_append,
    ):
        mock_request.return_value = {
            "sandbox_id": "sb-remote",
            "app_name": "app-remote",
            "sandbox_name": "remote-instance",
            "ssh_info": ["198.51.100.2", 2200],
        }

        parser = create_parser()
        args = parser.parse_args([
            "--remote",
            "--endpoint-url",
            "https://control-plane.modal.run",
            "--name",
            "app-remote",
            "--no-ssh-config",
        ])
        run_remote_launch(args, parser=parser)

        mock_append.assert_not_called()
