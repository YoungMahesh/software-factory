"""Unit tests for the sandbox.env_store module managing Central Environment Store vault resolution."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import warnings

from sandbox.env_store import (
    decrypt_sops_payload,
    fetch_github_file,
    fetch_vault_env,
    fetch_vault_env_bundle,
    fetch_vault_env_raw,
    fetch_vault_git_identity,
    parse_env_map,
    parse_env_text,
    serialize_env_dict,
)


class TestEnvStore(unittest.TestCase):
    def test_parse_env_text(self):
        text = """
        # Comment line
        KEY1=value1
        KEY2="quoted value with = sign"
        KEY3='single quoted'

        EMPTY=
        """
        parsed = parse_env_text(text)
        self.assertEqual(parsed["KEY1"], "value1")
        self.assertEqual(parsed["KEY2"], "quoted value with = sign")
        self.assertEqual(parsed["KEY3"], "single quoted")
        self.assertEqual(parsed["EMPTY"], "")
        self.assertNotIn("# Comment line", parsed)

    def test_serialize_env_dict(self):
        env_dict = {
            "SIMPLE": "value",
            "SPACED": "value with space",
            "SSH_KEY": "ssh-rsa AAAAB3NzaC1yc2EAAA... test@example",
            "QUOTED": "with'quote",
        }
        serialized = serialize_env_dict(env_dict)
        self.assertIn("SIMPLE=value", serialized)
        self.assertIn("SPACED='value with space'", serialized)
        self.assertIn("SSH_KEY='ssh-rsa AAAAB3NzaC1yc2EAAA... test@example'", serialized)
        self.assertIn('QUOTED="with\'quote"', serialized)

    @patch("urllib.request.urlopen")
    def test_fetch_github_file_success_json_base64(self, mock_urlopen):
        import base64
        import json

        mock_resp = MagicMock()
        mock_resp.status = 200
        content_bytes = b"MY_SECRET=encrypted_value"
        payload = {
            "content": base64.b64encode(content_bytes).decode("ascii"),
            "encoding": "base64",
        }
        mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_github_file("sFactory0", "env-store", "my-repo/default.env", token="ghp_test")
        self.assertEqual(result, "MY_SECRET=encrypted_value")

    @patch("urllib.request.urlopen")
    def test_fetch_github_file_404_returns_none(self, mock_urlopen):
        err = urllib.error.HTTPError(
            url="http://example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect = err
        result = fetch_github_file("sFactory0", "env-store", "missing-repo/default.env", token="ghp_test")
        self.assertIsNone(result)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_decrypt_sops_payload(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/sops"
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "PLAINTEXT_KEY=plain_value\n"
        mock_run.return_value = mock_res

        plaintext = decrypt_sops_payload("ENC[AES256_GCM,data:xyz...]", age_private_key="AGE-SECRET-KEY-1XYZ")
        self.assertEqual(plaintext, "PLAINTEXT_KEY=plain_value\n")
        self.assertTrue(mock_run.called)
        cmd, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"].get("SOPS_AGE_KEY"), "AGE-SECRET-KEY-1XYZ")

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_raw_success(self, mock_decrypt, mock_fetch):
        mock_fetch.return_value = "CIPHERTEXT"
        expected_raw = "# Header\nSSH_AUTHORIZED_KEY='ssh-rsa AAAAB3...'\nAPI_KEY=secret\n"
        mock_decrypt.return_value = expected_raw

        raw = fetch_vault_env_raw(
            repo_name="my-cool-app",
            org_name="sFactory0",
            gh_token="ghp_123",
            age_key="AGE-KEY-123",
        )

        self.assertEqual(raw, expected_raw)
        mock_fetch.assert_called_once_with(
            "sFactory0",
            "env-store",
            "my-cool-app/default.env",
            token="ghp_123",
        )

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_success(self, mock_decrypt, mock_fetch):
        mock_fetch.return_value = "CIPHERTEXT"
        mock_decrypt.return_value = "API_KEY=supersecret123\nDB_PASS=dbpass"

        env_dict = fetch_vault_env(
            repo_name="my-cool-app",
            org_name="sFactory0",
            gh_token="ghp_123",
            age_key="AGE-KEY-123",
        )

        self.assertIsNotNone(env_dict)
        self.assertEqual(env_dict["API_KEY"], "supersecret123")
        self.assertEqual(env_dict["DB_PASS"], "dbpass")
        mock_fetch.assert_called_once_with(
            "sFactory0",
            "env-store",
            "my-cool-app/default.env",
            token="ghp_123",
        )

    @patch("sandbox.env_store.fetch_github_file")
    def test_fetch_vault_env_not_found(self, mock_fetch):
        mock_fetch.return_value = None

        env_dict = fetch_vault_env(
            repo_name="nonexistent-app",
            org_name="sFactory0",
            gh_token="ghp_123",
            age_key="AGE-KEY-123",
        )

        self.assertIsNone(env_dict)

    @patch("sandbox.env_store.fetch_vault_env")
    def test_fetch_vault_git_identity_found(self, mock_fetch):
        mock_fetch.return_value = {
            "GIT_AUTHOR_NAME": "Vault Author",
            "GIT_AUTHOR_EMAIL": "vault@example.com",
        }
        res = fetch_vault_git_identity("my-repo", org_name="test-org", gh_token="tok")
        self.assertEqual(res, {"GIT_AUTHOR_NAME": "Vault Author", "GIT_AUTHOR_EMAIL": "vault@example.com"})
        mock_fetch.assert_called_once_with(
            repo_name="my-repo",
            org_name="test-org",
            gh_token="tok",
            age_key=None,
            env_repo_name="env-store",
            target_filename="git.env",
        )

    @patch("sandbox.env_store.fetch_vault_env")
    def test_fetch_vault_git_identity_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        res = fetch_vault_git_identity("missing-repo", org_name="test-org")
        self.assertIsNone(res)

    def test_parse_env_map_valid(self):
        map_content = """
        # Monorepo mapping
        web.env = apps/web/.env
        api.env = packages/api/.env.local
        worker.env = services/worker/.env
        """
        mappings = parse_env_map(map_content)
        self.assertEqual(
            mappings,
            [
                ("web.env", "apps/web/.env"),
                ("api.env", "packages/api/.env.local"),
                ("worker.env", "services/worker/.env"),
            ],
        )

    def test_parse_env_map_encrypted_warns_and_ignores(self):
        encrypted_map = """sops:
            mac: ENC[AES256_GCM,data:abc]
            version: 3.8.1
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mappings = parse_env_map(encrypted_map)
            self.assertEqual(mappings, [])
            self.assertTrue(any("encrypted" in str(item.message).lower() for item in w))

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_bundle_with_map(self, mock_decrypt, mock_fetch):
        def fake_fetch(owner, repo, path, token):
            if path == "my-app/env.map":
                return "web.env = apps/web/.env\napi.env = packages/api/.env\n"
            if path in ("my-app/web.env", "my-app/api.env"):
                return f"ENC_{path}"
            return None

        def fake_decrypt(cipher, age_private_key=None):
            if "web.env" in cipher:
                return "WEB_PORT=3000\n"
            if "api.env" in cipher:
                return "API_KEY=xyz\n"
            return ""

        mock_fetch.side_effect = fake_fetch
        mock_decrypt.side_effect = fake_decrypt

        bundle = fetch_vault_env_bundle("my-app", org_name="sFactory0", gh_token="ghp_1", age_key="key")
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["env_map_content"], "web.env = apps/web/.env\napi.env = packages/api/.env\n")
        self.assertEqual(
            bundle["mappings"],
            [("web.env", "apps/web/.env"), ("api.env", "packages/api/.env")],
        )
        self.assertEqual(bundle["files"]["web.env"], "WEB_PORT=3000\n")
        self.assertEqual(bundle["files"]["api.env"], "API_KEY=xyz\n")

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_bundle_fallback_default_env(self, mock_decrypt, mock_fetch):
        def fake_fetch(owner, repo, path, token):
            if path == "my-app/env.map":
                return None
            if path == "my-app/default.env":
                return "ENC_DEFAULT"
            return None

        mock_fetch.side_effect = fake_fetch
        mock_decrypt.return_value = "SECRET=123\n"

        bundle = fetch_vault_env_bundle("my-app", org_name="sFactory0", gh_token="ghp_1", age_key="key")
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["mappings"], [("default.env", ".env")])
        self.assertEqual(bundle["files"]["default.env"], "SECRET=123\n")
        self.assertEqual(bundle["env_map_content"], "default.env=.env\n")

    @patch("sandbox.env_store.fetch_github_file")
    @patch("sandbox.env_store.decrypt_sops_payload")
    def test_fetch_vault_env_bundle_missing_mapped_file_resilience(self, mock_decrypt, mock_fetch):
        def fake_fetch(owner, repo, path, token):
            if path == "my-app/env.map":
                return "found.env = apps/web/.env\nmissing.env = apps/api/.env\n"
            if path == "my-app/found.env":
                return "ENC_FOUND"
            return None  # missing.env is 404

        mock_fetch.side_effect = fake_fetch
        mock_decrypt.return_value = "FOUND=1\n"

        bundle = fetch_vault_env_bundle("my-app", org_name="sFactory0", gh_token="ghp_1", age_key="key")
        self.assertIsNotNone(bundle)
        self.assertIn("found.env", bundle["files"])
        self.assertNotIn("missing.env", bundle["files"])
        self.assertEqual(bundle["files"]["found.env"], "FOUND=1\n")


if __name__ == "__main__":
    unittest.main()
