from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch


class TestSandboxCliArgs(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"

    def test_help_contains_sops_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--sops", res.stdout)
        self.assertIn("Retain SOPS age private key", res.stdout)

    def test_missing_secret_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--sops"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("the following arguments are required: -s/--secret", res.stderr)

    def test_help_contains_github_branch_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--github-branch", res.stdout)
        self.assertIn("-b", res.stdout)
        self.assertNotIn("--github-ref", res.stdout)

    def test_github_ref_flag_is_rejected(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "-s", "dummy", "--github-ref", "main"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unrecognized arguments: --github-ref", res.stderr)

    def test_startup_script_verifies_symbolic_ref_and_uses_branch(self):
        startup_sh = self.repo_root / "shared" / "startup.sh"
        content = startup_sh.read_text()
        self.assertIn('BRANCH="${1:-main}"', content)
        self.assertNotIn('REF="${1:-main}"', content)
        self.assertIn("git symbolic-ref -q HEAD", content)
        self.assertIn("Only Git branches are supported", content)

    def test_parser_parses_github_branch_flag(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["-s", "my-secret", "--github-branch", "feature/auth"])
        self.assertEqual(args.github_branch, "feature/auth")

        args_short = parser.parse_args(["-s", "my-secret", "-b", "feature/dashboard"])
        self.assertEqual(args_short.github_branch, "feature/dashboard")

        args_default = parser.parse_args(["-s", "my-secret"])
        self.assertEqual(args_default.github_branch, "main")

    def test_git_symbolic_ref_behavior_on_branch_vs_tag(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "repo"
            repo_dir.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
            subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_dir, check=True)
            (repo_dir / "file.txt").write_text("hello")
            subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "tag", "v1.0.0"], cwd=repo_dir, check=True)

            # Clone branch -> attached HEAD
            branch_clone = Path(tmpdir) / "clone_branch"
            subprocess.run(["git", "clone", "--branch", "main", "--single-branch", str(repo_dir), str(branch_clone)], check=True, capture_output=True)
            res_branch = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=branch_clone, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res_branch.returncode, 0)

            # Clone tag -> detached HEAD
            tag_clone = Path(tmpdir) / "clone_tag"
            subprocess.run(["git", "clone", "--branch", "v1.0.0", "--single-branch", str(repo_dir), str(tag_clone)], check=True, capture_output=True)
            res_tag = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=tag_clone, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertNotEqual(res_tag.returncode, 0)


class TestSnapshotCliArgsAndValidation(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
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
        self.assertIsNone(args.secret)

    def test_from_snapshot_without_secret_requires_name(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--from-snapshot", "im-12345"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--name is required when launching from a snapshot without --secret", res.stderr)

    def test_snapshot_mutual_exclusion_with_from_snapshot(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--from-snapshot", "im-456"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot be used together", res.stderr.lower())

    def test_snapshot_mutual_exclusion_with_secret(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "-s", "dummy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot be used with --secret", res.stderr)

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
            ["python3", str(self.sandbox_main), "--terminate", "-s", "dummy"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--terminate can only be used with --snapshot", res.stderr)

    def test_snapshot_ttl_without_snapshot_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot-ttl", "10", "-s", "dummy"],
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
        self.assertEqual(call_kwargs["env"]["APP_NAME"], "my-restored-app")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("modal.Image.from_id")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_restore_from_snapshot_with_secret(
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
        mock_staged_image = MagicMock()
        mock_image.add_local_dir.return_value = mock_staged_image
        mock_image_from_id.return_value = mock_image

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-restored-secret"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmp_secrets:
            secrets_dir = Path(tmp_secrets) / "secrets" / "my-secret"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["--from-snapshot", "im-snap-456", "-s", "my-secret"])

            run_sandbox_launch(args, repo_root=Path(tmp_secrets))

        mock_build_image.assert_not_called()
        mock_image_from_id.assert_called_once_with("im-snap-456")
        mock_image.add_local_dir.assert_called_once()
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["image"], mock_staged_image)
        self.assertEqual(call_kwargs["env"]["RESUME_SNAPSHOT"], "1")


class TestStartupScriptResume(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
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


class TestT3CodeIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_help_contains_t3_flags(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
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
        args = parser.parse_args(["-s", "my-secret", "--t3"])
        self.assertTrue(args.t3)
        self.assertEqual(args.t3_port, 3775)

        args_alias = parser.parse_args(["-s", "my-secret", "--t3code", "--t3-port", "3776"])
        self.assertTrue(args_alias.t3)
        self.assertEqual(args_alias.t3_port, 3776)

    def test_snapshot_cannot_be_used_with_t3(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--t3"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot cannot be used with launch configuration arguments", res.stderr)

    def test_t3_port_collision_with_reserved_web_port(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--t3-port", "3000"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_opencode(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--opencode", "--t3-port", "4096"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_metro(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--react-native", "--t3-port", "8081"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_startup_script_contains_t3_daemon_and_check_script(self):
        content = self.startup_sh.read_text()
        self.assertIn("ENABLE_T3", content)
        self.assertIn("check-t3", content)
        self.assertIn("t3 serve", content)
        self.assertIn("--auto-bootstrap-project-from-cwd", content)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_passes_t3_configuration(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-123"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://test-t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "my-secret"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "my-secret", "--t3", "--name", "test-t3-app"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_build_image.assert_called_once_with(
            opencode=False,
            agy=False,
            browser=False,
            modal_tooling=False,
            react_native=False,
            t3=True,
        )
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertIn(3775, call_kwargs["encrypted_ports"])
        self.assertEqual(call_kwargs["env"]["ENABLE_T3"], "1")
        self.assertEqual(call_kwargs["env"]["T3_PORT"], "3775")

    def test_build_sandbox_image_layers_t3(self):
        from shared.image import build_sandbox_image, T3_VERSION, T3_TAR_URL

        with patch("shared.image.base_image") as mock_base:
            mock_img = MagicMock()
            mock_base.run_commands.return_value = mock_img
            result = build_sandbox_image(t3=True)
            mock_base.run_commands.assert_called_once_with(
                "mkdir -p /opt/t3",
                f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
                "ln -sf /opt/t3/t3 /usr/local/bin/t3",
            )

    def test_startup_script_mints_pairing_token(self):
        content = self.startup_sh.read_text()
        self.assertIn("t3 auth pairing create --ttl 24h --json > /tmp/t3-pairing.json", content)

    def test_generate_ascii_qr(self):
        from sandbox.main import generate_ascii_qr

        qr_text = generate_ascii_qr("https://test-t3.modal.run/pair#token=ABCD")
        self.assertIsNotNone(qr_text)
        self.assertTrue(any(c in qr_text for c in ["█", "▀", "▄"]))

    def test_print_access_info_with_1click_pair_url_and_qr(self):
        import io
        from unittest.mock import patch
        from sandbox.main import print_access_info

        mock_sb = MagicMock()
        mock_sb.object_id = "sb-123"

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            print_access_info(
                sandbox=mock_sb,
                app_name="my-app",
                t3_url="https://test-t3.modal.run",
                t3_port=3775,
                t3_pair_url="https://test-t3.modal.run/pair#token=ABCD123",
                t3_qr_code="  █▀▀█\n  ▀▀▀▀",
                cloudflare_enabled=False,
            )

        output = stdout_buf.getvalue()
        self.assertIn("• T3 Code:  https://test-t3.modal.run/pair#token=ABCD123", output)
        self.assertIn("Scan with T3 Code Mobile App (iOS / Android):", output)
        self.assertIn("█▀▀█", output)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    @patch("sandbox.main.print_access_info")
    def test_run_sandbox_launch_resolves_pair_url_from_container(
        self,
        mock_print_access,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-456"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}

        # Mock sandbox.exec("cat", "/tmp/t3-pairing.json")
        mock_exec_proc = MagicMock()
        mock_exec_proc.wait.return_value = 0
        mock_exec_proc.stdout.read.return_value = '{"credential": "SECRET_TOKEN_XYZ"}'
        mock_sandbox.exec.return_value = mock_exec_proc

        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "my-secret"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "my-secret", "--t3", "--name", "test-t3-pair"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_sandbox.exec.assert_called_with("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
        call_kwargs = mock_print_access.call_args.kwargs
        self.assertEqual(call_kwargs["t3_pair_url"], "https://t3.modal.run/pair#token=SECRET_TOKEN_XYZ")
        self.assertIsNotNone(call_kwargs["t3_qr_code"])


class TestSandboxShellAliases(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.aliases_path = self.repo_root / "shared" / "aliases.bash"
        self.legacy_git_bash = self.repo_root / "git.bash"
        self.startup_sh_path = self.repo_root / "shared" / "startup.sh"

    def test_legacy_git_bash_removed(self):
        self.assertFalse(self.legacy_git_bash.exists(), "Legacy root git.bash should be removed")

    def test_shared_aliases_file_exists_and_contains_requested_aliases(self):
        self.assertTrue(self.aliases_path.is_file(), "shared/aliases.bash must exist")
        content = self.aliases_path.read_text()

        expected_docker_aliases = [
            "alias dc='docker container'",
            "alias dco='docker compose'",
            "alias di='docker image'",
            "alias din='docker inspect'",
            "alias dl='docker logs'",
            "alias dn='docker network'",
            "alias dv='docker volume'",
        ]
        expected_git_aliases = [
            "alias gs='git status'",
            "alias gd='git diff'",
            "alias gds='git diff --cached'",
            "alias ga='git add .'",
            "alias gl='git log'",
            "alias gc='git commit -m'",
            "alias gp='git push'",
            "alias gP='git pull'",
            "alias gb='git branch'",
        ]

        for alias in expected_docker_aliases:
            self.assertIn(alias, content, f"Missing Docker alias: {alias}")

        for alias in expected_git_aliases:
            self.assertIn(alias, content, f"Missing Git alias: {alias}")

    def test_image_and_startup_script_stage_and_source_bash_aliases(self):
        from shared.image import LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH

        self.assertEqual(LOCAL_ALIASES_BASH, self.aliases_path)
        self.assertEqual(REMOTE_ALIASES_BASH, "/root/.bash_aliases")

        startup_content = self.startup_sh_path.read_text()
        self.assertIn('if [ -f /root/.bash_aliases ]; then', startup_content)
        self.assertIn('source /root/.bash_aliases', startup_content)
        self.assertNotIn('/root/.git.bash', startup_content)


if __name__ == "__main__":
    unittest.main()



