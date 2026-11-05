"""CLI and argument parsing tests for T3 Code integration."""

from pathlib import Path
import subprocess
import unittest
import pytest


class TestT3CodeCli(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"

    def test_help_contains_t3_flags(self):
        import sys

        res = subprocess.run(
            [sys.executable, str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--t3", res.stdout)
        self.assertIn("--t3code", res.stdout)
        self.assertIn("--t3-port", res.stdout)
        self.assertIn("T3 Code server", res.stdout)

    def test_parser_t3_flags(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["-r", "my-repo", "--t3"])
        self.assertTrue(args.t3)
        self.assertEqual(args.t3_port, 3775)

        args_alias = parser.parse_args(["-r", "my-repo", "--t3code", "--t3-port", "3776"])
        self.assertTrue(args_alias.t3)
        self.assertEqual(args_alias.t3_port, 3776)

    def test_snapshot_cannot_be_used_with_t3(self):
        import sys

        res = subprocess.run(
            [sys.executable, str(self.sandbox_main), "--snapshot", "sb-123", "--t3"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot cannot be used with launch configuration arguments", res.stderr)

    def test_t3_port_collision_with_reserved_web_port(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets" / "github-orgs.env"
            secrets_file.parent.mkdir(parents=True)
            secrets_file.write_text("SFACTORY0_GH_TOKEN=dummy\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "test-repo", "--t3", "--t3-port", "3000"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_opencode(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets" / "github-orgs.env"
            secrets_file.parent.mkdir(parents=True)
            secrets_file.write_text("SFACTORY0_GH_TOKEN=dummy\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "test-repo", "--t3", "--opencode", "--t3-port", "4096"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_metro(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets" / "github-orgs.env"
            secrets_file.parent.mkdir(parents=True)
            secrets_file.write_text("SFACTORY0_GH_TOKEN=dummy\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "test-repo", "--t3", "--react-native", "--t3-port", "8081"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_cli_validation_t3_ssh_host_requires_t3(self):
        from sandbox.main import create_parser, validate_args

        parser = create_parser()
        args = parser.parse_args(["-r", "my-repo", "--t3-ssh-host", "box1"])
        with pytest.raises(SystemExit):
            validate_args(parser, args)
