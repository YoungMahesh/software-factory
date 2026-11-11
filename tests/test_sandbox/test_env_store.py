"""Unit tests for the sandbox.env_store module managing Central Environment Store vault resolution."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from sandbox.env_store import (
    decrypt_sops_payload,
    fetch_github_file,
    fetch_vault_env,
    parse_env_text,
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


if __name__ == "__main__":
    unittest.main()
