"""Unit tests for push_repo_env helpers, git authorship, and single-file push."""

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
    main,
    push_repo_env,
    push_repo_git_identity,
    update_env_map_content,
)


class TestPushRepoEnvSingleFile(unittest.TestCase):
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
            env_repo="config",
            path="env/my-app/default.env",
            content_bytes=b"SOPS_CIPHERTEXT",
            token="ghp_test",
        )
        self.assertEqual(sha, "abc123")
        put_req = mock_urlopen.call_args_list[1].args[0]
        self.assertIn(b"chore(my-app): update default.env", put_req.data)

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
        self.assertEqual(mock_commit.call_args_list[0].kwargs["path"], "env/my-app/default.env")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["path"], "env/my-app/env.map")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["content_bytes"], b"default.env = .env\n")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_custom_env_without_dest_fails(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = None
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
    def test_push_repo_env_subpath_dotenv_unmapped_requires_dest(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "default.env = .env\n"
        web_env = self.repo_dir / "apps" / "web" / ".env"
        web_env.parent.mkdir(parents=True)
        web_env.write_text("PORT=3000\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=web_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            dest_name=None,
        )

        self.assertFalse(res.success)
        self.assertIn("-d/--dest", res.message)
        mock_encrypt.assert_not_called()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_single_file_resolves_from_env_map(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "default.env = .env\nweb.env = apps/web/.env\nlocal.env = .env.local\n"
        mock_commit.return_value = "sha_web"
        web_env = self.repo_dir / "apps" / "web" / ".env"
        web_env.parent.mkdir(parents=True)
        web_env.write_text("PORT=3000\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=Path("./apps/web/.env"),
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            dest_name=None,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.target_path, "env/my-app/web.env")
        self.assertEqual(mock_commit.call_count, 1)
        self.assertEqual(mock_commit.call_args.kwargs["path"], "env/my-app/web.env")
        self.assertEqual(mock_encrypt.call_args.kwargs.get("filename_override"), "web.env")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_single_file_ambiguous_env_map_fails(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\nweb2.env = apps/web/.env\n"
        web_env = self.repo_dir / "apps" / "web" / ".env"
        web_env.parent.mkdir(parents=True)
        web_env.write_text("PORT=3000\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=web_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
        )

        self.assertFalse(res.success)
        self.assertIn("Multiple entries in env.map", res.message)
        mock_encrypt.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_single_file_mapped_binary_allowed_implicitly(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "resource_plane_ssh = .secrets/resource_plane_ssh\n"
        mock_commit.return_value = "sha_ssh"
        key_file = self.repo_dir / ".secrets" / "resource_plane_ssh"
        key_file.parent.mkdir(parents=True)
        key_file.write_text("PRIVATE KEY")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=key_file,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            allow_binary=False,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.target_path, "env/my-app/resource_plane_ssh")
        mock_encrypt.assert_called_once()

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
        self.assertEqual(res.target_path, "env/my-app/local.env")
        mock_encrypt.assert_called_once()
        self.assertEqual(mock_commit.call_count, 2)
        self.assertEqual(mock_commit.call_args_list[0].kwargs["path"], "env/my-app/local.env")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["path"], "env/my-app/env.map")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["content_bytes"], b"local.env = .env.local\n")

    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_unknown_extension_without_allow_binary_fails(self, mock_encrypt, mock_commit):
        custom_env = self.repo_dir / ".env.local"
        custom_env.write_text("API_KEY=local_val\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=custom_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            recipient="age1testkey",
            dest_name="local.custom",
        )

        self.assertFalse(res.success)
        self.assertIn("unsupported extension", res.message)
        self.assertIn("--allow-binary", res.message)
        mock_encrypt.assert_not_called()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_unknown_extension_with_allow_binary_succeeds(self, mock_encrypt, mock_commit, mock_fetch):
        mock_commit.return_value = "commit_sha_bin"
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
            dest_name="local.custom",
            allow_binary=True,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.target_path, "env/my-app/local.custom")
        mock_encrypt.assert_called_once()
        self.assertEqual(mock_commit.call_count, 2)

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_passes_filename_override_to_encrypt(self, mock_encrypt, mock_commit, mock_fetch):
        mock_commit.return_value = "commit_sha_override"
        mock_fetch.return_value = None
        custom_env = self.repo_dir / ".env.local"
        custom_env.write_text("API_KEY=val\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            env_file=custom_env,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            dest_name="local.env",
        )

        self.assertTrue(res.success)
        mock_encrypt.assert_called_once()
        self.assertEqual(mock_encrypt.call_args.kwargs.get("filename_override"), "local.env")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_push_repo_env_custom_preserves_existing_default_env(self, mock_encrypt, mock_commit, mock_fetch):
        def fake_fetch(owner, repo, path, token):
            if path == "env/my-app/default.env":
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
        self.assertEqual(res.target_path, "env/my-app/git.env")
        mock_encrypt.assert_called_once()
        mock_commit.assert_called_once()
        self.assertEqual(mock_commit.call_args.kwargs["path"], "env/my-app/git.env")

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
    def test_main_cli_custom_env_without_dest_delegates_to_env_map_lookup(self, mock_push):
        mock_push.return_value = MagicMock(success=True, declined_all=False, pushed_files=[], target_path="repo/local.env", commit_sha="123", org_name="sFactory0")
        with patch.object(sys, "argv", ["push_repo_env.py", "-e", ".env.local"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        mock_push.assert_called_once()
        self.assertEqual(mock_push.call_args.kwargs["env_file"], Path(".env.local"))
        self.assertIsNone(mock_push.call_args.kwargs["dest_name"])

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_custom_env_with_dest_accepted(self, mock_push):
        mock_push.return_value = MagicMock(success=True, declined_all=False, pushed_files=[], target_path="repo/default.env", commit_sha="123", org_name="sFactory0")
        with patch.object(sys, "argv", ["push_repo_env.py", "-e", ".env.local", "-d", "default.env"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        mock_push.assert_called_once()
        self.assertEqual(mock_push.call_args.kwargs["dest_name"], "default.env")

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_allow_binary_flag_passed(self, mock_push):
        mock_push.return_value = MagicMock(success=True, declined_all=False, pushed_files=[], target_path="repo/local.custom", commit_sha="123", org_name="sFactory0")
        with patch.object(sys, "argv", ["push_repo_env.py", "-e", ".env.local", "-d", "local.custom", "--allow-binary"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        mock_push.assert_called_once()
        self.assertTrue(mock_push.call_args.kwargs["allow_binary"])

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_all_with_env_rejected(self, mock_push):
        with patch.object(sys, "argv", ["push_repo_env.py", "--all", "-e", ".env"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertNotEqual(ctx.exception.code, 0)
        mock_push.assert_not_called()
