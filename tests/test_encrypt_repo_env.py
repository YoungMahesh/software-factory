"""Unit tests for encrypt-repo-env script."""

import os
from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from scripts.encrypt_repo_env import (
    DEFAULT_AGE_RECIPIENT,
    EncryptResult,
    encrypt_repo_env,
    main as cli_main,
    parse_args,
    resolve_age_recipient,
    update_env_map,
    update_gitignore,
)


class TestEncryptRepoEnv(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        # Initialize a git repo
        subprocess.run(["git", "init", "-b", "main", str(self.repo_dir)], check=True, capture_output=True)
        # Set git user
        subprocess.run(["git", "-C", str(self.repo_dir), "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "-C", str(self.repo_dir), "config", "user.email", "test@example.com"], check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_age_recipient_precedence(self):
        # 1. Explicit override
        self.assertEqual(resolve_age_recipient("age1custom"), "age1custom")

        # 2. Key file fallback or default
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "age1derived\n"
            mock_run.return_value = mock_proc
            with patch("pathlib.Path.is_file", return_value=True):
                self.assertEqual(resolve_age_recipient(None, key_file=Path("/fake/keys.txt")), "age1derived")

        # 3. Default fallback
        with patch("pathlib.Path.is_file", return_value=False):
            self.assertEqual(resolve_age_recipient(None, key_file=Path("/nonexistent")), DEFAULT_AGE_RECIPIENT)

    def test_update_env_map(self):
        env_map_file = self.repo_dir / ".secrets" / "env.map"
        env_map_file.parent.mkdir(parents=True, exist_ok=True)

        # First entry
        update_env_map(env_map_file, "app.env", ".env")
        self.assertEqual(env_map_file.read_text().strip(), "app.env=.env")

        # Idempotent re-entry
        update_env_map(env_map_file, "app.env", ".env")
        self.assertEqual(env_map_file.read_text().strip(), "app.env=.env")

        # Second entry
        update_env_map(env_map_file, "web.env", "apps/web/.env")
        lines = [line.strip() for line in env_map_file.read_text().splitlines() if line.strip()]
        self.assertEqual(lines, ["app.env=.env", "web.env=apps/web/.env"])

    def test_update_gitignore(self):
        gitignore_file = self.repo_dir / ".gitignore"
        gitignore_file.write_text("node_modules/\ndist/\n")

        changed = update_gitignore(gitignore_file, ".env")
        self.assertTrue(changed)
        content = gitignore_file.read_text()
        self.assertIn(".env", content)

        # Idempotent check
        changed_second = update_gitignore(gitignore_file, ".env")
        self.assertFalse(changed_second)

    @patch("scripts.encrypt_repo_env.run_sops_encrypt")
    @patch("scripts.encrypt_repo_env.verify_sops_decrypt")
    def test_encrypt_repo_env_success_root_env(self, mock_verify, mock_encrypt):
        env_path = self.repo_dir / ".env"
        env_path.write_text("FOO=bar\n")
        # Track .env in git
        subprocess.run(["git", "-C", str(self.repo_dir), "add", ".env"], check=True)
        subprocess.run(["git", "-C", str(self.repo_dir), "commit", "-m", "add .env"], check=True)

        def fake_encrypt(src, dest, recipient):
            dest.write_text("ENC_CONTENT")
        mock_encrypt.side_effect = fake_encrypt
        mock_verify.return_value = True

        result = encrypt_repo_env(
            repo_path=self.repo_dir,
            env_file=env_path,
        )

        self.assertEqual(result.mapping_name, "app.env")
        self.assertEqual(result.dest_rel, ".env")
        self.assertTrue(result.git_untracked)
        self.assertTrue(result.verified)
        self.assertTrue((self.repo_dir / ".secrets" / "app.env").exists())
        self.assertEqual((self.repo_dir / ".secrets" / "env.map").read_text().strip(), "app.env=.env")

        # Check git status: .env should be untracked/deleted from index
        p = subprocess.run(["git", "-C", str(self.repo_dir), "status", "--porcelain"], capture_output=True, text=True)
        self.assertIn("D  .env", p.stdout)

    @patch("scripts.encrypt_repo_env.run_sops_encrypt")
    @patch("scripts.encrypt_repo_env.verify_sops_decrypt")
    def test_encrypt_repo_env_subpath(self, mock_verify, mock_encrypt):
        sub_dir = self.repo_dir / "apps" / "web"
        sub_dir.mkdir(parents=True)
        env_path = sub_dir / ".env"
        env_path.write_text("SUB_VAR=123\n")

        def fake_encrypt(src, dest, recipient):
            dest.write_text("ENC_CONTENT")
        mock_encrypt.side_effect = fake_encrypt
        mock_verify.return_value = True

        result = encrypt_repo_env(
            repo_path=self.repo_dir,
            env_file=env_path,
            mapping_name="web.env",
        )

        self.assertEqual(result.mapping_name, "web.env")
        self.assertEqual(result.dest_rel, "apps/web/.env")
        self.assertTrue((self.repo_dir / ".secrets" / "web.env").exists())
        self.assertEqual((self.repo_dir / ".secrets" / "env.map").read_text().strip(), "web.env=apps/web/.env")

    def test_dry_run_does_not_modify_disk(self):
        env_path = self.repo_dir / ".env"
        env_path.write_text("DRY_RUN=1\n")

        result = encrypt_repo_env(
            repo_path=self.repo_dir,
            env_file=env_path,
            dry_run=True,
        )
        self.assertFalse((self.repo_dir / ".secrets").exists())
        self.assertFalse(result.git_untracked)

    @patch("scripts.encrypt_repo_env.run_sops_encrypt")
    @patch("scripts.encrypt_repo_env.verify_sops_decrypt")
    def test_file_exists_error_without_force(self, mock_verify, mock_encrypt):
        env_path = self.repo_dir / ".env"
        env_path.write_text("A=1\n")
        secrets_dir = self.repo_dir / ".secrets"
        secrets_dir.mkdir()
        (secrets_dir / "app.env").write_text("EXISTING")

        with self.assertRaises(FileExistsError):
            encrypt_repo_env(repo_path=self.repo_dir, env_file=env_path, force=False)

        # With force=True, it should succeed
        mock_verify.return_value = True
        result = encrypt_repo_env(repo_path=self.repo_dir, env_file=env_path, force=True)
        self.assertEqual(result.mapping_name, "app.env")

    def test_invalid_repo_and_missing_env(self):
        non_git_dir = self.repo_dir / "nongit"
        non_git_dir.mkdir()
        with self.assertRaises(ValueError):
            encrypt_repo_env(repo_path=non_git_dir)

        with self.assertRaises(FileNotFoundError):
            encrypt_repo_env(repo_path=self.repo_dir, env_file=self.repo_dir / "missing.env")

    def test_parse_args(self):
        args = parse_args(["/path/to/repo", ".env.custom", "-m", "custom.env", "-d", "custom/.env", "--force", "--dry-run"])
        self.assertEqual(args.repo_path, "/path/to/repo")
        self.assertEqual(args.env_file, ".env.custom")
        self.assertEqual(args.mapping_name, "custom.env")
        self.assertEqual(args.dest, "custom/.env")
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    main()
