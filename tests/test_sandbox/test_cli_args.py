"""Subsystem tests for Modal Sandbox runner and configuration."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import ANY, MagicMock, patch

class TestSandboxCliArgs(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
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

    def test_missing_secret_without_name_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--sops"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--name is required when launching without --secret", res.stderr)

    def test_launch_without_secret_with_branch_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--name", "my-app", "-b", "dev"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--github-branch cannot be used without -s/--secret", res.stderr)

    def test_launch_without_secret_with_testing_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--name", "my-app", "--testing"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--testing cannot be used without -s/--secret", res.stderr)

    def test_parser_parses_standalone_launch_with_name(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["--name", "standalone-app"])
        self.assertEqual(args.name, "standalone-app")
        self.assertIsNone(args.secret)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_standalone_sets_no_repo_env(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-standalone-1"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "standalone-app"])

        run_sandbox_launch(args)

        mock_app_lookup.assert_called_once_with("standalone-app", create_if_missing=True)
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["image"], mock_image)
        self.assertTrue(call_kwargs["name"].startswith("standalone-app-"))
        self.assertEqual(call_kwargs["env"]["APP_NAME"], call_kwargs["name"])
        self.assertEqual(call_kwargs["env"]["MODAL_APP_NAME"], "standalone-app")
        self.assertEqual(call_kwargs["env"]["NO_REPO"], "1")
        self.assertNotIn("GH_REPO", call_kwargs["env"])

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

    def test_startup_script_shallow_clone_depth_limit(self):
        startup_sh = self.repo_root / "shared" / "startup.sh"
        content = startup_sh.read_text()
        self.assertIn("git clone --quiet --depth 50 --branch", content)

    def test_startup_script_does_not_mutate_bashrc_working_directory(self):
        startup_sh = self.repo_root / "shared" / "startup.sh"
        content = startup_sh.read_text()
        self.assertNotIn("cd $TARGET_DIR", content)
        self.assertNotIn('~/.bashrc" || echo "cd', content)

    def test_startup_script_standalone_no_repo_initializes_git_workspace(self):
        import tempfile

        startup_sh = self.repo_root / "shared" / "startup.sh"

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()

            test_script = f"""
            export HOME="{fake_root}"
            export NO_REPO="1"
            export APP_NAME="my-standalone-app"
            export ENABLE_CLOUDFLARE="0"
            sed -e 's|/root|{fake_root}|g' -e 's|/usr/sbin/sshd|true|g' -e 's|exec sleep infinity|exit 0|g' "{startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")
            self.assertIn("No repository secret provided: skipping repository fetch.", res.stdout)
            self.assertIn("Initializing empty Git repository with branch main", res.stdout)
            target_dir = fake_root / "my-standalone-app"
            self.assertTrue(target_dir.is_dir())
            self.assertTrue((target_dir / ".git").is_dir())
            self.assertTrue((target_dir / ".gitignore").is_file())
            gitignore_content = (target_dir / ".gitignore").read_text()
            self.assertIn(".env", gitignore_content)
            self.assertIn("node_modules/", gitignore_content)
            self.assertIn("dist/", gitignore_content)
            self.assertIn(".venv/", gitignore_content)
            self.assertIn("__pycache__/", gitignore_content)

            git_log = subprocess.run(
                ["git", "-C", str(target_dir), "log", "-1", "--pretty=%B"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("initial commit", git_log.stdout)

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

    def test_name_and_secret_mutually_exclusive(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "-s", "dummy", "--name", "my-app"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--name cannot be used with -s/--secret", res.stderr)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_repo_launch_uses_constant_app_name_and_unique_named_sandbox(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        mock_image = MagicMock()
        mock_staged_image = MagicMock()
        mock_image.add_local_dir.return_value = mock_staged_image
        mock_build_image.return_value = mock_image

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-repo-123"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "my-project"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("GH_REPO=owner/my-project")

            parser = create_parser()
            args = parser.parse_args(["-s", "my-project"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_app_lookup.assert_called_once_with("my-project", create_if_missing=True)
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertTrue(call_kwargs["name"].startswith("my-project-"))
        self.assertEqual(call_kwargs["env"]["APP_NAME"], call_kwargs["name"])
        self.assertEqual(call_kwargs["env"]["MODAL_APP_NAME"], "my-project")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_testing_launch_uses_test_prefixed_constant_app(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        mock_image = MagicMock()
        mock_staged_image = MagicMock()
        mock_image.add_local_dir.return_value = mock_staged_image
        mock_build_image.return_value = mock_image

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-test-123"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            org_secrets_dir = Path(tmpdir) / "secrets_org" / "software-factory-09-test"
            org_secrets_dir.mkdir(parents=True)
            (org_secrets_dir / "token").write_text("GITHUB_TOKEN=dummy")

            parser = create_parser()
            args = parser.parse_args(["-s", "software-factory-09-test/test1", "--testing"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_app_lookup.assert_called_once_with("test-test1", create_if_missing=True)
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertTrue(call_kwargs["name"].startswith("test-test1-"))
        self.assertEqual(call_kwargs["env"]["APP_NAME"], call_kwargs["name"])
        self.assertEqual(call_kwargs["env"]["MODAL_APP_NAME"], "test-test1")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_already_exists_error_exits_with_code_1(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        import modal.exception
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox_create.side_effect = modal.exception.AlreadyExistsError("sandbox exists")

        parser = create_parser()
        args = parser.parse_args(["--name", "standalone-app"])

        with self.assertRaises(SystemExit) as cm:
            run_sandbox_launch(args)
        self.assertEqual(cm.exception.code, 1)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_vm_launch_uses_stable_runtime_and_burstable_memory(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-vm-1"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "vm-sandbox-app", "--vm"])
        run_sandbox_launch(args)

        mock_sandbox_create.assert_called_once()
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["runtime"], "vm")
        self.assertEqual(call_kwargs["memory"], (128, 16384))
        self.assertNotIn("experimental_options", call_kwargs)
        self.assertEqual(call_kwargs["env"]["ENABLE_DOCKER"], "1")
        self.assertEqual(call_kwargs["env"]["SWAP_GB"], "2")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_vm_launch_with_memory_soft_deprecation(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        import io
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-vm-2"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "vm-sandbox-app", "--vm", "--memory", "3"])

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            run_sandbox_launch(args)

        self.assertIn("Warning: --memory is deprecated", stderr_buf.getvalue())
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["runtime"], "vm")
        self.assertEqual(call_kwargs["memory"], (128, 16384))
        self.assertEqual(call_kwargs["env"]["SWAP_GB"], "6")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_standard_launch_uses_gvisor_runtime(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-std-1"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        parser = create_parser()
        args = parser.parse_args(["--name", "standard-app"])
        run_sandbox_launch(args)

        mock_sandbox_create.assert_called_once()
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["runtime"], "gvisor")
        self.assertEqual(call_kwargs["memory"], (128, 16384))
        self.assertNotIn("experimental_options", call_kwargs)
        self.assertNotIn("ENABLE_DOCKER", call_kwargs["env"])

    def test_help_contains_full_clone_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--full-clone", res.stdout)

    def test_parser_parses_full_clone_flag(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["-s", "my-secret", "--full-clone"])
        self.assertTrue(args.full_clone)

        args_default = parser.parse_args(["-s", "my-secret"])
        self.assertFalse(args_default.full_clone)

    def test_full_clone_validation(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--name", "my-app", "--full-clone"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--full-clone cannot be used without -s/--secret", res.stderr)

        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--snapshot", "sb-123", "--full-clone"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot cannot be used with launch configuration arguments", res.stderr)

        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--from-snapshot", "im-123", "--name", "my-app", "--full-clone"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--full-clone cannot be used with --from-snapshot", res.stderr)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_full_clone_sets_env_and_feature_in_launch(self, mock_load_pubkey, mock_build_image, mock_app_lookup, mock_sandbox_create):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile
        import io

        mock_image = MagicMock()
        mock_image.add_local_dir.return_value = mock_image
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-full-1"
        mock_sandbox.tunnels.return_value = {}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "full-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("GH_REPO=owner/full-repo")

            parser = create_parser()
            args = parser.parse_args(["-s", "full-repo", "--full-clone"])

            stdout_buf = io.StringIO()
            with patch("sys.stdout", stdout_buf):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

            call_kwargs = mock_sandbox_create.call_args.kwargs
            self.assertEqual(call_kwargs["env"]["FULL_CLONE"], "1")
            self.assertIn("Full Git Clone", stdout_buf.getvalue())

    def test_startup_script_full_clone_support(self):
        startup_sh = self.repo_root / "shared" / "startup.sh"
        content = startup_sh.read_text()
        self.assertIn('if [ "${FULL_CLONE:-0}" = "1" ]; then', content)
        self.assertIn("git clone --quiet --branch", content)
        self.assertIn("git clone --quiet --depth 50 --branch", content)
