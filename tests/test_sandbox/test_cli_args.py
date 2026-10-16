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
