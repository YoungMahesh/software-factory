"""Unit tests for env.map-driven multi-file push, prompting, and --all CLI behavior."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.push_repo_env import PushFileOutcome, PushResult, main, push_repo_env


class TestPushRepoEnvManifestSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, rel_path: str, content: str = "KEY=VAL\n") -> Path:
        p = self.repo_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_ignores_local_vault_cache_and_falls_back_to_root_dotenv(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = None
        mock_commit.return_value = "sha_root"
        self._write(".env", "ROOT=1\n")
        self._write(".git/env-vault/env.map", "web.env = apps/web/.env\n")
        self._write("apps/web/.env", "WEB=1\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
        )

        self.assertTrue(res.success)
        self.assertEqual([o.target_path for o in res.pushed_files], ["env/my-app/default.env"])
        self.assertEqual(mock_commit.call_args_list[0].kwargs["path"], "env/my-app/default.env")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["path"], "env/my-app/env.map")
        self.assertEqual(mock_commit.call_args_list[1].kwargs["content_bytes"], b"default.env = .env\n")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_env_map_only_default_env_auto_pushes_without_prompt(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "default.env = .env\n"
        mock_commit.return_value = "sha_1"
        self._write(".env", "ROOT=1\n")
        prompt_mock = MagicMock()

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            prompt_fn=prompt_mock,
        )

        self.assertTrue(res.success)
        prompt_mock.assert_not_called()
        self.assertEqual(mock_commit.call_count, 1)
        self.assertEqual(mock_commit.call_args.kwargs["path"], "env/my-app/default.env")

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_all_flag_pushes_all_mapped_and_unmapped_root_dotenv(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\napi.env = packages/api/.env.local\n"
        mock_commit.side_effect = ["sha_web", "sha_api", "sha_root", "sha_map"]
        self._write("apps/web/.env", "WEB=1\n")
        self._write("packages/api/.env.local", "API=1\n")
        self._write(".env", "ROOT=1\n")
        prompt_mock = MagicMock()

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
            prompt_fn=prompt_mock,
        )

        self.assertTrue(res.success)
        prompt_mock.assert_not_called()
        self.assertEqual(
            [o.target_path for o in res.pushed_files],
            ["env/my-app/web.env", "env/my-app/api.env", "env/my-app/default.env"],
        )
        self.assertEqual(mock_commit.call_count, 4)
        map_bytes = mock_commit.call_args_list[3].kwargs["content_bytes"].decode("utf-8")
        self.assertIn("web.env = apps/web/.env", map_bytes)
        self.assertIn("api.env = packages/api/.env.local", map_bytes)
        self.assertIn("default.env = .env", map_bytes)

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_interactive_prompts_for_each_file_on_tty(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\napi.env = packages/api/.env\n"
        mock_commit.return_value = "sha_web"
        self._write("apps/web/.env", "WEB=1\n")
        self._write("packages/api/.env", "API=1\n")

        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["maybe", "y", ""]):
            res = push_repo_env(
                repo_dir=self.repo_dir,
                repo_name="my-app",
                org_name="sFactory0",
                gh_token="ghp_test",
            )

        self.assertTrue(res.success)
        self.assertEqual([o.target_path for o in res.pushed_files], ["env/my-app/web.env"])
        self.assertEqual(mock_commit.call_count, 1)

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_single_non_root_file_prompts_unless_all(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\n"
        self._write("apps/web/.env", "WEB=1\n")

        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="n") as mock_in:
            res = push_repo_env(
                repo_dir=self.repo_dir,
                repo_name="my-app",
                org_name="sFactory0",
                gh_token="ghp_test",
            )

        self.assertTrue(res.success)
        self.assertTrue(res.declined_all)
        self.assertEqual(res.pushed_files, [])
        mock_in.assert_called_once()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_non_tty_without_all_fails_fast(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\napi.env = packages/api/.env\n"
        self._write("apps/web/.env", "WEB=1\n")
        self._write("packages/api/.env", "API=1\n")

        with patch("sys.stdin.isatty", return_value=False):
            res = push_repo_env(
                repo_dir=self.repo_dir,
                repo_name="my-app",
                org_name="sFactory0",
                gh_token="ghp_test",
            )

        self.assertFalse(res.success)
        self.assertIn("--all", res.message)
        mock_encrypt.assert_not_called()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_skips_missing_local_files_and_keeps_env_map(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\napi.env = packages/api/.env\n"
        mock_commit.return_value = "sha_web"
        self._write("apps/web/.env", "WEB=1\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.skipped_files, ["packages/api/.env"])
        self.assertEqual([o.target_path for o in res.pushed_files], ["env/my-app/web.env"])
        self.assertEqual(mock_commit.call_count, 1)

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_all_mapped_files_missing_fails(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\napi.env = packages/api/.env\n"

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
        )

        self.assertFalse(res.success)
        self.assertIn("None of the files mapped in env.map exist locally", res.message)
        self.assertEqual(res.skipped_files, ["apps/web/.env", "packages/api/.env"])
        mock_encrypt.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_allows_binary_entry_in_env_map(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "default.env = .env\nresource_plane_ssh = .secrets/resource_plane_ssh\n"
        mock_commit.side_effect = ["sha_def", "sha_ssh"]
        self._write(".env", "ROOT=1\n")
        self._write(".secrets/resource_plane_ssh", "SSH_KEY\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
            allow_binary=False,
        )

        self.assertTrue(res.success)
        self.assertEqual(
            [o.target_path for o in res.pushed_files],
            ["env/my-app/default.env", "env/my-app/resource_plane_ssh"],
        )

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_encrypted_env_map_fails_fast(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "sops:\n  mac: ENC[AES256_GCM,data:abc]\n"
        self._write(".env", "ROOT=1\n")

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
        )

        self.assertFalse(res.success)
        self.assertIn("SOPS-encrypted", res.message)
        mock_encrypt.assert_not_called()
        mock_commit.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_rejects_path_traversal_in_env_map(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "evil.env = ../../etc/passwd\n"

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
        )

        self.assertFalse(res.success)
        self.assertIn("escapes repository root", res.message)
        mock_encrypt.assert_not_called()

    @patch("scripts.push_repo_env.fetch_github_file")
    @patch("scripts.push_repo_env.commit_to_env_store")
    @patch("scripts.push_repo_env.run_sops_encrypt")
    def test_bare_push_partial_failure_skips_adding_failed_root_to_env_map(self, mock_encrypt, mock_commit, mock_fetch):
        mock_fetch.return_value = "web.env = apps/web/.env\n"
        self._write("apps/web/.env", "WEB=1\n")
        self._write(".env", "ROOT=1\n")

        def fake_commit(**kwargs):
            if kwargs["path"] == "env/my-app/default.env":
                raise RuntimeError("GitHub API 500")
            return "sha_web"

        mock_commit.side_effect = fake_commit

        res = push_repo_env(
            repo_dir=self.repo_dir,
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            push_all=True,
        )

        self.assertFalse(res.success)
        self.assertEqual([o.target_path for o in res.pushed_files], ["env/my-app/web.env"])
        self.assertEqual([o.target_path for o in res.failed_files], ["env/my-app/default.env"])
        self.assertNotIn("env/my-app/env.map", [c.kwargs["path"] for c in mock_commit.call_args_list])

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_all_flag_and_multi_file_output(self, mock_push):
        mock_push.return_value = PushResult(
            success=True,
            repo_name="my-app",
            target_path="my-app/default.env, my-app/web.env",
            commit_sha="sha2",
            org_name="sFactory0",
            pushed_files=[
                PushFileOutcome("default.env", ".env", "my-app/default.env", True, commit_sha="sha1"),
                PushFileOutcome("web.env", "apps/web/.env", "my-app/web.env", True, commit_sha="sha2"),
            ],
        )
        with patch.object(sys, "argv", ["push_repo_env.py", "--all"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        mock_push.assert_called_once()
        self.assertIsNone(mock_push.call_args.kwargs["env_file"])
        self.assertTrue(mock_push.call_args.kwargs["push_all"])

    @patch("scripts.push_repo_env.push_repo_env")
    def test_main_cli_declined_all_exits_zero(self, mock_push):
        mock_push.return_value = PushResult(
            success=True,
            repo_name="my-app",
            target_path="",
            declined_all=True,
            org_name="sFactory0",
        )
        with patch.object(sys, "argv", ["push_repo_env.py"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
