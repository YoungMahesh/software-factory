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

    @patch("scripts.pull_repo_env.fetch_vault_env")
    def test_pull_repo_env_success(self, mock_fetch):
        mock_fetch.return_value = {
            "SECRET_ONE": "value1",
            "SECRET_TWO": "value2",
        }

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
        self.assertIn("SECRET_ONE=value1", content)
        self.assertIn("SECRET_TWO=value2", content)
        self.assertEqual(oct(dest_file.stat().st_mode)[-3:], "600")

    @patch("scripts.pull_repo_env.fetch_vault_env")
    def test_pull_repo_env_not_found(self, mock_fetch):
        mock_fetch.return_value = None

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
