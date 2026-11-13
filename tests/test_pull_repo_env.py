"""Unit tests for the pull_repo_env script."""

from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.pull_repo_env import main as cli_main, pull_repo_env


class TestPullRepoEnv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_pull_repo_env_success_preserves_quotes_and_comments(self, mock_fetch_raw):
        mock_raw_env = (
            "# Project configuration\n"
            "SECRET_ONE=value1\n"
            "SSH_AUTHORIZED_KEY='ssh-rsa AAAAB3NzaC1yc2EAAA... test@example'\n"
            'OTHER_KEY="double quoted"\n'
        )
        mock_fetch_raw.return_value = mock_raw_env

        dest_file = self.repo_dir / ".env"
        success = pull_repo_env(
            repo_name="my-app",
            org_name="sFactory0",
            dest_file=dest_file,
            gh_token="ghp_test",
            age_key="AGE-KEY-123",
        )

        self.assertTrue(success)
        self.assertTrue(dest_file.is_file())
        content = dest_file.read_text()
        self.assertEqual(content, mock_raw_env)
        self.assertIn("SSH_AUTHORIZED_KEY='ssh-rsa AAAAB3NzaC1yc2EAAA... test@example'", content)
        self.assertIn("# Project configuration", content)
        self.assertEqual(oct(dest_file.stat().st_mode)[-3:], "600")

    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_pull_repo_env_not_found(self, mock_fetch_raw):
        mock_fetch_raw.return_value = None

        dest_file = self.repo_dir / ".env"
        success = pull_repo_env(
            repo_name="missing-app",
            org_name="sFactory0",
            dest_file=dest_file,
            gh_token="ghp_test",
        )

        self.assertFalse(success)
        self.assertFalse(dest_file.is_file())

    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_pull_repo_env_optional_when_not_found(self, mock_fetch_raw):
        mock_fetch_raw.return_value = None

        dest_file = self.repo_dir / ".env"
        success = pull_repo_env(
            repo_name="missing-app",
            org_name="sFactory0",
            dest_file=dest_file,
            gh_token="ghp_test",
            optional=True,
        )

        self.assertFalse(success)
        self.assertFalse(dest_file.is_file())

    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_pull_repo_env_optional_on_decryption_error(self, mock_fetch_raw):
        mock_fetch_raw.side_effect = RuntimeError("SOPS decryption failed: missing private key")

        dest_file = self.repo_dir / ".env"
        success = pull_repo_env(
            repo_name="secure-app",
            org_name="sFactory0",
            dest_file=dest_file,
            gh_token="ghp_test",
            optional=True,
        )

        self.assertFalse(success)
        self.assertFalse(dest_file.is_file())

    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_cli_optional_flag_exits_zero_on_missing(self, mock_fetch_raw):
        mock_fetch_raw.return_value = None
        dest_file = self.repo_dir / ".env"

        test_args = [
            "pull_repo_env.py",
            "-r", "missing-app",
            "-o", "sFactory0",
            "-t", "ghp_test",
            "-d", str(dest_file),
            "--optional",
        ]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                cli_main()
            self.assertEqual(cm.exception.code, 0)


    @patch("subprocess.run")
    @patch("scripts.pull_repo_env.fetch_vault_git_identity")
    @patch("scripts.pull_repo_env.fetch_vault_env_raw")
    def test_pull_repo_env_configures_local_git_author_when_git_env_present(
        self, mock_fetch_raw, mock_fetch_git, mock_run
    ):
        mock_fetch_raw.return_value = "API_KEY=123\n"
        mock_fetch_git.return_value = {
            "GIT_AUTHOR_NAME": "Repo User",
            "GIT_AUTHOR_EMAIL": "repo@example.com",
        }
        (self.repo_dir / ".git").mkdir()
        dest_file = self.repo_dir / ".env"

        success = pull_repo_env(
            repo_name="my-app",
            org_name="sFactory0",
            dest_file=dest_file,
            gh_token="ghp_test",
        )

        self.assertTrue(success)
        self.assertEqual(dest_file.read_text(), "API_KEY=123\n")
        self.assertNotIn("GIT_AUTHOR_NAME", dest_file.read_text())
        mock_run.assert_any_call(
            ["git", "-C", str(self.repo_dir), "config", "--local", "user.name", "Repo User"],
            check=False,
        )
        mock_run.assert_any_call(
            ["git", "-C", str(self.repo_dir), "config", "--local", "user.email", "repo@example.com"],
            check=False,
        )


if __name__ == "__main__":

    unittest.main()
