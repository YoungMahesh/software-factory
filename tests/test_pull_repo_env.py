"""Unit tests for the pull_repo_env script."""

from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.env_store import (
    decrypt_sops_payload,
    fetch_vault_env_raw,
    get_file_extension,
    is_sops_supported_format,
)
from scripts.pull_repo_env import main as cli_main, pull_repo_env


class TestPullRepoEnv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sops_supported_format_resolution(self):
        self.assertTrue(is_sops_supported_format("default.env"))
        self.assertTrue(is_sops_supported_format(".env"))
        self.assertTrue(is_sops_supported_format("local.env"))
        self.assertTrue(is_sops_supported_format("config.json"))
        self.assertTrue(is_sops_supported_format("settings.yaml"))
        self.assertTrue(is_sops_supported_format("docker-compose.yml"))
        self.assertTrue(is_sops_supported_format("app.ini"))

        self.assertFalse(is_sops_supported_format(".env.local"))
        self.assertFalse(is_sops_supported_format("local.custom"))
        self.assertFalse(is_sops_supported_format("cert.pem"))
        self.assertFalse(is_sops_supported_format("binary.bin"))
        self.assertFalse(is_sops_supported_format("no_ext_file"))

    @patch("subprocess.run")
    def test_decrypt_sops_payload_passes_filename_override(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "FOO=BAR\n"
        mock_run.return_value = mock_proc

        result = decrypt_sops_payload("CIPHERTEXT", target_filename="local.custom")
        self.assertEqual(result, "FOO=BAR\n")
        cmd_called = mock_run.call_args[0][0]
        self.assertIn("--filename-override", cmd_called)
        self.assertIn("local.custom", cmd_called)

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_raw_passes_target_filename(self, mock_decrypt, mock_fetch):
        mock_fetch.return_value = "CIPHERTEXT"
        mock_decrypt.return_value = "DECRYPTED"

        res = fetch_vault_env_raw(
            repo_name="my-app",
            org_name="sFactory0",
            gh_token="ghp_test",
            age_key="AGE-TEST-KEY",
            target_filename="custom.pem",
        )
        self.assertEqual(res, "DECRYPTED")
        mock_decrypt.assert_called_once_with("CIPHERTEXT", age_private_key="AGE-TEST-KEY", target_filename="custom.pem")

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

    @patch("scripts.pull_repo_env.fetch_vault_env_bundle")
    def test_pull_repo_env_bundle_materialization_and_vault_staging(self, mock_fetch_bundle):
        (self.repo_dir / ".git").mkdir()
        bundle = {
            "env_map_content": "web.env = apps/web/.env\napi.env = packages/api/.env.local\n",
            "mappings": [("web.env", "apps/web/.env"), ("api.env", "packages/api/.env.local")],
            "files": {"web.env": "PORT=3000\n", "api.env": "SECRET=xyz\n"},
        }
        mock_fetch_bundle.return_value = bundle

        success = pull_repo_env(
            repo_name="my-app",
            org_name="sFactory0",
            dest_file=self.repo_dir / ".env",
            gh_token="ghp_test",
        )

        self.assertTrue(success)
        web_env = self.repo_dir / "apps" / "web" / ".env"
        api_env = self.repo_dir / "packages" / "api" / ".env.local"
        self.assertTrue(web_env.is_file())
        self.assertTrue(api_env.is_file())
        self.assertEqual(web_env.read_text(), "PORT=3000\n")
        self.assertEqual(api_env.read_text(), "SECRET=xyz\n")

        vault_dir = self.repo_dir / ".git" / "env-vault"
        self.assertTrue((vault_dir / "env.map").is_file())
        self.assertTrue((vault_dir / "web.env").is_file())
        self.assertTrue((vault_dir / "api.env").is_file())
        self.assertEqual((vault_dir / "env.map").read_text(), bundle["env_map_content"])

    @patch("scripts.pull_repo_env.fetch_vault_env_bundle")
    def test_pull_repo_env_bundle_binary_safe_materialization(self, mock_fetch_bundle):
        (self.repo_dir / ".git").mkdir()
        raw_binary_content = b"\x00\x01\x02\xffBINARY_DATA"
        bundle = {
            "env_map_content": "token.bin = certs/token.bin\n",
            "mappings": [("token.bin", "certs/token.bin")],
            "files": {"token.bin": raw_binary_content},
        }
        mock_fetch_bundle.return_value = bundle

        success = pull_repo_env(
            repo_name="my-app",
            org_name="sFactory0",
            dest_file=self.repo_dir / ".env",
            gh_token="ghp_test",
        )

        self.assertTrue(success)
        token_bin = self.repo_dir / "certs" / "token.bin"
        self.assertTrue(token_bin.is_file())
        self.assertEqual(token_bin.read_bytes(), raw_binary_content)


if __name__ == "__main__":
    unittest.main()
