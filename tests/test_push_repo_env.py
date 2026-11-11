"""Unit tests for the push_repo_env script."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from scripts.push_repo_env import (
    commit_to_env_store,
    detect_repo_name,
    ensure_gitignore,
    push_repo_env,
)


class TestPushRepoEnv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ensure_gitignore_creates_and_appends(self):
        gitignore = self.repo_dir / ".gitignore"
        # File doesn't exist yet
        updated = ensure_gitignore(self.repo_dir)
        self.assertTrue(updated)
        self.assertTrue(gitignore.is_file())
        self.assertIn(".env*", gitignore.read_text())

        # Calling again should be idempotent
        updated2 = ensure_gitignore(self.repo_dir)
        self.assertFalse(updated2)

    @patch("subprocess.run")
    def test_detect_repo_name_from_git(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "git@github.com:sFactory0/my-open-app.git\n"
        mock_run.return_value = mock_proc

        owner, repo = detect_repo_name(self.repo_dir)
        self.assertEqual(owner, "sFactory0")
        self.assertEqual(repo, "my-open-app")

    @patch("urllib.request.urlopen")
    def test_commit_to_env_store_new_file(self, mock_urlopen):
        # 1. GET returns 404 (file doesn't exist yet)
        get_err = urllib.error.HTTPError(url="http://example", code=404, msg="Not Found", hdrs={}, fp=None)
        # 2. PUT returns 201 (created)
        put_resp = MagicMock()
        put_resp.status = 201
        put_resp.read.return_value = b'{"commit": {"sha": "abc123"}}'

        mock_urlopen.side_effect = [get_err, MagicMock(__enter__=MagicMock(return_value=put_resp))]

        sha = commit_to_env_store(
            owner="sFactory0",
            env_repo="env-store",
            path="my-app/default.env",
            content_bytes=b"SOPS_CIPHERTEXT",
            token="ghp_test",
        )
        self.assertEqual(sha, "abc123")

    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_orchestration(self, mock_encrypt, mock_commit):
        mock_commit.return_value = "commit_sha_123"
        env_file = self.repo_dir / ".env"
        env_file.write_text("API_KEY=hello\nDB_URL=postgres://localhost\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=env_file,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            recipient="age1testkey",
        )

        self.assertTrue(res.success)
        self.assertEqual(res.commit_sha, "commit_sha_123")
        mock_encrypt.assert_called_once()
        mock_commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
