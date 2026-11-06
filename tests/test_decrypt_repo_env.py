"""Unit tests for decrypt-repo-env script."""

from pathlib import Path
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

from scripts.decrypt_repo_env import (
    DecryptResult,
    decrypt_repo_env,
    main as cli_main,
    parse_args,
    parse_env_map,
)


class TestDecryptRepoEnv(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        (self.repo_dir / ".git").mkdir()
        self.secrets_dir = self.repo_dir / ".secrets"
        self.secrets_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_env_map(self):
        env_map_file = self.secrets_dir / "env.map"
        env_map_file.write_text(
            "# Comment line\n"
            "\n"
            "app.env=.env\n"
            "web.env=apps/web/.env\n"
        )
        mappings = parse_env_map(env_map_file)
        self.assertEqual(mappings, [("app.env", ".env"), ("web.env", "apps/web/.env")])

    def test_missing_env_map_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            decrypt_repo_env(repo_path=self.repo_dir)

    @patch("scripts.decrypt_repo_env.run_sops_decrypt")
    def test_decrypt_single_root_env(self, mock_decrypt):
        (self.secrets_dir / "env.map").write_text("app.env=.env\n")
        (self.secrets_dir / "app.env").write_text("ENC_CONTENT")
        mock_decrypt.return_value = "FOO=bar\nBAZ=qux\n"

        results = decrypt_repo_env(repo_path=self.repo_dir)
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.src_rel, "app.env")
        self.assertEqual(res.dest_rel, ".env")
        self.assertTrue(res.written)

        dest_file = self.repo_dir / ".env"
        self.assertTrue(dest_file.is_file())
        self.assertEqual(dest_file.read_text(), "FOO=bar\nBAZ=qux\n")
        # Check permissions 0600
        self.assertEqual(dest_file.stat().st_mode & 0o777, 0o600)

    @patch("scripts.decrypt_repo_env.run_sops_decrypt")
    def test_decrypt_monorepo_subpackages(self, mock_decrypt):
        (self.secrets_dir / "env.map").write_text("web.env=apps/web/.env\napi.env=apps/api/.env\n")
        (self.secrets_dir / "web.env").write_text("ENC_WEB")
        (self.secrets_dir / "api.env").write_text("ENC_API")

        mock_decrypt.side_effect = lambda path, **kwargs: f"DECRYPTED_{path.name}"

        results = decrypt_repo_env(repo_path=self.repo_dir)
        self.assertEqual(len(results), 2)

        web_file = self.repo_dir / "apps" / "web" / ".env"
        api_file = self.repo_dir / "apps" / "api" / ".env"
        self.assertTrue(web_file.is_file())
        self.assertTrue(api_file.is_file())
        self.assertEqual(web_file.read_text(), "DECRYPTED_web.env")
        self.assertEqual(api_file.read_text(), "DECRYPTED_api.env")

    @patch("scripts.decrypt_repo_env.run_sops_decrypt")
    def test_decrypt_mapping_filter(self, mock_decrypt):
        (self.secrets_dir / "env.map").write_text("web.env=apps/web/.env\napi.env=apps/api/.env\n")
        (self.secrets_dir / "web.env").write_text("ENC_WEB")
        (self.secrets_dir / "api.env").write_text("ENC_API")

        mock_decrypt.return_value = "DECRYPTED_WEB"

        results = decrypt_repo_env(repo_path=self.repo_dir, mapping_filter="web.env")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].src_rel, "web.env")
        self.assertFalse((self.repo_dir / "apps" / "api" / ".env").exists())

    @patch("scripts.decrypt_repo_env.run_sops_decrypt")
    def test_file_exists_error_without_force(self, mock_decrypt):
        (self.secrets_dir / "env.map").write_text("app.env=.env\n")
        (self.secrets_dir / "app.env").write_text("ENC_CONTENT")
        (self.repo_dir / ".env").write_text("EXISTING")
        mock_decrypt.return_value = "NEW_CONTENT"

        with self.assertRaises(FileExistsError):
            decrypt_repo_env(repo_path=self.repo_dir, force=False)

        # With force=True, it should overwrite
        results = decrypt_repo_env(repo_path=self.repo_dir, force=True)
        self.assertEqual(len(results), 1)
        self.assertEqual((self.repo_dir / ".env").read_text(), "NEW_CONTENT")

    @patch("scripts.decrypt_repo_env.run_sops_decrypt")
    def test_to_stdout_does_not_write_files(self, mock_decrypt):
        (self.secrets_dir / "env.map").write_text("app.env=.env\n")
        (self.secrets_dir / "app.env").write_text("ENC_CONTENT")
        mock_decrypt.return_value = "STDOUT_CONTENT"

        results = decrypt_repo_env(repo_path=self.repo_dir, to_stdout=True)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].written)
        self.assertFalse((self.repo_dir / ".env").exists())

    def test_parse_args(self):
        args = parse_args(["/path/to/repo", "-m", "app.env", "-f", "-s", "--dry-run"])
        self.assertEqual(args.repo_path, "/path/to/repo")
        self.assertEqual(args.mapping, "app.env")
        self.assertTrue(args.force)
        self.assertTrue(args.stdout)
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    main()
