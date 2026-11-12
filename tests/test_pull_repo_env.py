"""Unit tests for the pull_repo_env script."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.pull_repo_env import pull_repo_env


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


if __name__ == "__main__":
    unittest.main()
