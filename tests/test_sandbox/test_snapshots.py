"""Subsystem tests for Modal Sandbox runner and configuration."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import ANY, MagicMock, patch


class TestSnapshotCliArgsAndValidation(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"

    def test_help_contains_snapshot_flags(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--snapshot", res.stdout)
        self.assertIn("--snapshot-ttl", res.stdout)
        self.assertIn("--terminate", res.stdout)
        self.assertIn("--from-snapshot", res.stdout)
        self.assertIn("--name", res.stdout)

    def test_parser_parses_snapshot_args(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--snapshot", "sb-12345"])
        self.assertEqual(args.snapshot, "sb-12345")
        self.assertEqual(args.snapshot_ttl, 30)
        self.assertFalse(args.terminate)

        args_custom = parser.parse_args(["--snapshot", "sb-999", "--snapshot-ttl", "14", "--terminate"])
        self.assertEqual(args_custom.snapshot, "sb-999")
        self.assertEqual(args_custom.snapshot_ttl, 14)
        self.assertTrue(args_custom.terminate)

    def test_parser_parses_from_snapshot_with_name(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--from-snapshot", "im-12345", "--name", "my-app"])
        self.assertEqual(args.from_snapshot, "im-12345")
        self.assertEqual(args.name, "my-app")
        self.assertIsNone(args.repo)

    def test_from_snapshot_without_secret_requires_name(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--from-snapshot", "im-12345"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--name is required when launching from a snapshot without -r/--repo", res.stderr)

    def test_snapshot_mutual_exclusion_with_from_snapshot(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--from-snapshot", "im-456"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot be used together", res.stderr.lower())

    def test_snapshot_mutual_exclusion_with_repo(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "-r", "dummy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot be used with -r/--repo", res.stderr)

    def test_snapshot_mutual_exclusion_with_name(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--name", "my-app"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot be used with --name", res.stderr)

    def test_snapshot_mutual_exclusion_with_launch_flags(self):
        for flag in [["--vm"], ["--memory", "2"], ["--no-cloudflare"], ["--github-branch", "feat"], ["--agy"]]:
            res = subprocess.run(
                ["python3", str(self.sandbox_main), "--snapshot", "sb-123"] + flag,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0, f"Expected {flag} to fail with --snapshot")
            self.assertIn(f"--snapshot cannot be used with", res.stderr)

    def test_terminate_without_snapshot_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--terminate", "-r", "dummy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--terminate can only be used with --snapshot", res.stderr)

    def test_snapshot_ttl_without_snapshot_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot-ttl", "10", "-r", "dummy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot-ttl can only be used with --snapshot", res.stderr)

    def test_snapshot_ttl_invalid_value_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--snapshot-ttl", "0"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot-ttl must be a positive integer", res.stderr)


class TestSnapshotRunnerExecution(unittest.TestCase):
    @patch("modal.Sandbox.from_id")
    def test_capture_snapshot_invokes_sync_and_snapshot_filesystem(self, mock_from_id):
        import io
        import contextlib
        from unittest.mock import MagicMock
        from sandbox.main import capture_snapshot

        mock_sandbox = MagicMock()
        mock_from_id.return_value = mock_sandbox

        mock_sync_proc = MagicMock()
        mock_sync_proc.wait.return_value = 0
        mock_vm_proc = MagicMock()
        mock_vm_proc.wait.return_value = 1  # not VM

        def mock_exec(*args, **kwargs):
            if args and args[0] == "sync":
                return mock_sync_proc
            return mock_vm_proc

        mock_sandbox.exec.side_effect = mock_exec

        mock_image = MagicMock()
        mock_image.object_id = "im-snap-999"
        mock_sandbox.snapshot_filesystem.return_value = mock_image

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            image_id = capture_snapshot("sb-test-123", ttl_days=10, terminate=False)

        self.assertEqual(image_id, "im-snap-999")
        mock_from_id.assert_called_once_with("sb-test-123")
        mock_sandbox.exec.assert_any_call("sync")
        mock_sync_proc.wait.assert_called_once()
        mock_sandbox.snapshot_filesystem.assert_called_once_with(ttl=864000)
        mock_sandbox.terminate.assert_not_called()

        output = buf.getvalue()
        self.assertIn("im-snap-999", output)
        self.assertIn("--from-snapshot im-snap-999", output)
        self.assertIn("10 days (864000s)", output)

    @patch("modal.Sandbox.from_id")
    def test_capture_snapshot_respects_terminate(self, mock_from_id):
        import io
        import contextlib
        from unittest.mock import MagicMock
        from sandbox.main import capture_snapshot

        mock_sandbox = MagicMock()
        mock_from_id.return_value = mock_sandbox
        mock_sync_proc = MagicMock()
        mock_sync_proc.wait.return_value = 0
        mock_vm_proc = MagicMock()
        mock_vm_proc.wait.return_value = 1
        mock_sandbox.exec.side_effect = lambda *args, **kwargs: mock_sync_proc if args and args[0] == "sync" else mock_vm_proc

        mock_image = MagicMock()
        mock_image.object_id = "im-snap-terminate"
        mock_sandbox.snapshot_filesystem.return_value = mock_image

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            image_id = capture_snapshot("sb-test-123", ttl_days=30, terminate=True)

        self.assertEqual(image_id, "im-snap-terminate")
        mock_sandbox.terminate.assert_called_once()
        output = buf.getvalue()
        self.assertIn("Terminating sandbox sb-test-123", output)

    @patch("modal.Sandbox.from_id")
    def test_capture_snapshot_vm_notice(self, mock_from_id):
        import io
        import contextlib
        from unittest.mock import MagicMock
        from sandbox.main import capture_snapshot

        mock_sandbox = MagicMock()
        mock_from_id.return_value = mock_sandbox
        mock_sync_proc = MagicMock()
        mock_sync_proc.wait.return_value = 0
        mock_sandbox.exec.return_value = mock_sync_proc

        mock_image = MagicMock()
        mock_image.object_id = "im-snap-vm"
        mock_sandbox.snapshot_filesystem.return_value = mock_image

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            capture_snapshot("sb-vm-123", ttl_days=30)

        output = buf.getvalue()
        self.assertIn("VM Sandbox detected", output)
        self.assertIn("Docker daemon storage", output)
        self.assertIn("--vm", output)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("modal.Image.from_id")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_restore_from_snapshot_configuration(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_image_from_id,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from unittest.mock import MagicMock
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_image_from_id.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-restored-1"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--from-snapshot", "im-snap-123", "--name", "my-restored-app"])

        run_sandbox_launch(args)

        mock_build_image.assert_not_called()
        mock_image_from_id.assert_called_once_with("im-snap-123")
        mock_app_lookup.assert_called_once_with("my-restored-app", create_if_missing=True)

        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["image"], mock_image)
        self.assertEqual(call_kwargs["env"]["RESUME_SNAPSHOT"], "1")
        self.assertTrue(call_kwargs["name"].startswith("my-restored-app-"))
        self.assertEqual(call_kwargs["env"]["APP_NAME"], call_kwargs["name"])
        self.assertEqual(call_kwargs["env"]["MODAL_APP_NAME"], "my-restored-app")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("modal.Image.from_id")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_restore_from_snapshot_with_repo(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_image_from_id,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from unittest.mock import MagicMock
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        mock_image = MagicMock()
        mock_image_from_id.return_value = mock_image

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-restored-repo"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmp_secrets:
            dotenv_file = Path(tmp_secrets) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["--from-snapshot", "im-snap-456", "-r", "my-repo"])

            run_sandbox_launch(args, repo_root=Path(tmp_secrets))

        mock_build_image.assert_not_called()
        mock_image_from_id.assert_called_once_with("im-snap-456")
        mock_image.add_local_file.assert_not_called()
        mock_app_lookup.assert_called_once_with("my-repo", create_if_missing=True)
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["image"], mock_image)
        self.assertEqual(call_kwargs["env"]["RESUME_SNAPSHOT"], "1")
        self.assertTrue(call_kwargs["name"].startswith("my-repo-"))
        self.assertEqual(call_kwargs["env"]["APP_NAME"], call_kwargs["name"])
        self.assertEqual(call_kwargs["env"]["MODAL_APP_NAME"], "my-repo")


class TestStartupScriptResume(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_startup_script_contains_resume_snapshot_branches(self):
        content = self.startup_sh.read_text()
        self.assertIn("RESUME_SNAPSHOT", content)
        self.assertIn("Resuming from filesystem snapshot", content)

    def test_startup_script_skips_git_clone_and_discovers_workspace_on_resume(self):
        content = self.startup_sh.read_text()
        self.assertIn('"${RESUME_SNAPSHOT:-0}"', content)
        self.assertIn("for d in /root/*/", content)

    def test_startup_script_syntax_valid(self):
        res = subprocess.run(["bash", "-n", str(self.startup_sh)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in startup.sh: {res.stderr}")

    def test_startup_script_execution_on_resume(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()
            fake_repo = fake_root / "test-repo"
            fake_repo.mkdir()
            (fake_repo / ".git").mkdir()
            (fake_repo / "pnpm-lock.yaml").write_text("lockfile")

            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()

            (fake_bin / "sshd").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "pnpm").write_text("#!/bin/sh\necho 'PNPM CALLED' >&2\nexit 1\n")
            (fake_bin / "git").write_text("#!/bin/sh\necho 'GIT CALLED' >&2\nexit 1\n")
            for cmd in ["sshd", "pnpm", "git"]:
                (fake_bin / cmd).chmod(0o755)

            test_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            export ENABLE_CLOUDFLARE="0"
            export PATH="{fake_bin}:$PATH"
            sed -e 's|/root|{fake_root}|g' -e 's|/usr/sbin/sshd|true|g' -e 's|exec sleep infinity|exit 0|g' "{self.startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")
            self.assertIn("Resuming from filesystem snapshot", res.stdout)
            self.assertNotIn("PNPM CALLED", res.stderr)
            self.assertNotIn("GIT CALLED", res.stderr)
            self.assertIn(f"Workspace resolved to {fake_repo}", res.stdout)
