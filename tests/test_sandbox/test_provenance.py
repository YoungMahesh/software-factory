"""Unit tests for software-factory git identity and provenance resolution."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.provenance import (
    resolve_host_git_identity,
    resolve_host_software_factory_provenance,
)


class TestHostGitIdentityResolution(unittest.TestCase):
    def test_resolve_from_git_author_env(self):
        with patch.dict(os.environ, {"GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com"}):
            ident = resolve_host_git_identity()
            self.assertEqual(ident.get("GIT_AUTHOR_NAME"), "Alice")
            self.assertEqual(ident.get("GIT_AUTHOR_EMAIL"), "alice@example.com")
            self.assertEqual(ident.get("DEFAULT_GIT_NAME"), "Alice")
            self.assertEqual(ident.get("DEFAULT_GIT_EMAIL"), "alice@example.com")

    def test_resolve_from_default_git_env(self):
        empty_env = {
            "GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": "",
            "GIT_COMMITTER_NAME": "", "GIT_COMMITTER_EMAIL": "",
            "DEFAULT_GIT_NAME": "Default User", "DEFAULT_GIT_EMAIL": "default@example.com",
        }
        with patch.dict(os.environ, empty_env, clear=False):
            ident = resolve_host_git_identity()
            self.assertEqual(ident.get("GIT_AUTHOR_NAME"), "Default User")
            self.assertEqual(ident.get("GIT_AUTHOR_EMAIL"), "default@example.com")
            self.assertEqual(ident.get("DEFAULT_GIT_NAME"), "Default User")
            self.assertEqual(ident.get("DEFAULT_GIT_EMAIL"), "default@example.com")

    def test_resolve_from_dotenv_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / ".env").write_text("DEFAULT_GIT_NAME=DotenvUser\nDEFAULT_GIT_EMAIL=dotenv@example.com\n")
            empty_env = {
                "GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": "",
                "GIT_COMMITTER_NAME": "", "GIT_COMMITTER_EMAIL": "",
                "DEFAULT_GIT_NAME": "", "DEFAULT_GIT_EMAIL": "",
            }
            with patch.dict(os.environ, empty_env, clear=False):
                ident = resolve_host_git_identity(repo_root=repo_root)
                self.assertEqual(ident.get("DEFAULT_GIT_NAME"), "DotenvUser")
                self.assertEqual(ident.get("DEFAULT_GIT_EMAIL"), "dotenv@example.com")

    @patch("subprocess.run")
    def test_resolve_empty_when_unconfigured(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            empty_env = {
                "GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": "",
                "GIT_COMMITTER_NAME": "", "GIT_COMMITTER_EMAIL": "",
                "DEFAULT_GIT_NAME": "", "DEFAULT_GIT_EMAIL": "",
            }
            with patch.dict(os.environ, empty_env, clear=False):
                ident = resolve_host_git_identity(repo_root=repo_root)
                self.assertEqual(ident, {})


class TestSoftwareFactoryProvenanceResolution(unittest.TestCase):
    def test_resolve_provenance_from_env(self):
        env_dict = {
            "SOFTWARE_FACTORY_COMMIT": "1111222233334444555566667777888899990000",
            "SOFTWARE_FACTORY_COMMIT_SHORT": "1111222",
            "SOFTWARE_FACTORY_REF": "release-v2",
            "SOFTWARE_FACTORY_DIRTY": "1",
        }
        with patch.dict(os.environ, env_dict, clear=False):
            prov = resolve_host_software_factory_provenance()
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT"], "1111222233334444555566667777888899990000")
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT_SHORT"], "1111222")
            self.assertEqual(prov["SOFTWARE_FACTORY_REF"], "release-v2")
            self.assertEqual(prov["SOFTWARE_FACTORY_DIRTY"], "1")

    @patch("subprocess.run")
    def test_resolve_provenance_from_git_clean(self, mock_run):
        def fake_run(cmd, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "abcdef1234567890abcdef1234567890abcdef12\n"
            elif cmd == ["git", "rev-parse", "--short", "HEAD"]:
                res.stdout = "abcdef1\n"
            elif cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                res.stdout = "feat/sandbox-provenance\n"
            elif cmd == ["git", "status", "--porcelain"]:
                res.stdout = ""
            else:
                res.stdout = ""
            return res

        mock_run.side_effect = fake_run

        empty_env = {
            "SOFTWARE_FACTORY_COMMIT": "",
            "SOFTWARE_FACTORY_COMMIT_SHORT": "",
            "SOFTWARE_FACTORY_REF": "",
            "SOFTWARE_FACTORY_DIRTY": "",
        }
        with patch.dict(os.environ, empty_env, clear=False):
            prov = resolve_host_software_factory_provenance()
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT"], "abcdef1234567890abcdef1234567890abcdef12")
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT_SHORT"], "abcdef1")
            self.assertEqual(prov["SOFTWARE_FACTORY_REF"], "feat/sandbox-provenance")
            self.assertEqual(prov["SOFTWARE_FACTORY_DIRTY"], "0")

    @patch("subprocess.run")
    def test_resolve_provenance_from_git_dirty(self, mock_run):
        def fake_run(cmd, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "9999999999999999999999999999999999999999\n"
            elif cmd == ["git", "rev-parse", "--short", "HEAD"]:
                res.stdout = "9999999\n"
            elif cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                res.stdout = "main\n"
            elif cmd == ["git", "status", "--porcelain"]:
                res.stdout = " M shared/startup.sh\n"
            else:
                res.stdout = ""
            return res

        mock_run.side_effect = fake_run

        empty_env = {
            "SOFTWARE_FACTORY_COMMIT": "",
            "SOFTWARE_FACTORY_COMMIT_SHORT": "",
            "SOFTWARE_FACTORY_REF": "",
            "SOFTWARE_FACTORY_DIRTY": "",
        }
        with patch.dict(os.environ, empty_env, clear=False):
            prov = resolve_host_software_factory_provenance()
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT"], "9999999999999999999999999999999999999999")
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT_SHORT"], "9999999")
            self.assertEqual(prov["SOFTWARE_FACTORY_REF"], "main")
            self.assertEqual(prov["SOFTWARE_FACTORY_DIRTY"], "1")

    @patch("subprocess.run")
    def test_resolve_provenance_fallback_on_git_failure(self, mock_run):
        mock_run.side_effect = RuntimeError("git not found")

        empty_env = {
            "SOFTWARE_FACTORY_COMMIT": "",
            "SOFTWARE_FACTORY_COMMIT_SHORT": "",
            "SOFTWARE_FACTORY_REF": "",
            "SOFTWARE_FACTORY_DIRTY": "",
        }
        with patch.dict(os.environ, empty_env, clear=False):
            prov = resolve_host_software_factory_provenance()
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT"], "unknown")
            self.assertEqual(prov["SOFTWARE_FACTORY_COMMIT_SHORT"], "unknown")
            self.assertEqual(prov["SOFTWARE_FACTORY_REF"], "unknown")
            self.assertEqual(prov["SOFTWARE_FACTORY_DIRTY"], "0")


if __name__ == "__main__":
    unittest.main()
