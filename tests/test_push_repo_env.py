"""Unit tests for the push_repo_env script."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from scripts.push_repo_env import (
    commit_to_env_store,
    detect_repo_name,
    ensure_gitignore,
    fetch_github_file,
    main,
    push_repo_env,
    push_repo_git_identity,
    update_env_map_content,
)


class TestPushRepoEnv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_env_map_content_new(self):
        content = update_env_map_content(None, "default.env", ".env")
        self.assertEqual(content, "default.env = .env\n")

    def test_update_env_map_content_append(self):
        initial = "default.env = .env\n"
        content = update_env_map_content(initial, "local.env", ".env.local")
        self.assertIn("default.env = .env", content)
        self.assertIn("local.env = .env.local", content)

    def test_update_env_map_content_update_existing(self):
        initial = "default.env = .env\nlocal.env = .env.old\n"
        content = update_env_map_content(initial, "local.env", ".env.local")
        self.assertIn("local.env = .env.local", content)
        self.assertNotIn(".env.old", content)
        self.assertEqual(content.count("local.env"), 1)

    def test_ensure_gitignore_creates_and_appends(self):
        gitignore = self.repo_dir / ".gitignore"
        updated = ensure_gitignore(self.repo_dir)
        self.assertTrue(updated)
        self.assertTrue(gitignore.is_file())
        self.assertIn(".env*", gitignore.read_text())

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
        get_err = urllib.error.HTTPError(url="http://example", code=404, msg="Not Found", hdrs={}, fp=None)
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

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_orchestration(self, mock_encrypt, mock_commit, mock_fetch):
        mock_commit.return_value = "commit_sha_123"
        mock_fetch.return_value = None
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
        self.assertEqual(mock_commit.call_count, 2)
        # Call 1: encrypted default.env
        self.assertEqual(mock_commit.call_args_list[0].kwargs["path"], "my-app/default.env")
        # Call 2: env.map manifest
        self.assertEqual(mock_commit.call_args_list[1].kwargs["path"], "my-app/env.map")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["content_bytes"], b"default.env = .env\n")

    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_custom_env_without_dest_fails(self, mock_encrypt, mock_commit):
        custom_env = self.repo_dir / ".env.local"
        custom_env.write_text("API_KEY=hello\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=custom_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            recipient="age1testkey",
            dest_name=None,
        )

        self.assertFalse(res.success)
        self.assertIn("-d/--dest", res.message)
        mock_encrypt.assert_not_called()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_custom_env_with_dest_succeeds(self, mock_encrypt, mock_commit, mock_fetch):
        mock_commit.return_value = "commit_sha_local"
        mock_fetch.return_value = None
        custom_env = self.repo_dir / ".env.local"
        custom_env.write_text("API_KEY=local_val\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=custom_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            recipient="age1testkey",
            dest_name="local.env",
        )

        self.assertTrue(res.success)
        self.assertEqual(res.target_path, "my-app/local.env")
        mock_encrypt.assert_called_once()
        self.assertEqual(mock_commit.call_count, 2)
        # Call 1: encrypted local.env
        self.assertEqual(mock_commit.call_args_list[0].kwargs["path"], "my-app/local.env")
        # Call 2: env.map
        self.assertEqual(mock_commit.call_args_list[1].kwargs["path"], "my-app/env.map")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["content_bytes"], b"local.env = .env.local\n")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_custom_preserves_existing_default_env(self, mock_encrypt, mock_commit, mock_fetch):
        def fake_fetch(owner, repo, path, token):
            if path == "my-app/default.env":
                return "ENC_CIPHERTEXT"
            return None

        mock_fetch.side_effect = fake_fetch
        mock_commit.return_value = "commit_sha_local"
        custom_env = self.repo_dir / ".env.local"
        custom_env.write_text("API_KEY=local_val\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=custom_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            dest_name="local.env",
        )

        self.assertTrue(res.success)
        map_bytes = mock_commit.call_args_list[1].kwargs["content_bytes"].decode("utf-8")
        self.assertIn("local.env = .env.local", map_bytes)
        self.assertIn("default.env = .env", map_bytes)

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_skips_commit_if_env_map_unchanged(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "default.env = .env\n"
        mock_commit.return_value = "sha1"
        env_file = self.repo_dir / ".env"
        env_file.write_text("FOO=bar\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=env_file,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
        )

        self.assertTrue(res.success)
        # Commit should only be called once for default.env; env.map commit skipped because identical
        self.assertEqual(mock_commit.call_count, 1)

    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_git_identity_success(self, mock_encrypt, mock_commit):
        mock_commit.return_value = "git_sha_456"

        res = push_repo_git_identity(
            repo_dir=self.repo_dir,
            name="Alice Developer",
            email="alice@example.com",
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            recipient="age1testkey",
        )

        self.assertTrue(res.success)
        self.assertEqual(res.commit_sha, "git_sha_456")
        self.assertEqual(res.target_path, "my-app/git.env")
        mock_encrypt.assert_called_once()
        mock_commit.assert_called_once()
        call_kwargs = mock_commit.call_args.kwargs
        self.assertEqual(call_kwargs["path"], "my-app/git.env")

    @patch("subprocess.run")
    def test_push_repo_git_identity_missing_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        with patch.dict(os.environ, {"GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": ""}, clear=False):
            res = push_repo_git_identity(
                repo_dir=self.repo_dir,
                name=None,
                email=None,
                repo_name="my-app",
                org_name="sFactory0",
                gh_token="ghp_test",
            )

        self.assertFalse(res.success)
        self.assertIn("Git author name and email are required", res.message)

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_custom_env_without_dest_rejected(self, mock_push):
        with patch.object(sys, "argv", ["push_repo_env.py", "-e", ".env.local"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertNotEqual(ctx.exception.code, 0)
        mock_push.assert_not_called()

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_custom_env_with_dest_accepted(self, mock_push):
        mock_push.return_value = MagicMock(success=True, target_path="repo/default.env", commit_sha="123", org_name="sFactory0")
        with patch.object(sys, "argv", ["push_repo_env.py", "-e", ".env.local", "-d", "default.env"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        mock_push.assert_called_once()
        self.assertEqual(mock_push.call_args.kwargs["dest_name"], "default.env")


if __name__ == "__main__":
    unittest.main()
