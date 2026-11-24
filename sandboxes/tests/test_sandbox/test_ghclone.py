"""Tests for ghclone CLI helper script."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


class TestGhClone(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.ghclone_script = self.repo_root / "scripts" / "ghclone"
        self.assertTrue(self.ghclone_script.exists(), "scripts/ghclone must exist")

    def test_help_flag_exits_zero_with_usage(self):
        for flag in ["-h", "--help"]:
            res = subprocess.run(
                [str(self.ghclone_script), flag],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn("Usage: ghclone", res.stdout)
            self.assertIn("GH_ORG_NAME", res.stdout)
            self.assertIn("destination", res.stdout)
            self.assertIn("--no-decrypt", res.stdout)
            self.assertIn("env-store", res.stdout)

    def test_missing_repo_argument_exits_nonzero_with_error(self):
        res = subprocess.run(
            [str(self.ghclone_script)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Error: No repository specified.", res.stderr)
        self.assertIn("Run 'ghclone --help' for details.", res.stderr)

    def _run_with_mocks(
        self,
        args,
        home_dir=None,
        decrypt_exit_code=0,
        use_py_script_name=False,
        extra_env=None,
    ):
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            gh_record_file = temp_path / "gh_args.txt"
            decrypt_record_file = temp_path / "decrypt_args.txt"

            mock_gh = bin_dir / "gh"
            mock_gh_lines = [
                "#!/usr/bin/env bash",
                f'printf "%s\\n" "$@" > "{gh_record_file}"',
            ]
            mock_gh.write_text("\n".join(mock_gh_lines) + "\n")
            mock_gh.chmod(mock_gh.stat().st_mode | stat.S_IXUSR)

            decrypt_name = "pull_repo_env.py" if use_py_script_name else "pull-repo-env"
            mock_decrypt = bin_dir / decrypt_name
            mock_decrypt.write_text(
                "#!/usr/bin/env bash\n"
                f'printf "%s\\n" "$@" > "{decrypt_record_file}"\n'
                f"exit {decrypt_exit_code}\n"
            )
            mock_decrypt.chmod(mock_decrypt.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.setdefault("GH_ORG_NAME", "sFactory0")
            if extra_env:
                env.update(extra_env)
            orig_path = env.get("PATH", "")
            if use_py_script_name:
                orig_path = ":".join(
                    p for p in orig_path.split(":") if not (Path(p) / "pull-repo-env").exists()
                )
            env["PATH"] = f"{bin_dir}:{orig_path}"
            if home_dir:
                env["HOME"] = str(home_dir)

            res = subprocess.run(
                [str(self.ghclone_script)] + args,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            gh_args = gh_record_file.read_text().splitlines() if gh_record_file.exists() else []
            decrypt_args = (
                decrypt_record_file.read_text().splitlines()
                if decrypt_record_file.exists()
                else None
            )
            return res, gh_args, decrypt_args

    def _run_with_mock_gh(self, args, home_dir=None):
        res, gh_args, _ = self._run_with_mocks(args, home_dir=home_dir)
        self.assertEqual(res.returncode, 0, f"Script failed: {res.stderr}")
        return gh_args

    def test_clone_unqualified_repo_resolves_gh_org_name_and_home_dir(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo"], home_dir=home_td)
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/my-repo"]
            )

    def test_clone_unqualified_repo_without_gh_org_name_fails(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, _, _ = self._run_with_mocks(["my-repo"], home_dir=home_td, extra_env={"GH_ORG_NAME": ""})
            self.assertEqual(res.returncode, 1)
            self.assertIn("GH_ORG_NAME is not set", res.stderr)

    def test_clone_qualified_repo_preserves_owner_and_uses_home_dir(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["other-org/project-xyz"], home_dir=home_td)
            self.assertEqual(
                args,
                ["repo", "clone", "other-org/project-xyz", f"{home_td}/project-xyz"],
            )

    def test_clone_with_custom_destination(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(
                ["my-repo", f"{home_td}/custom-dest"], home_dir=home_td
            )
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/custom-dest"]
            )

    def test_clone_with_relative_destination(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "relative-dir"], home_dir=home_td)
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", "relative-dir"]
            )

    def test_clone_with_tilde_destination(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "~"], home_dir=home_td)
            self.assertEqual(args, ["repo", "clone", "sFactory0/my-repo", str(home_td)])

    def test_clone_with_tilde_subpath(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "~/nested/target"], home_dir=home_td)
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/nested/target"]
            )

    def test_clone_with_passthrough_flags(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(
                ["my-repo", "--", "--depth", "1"], home_dir=home_td
            )
            self.assertEqual(
                args,
                [
                    "repo",
                    "clone",
                    "sFactory0/my-repo",
                    f"{home_td}/my-repo",
                    "--",
                    "--depth",
                    "1",
                ],
            )

    def test_clone_with_mixed_passthrough_flags_and_custom_dest(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(
                ["my-repo", f"{home_td}/out", "--depth", "1"], home_dir=home_td
            )
            self.assertEqual(
                args,
                [
                    "repo",
                    "clone",
                    "sFactory0/my-repo",
                    f"{home_td}/out",
                    "--depth",
                    "1",
                ],
            )

    def test_clone_executes_pull_repo_env_by_default(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, gh_args, decrypt_args = self._run_with_mocks(
                ["my-repo"], home_dir=home_td
            )
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                gh_args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/my-repo"]
            )
            self.assertEqual(
                decrypt_args,
                ["--optional", "-r", "my-repo", "-d", f"{home_td}/my-repo/.env", "-o", "sFactory0"],
            )

    def test_clone_with_no_decrypt_flag_skips_pull_repo_env(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, gh_args, decrypt_args = self._run_with_mocks(
                ["my-repo", "--no-decrypt"], home_dir=home_td
            )
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                gh_args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/my-repo"]
            )
            self.assertIsNone(decrypt_args)

    def test_clone_with_skip_decrypt_flag_skips_pull_repo_env(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, gh_args, decrypt_args = self._run_with_mocks(
                ["--skip-decrypt", "my-repo"], home_dir=home_td
            )
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                gh_args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/my-repo"]
            )
            self.assertIsNone(decrypt_args)

    def test_clone_pull_failure_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, gh_args, decrypt_args = self._run_with_mocks(
                ["my-repo"], home_dir=home_td, decrypt_exit_code=1
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertEqual(
                decrypt_args,
                ["--optional", "-r", "my-repo", "-d", f"{home_td}/my-repo/.env", "-o", "sFactory0"],
            )

    def test_clone_executes_pull_repo_env_py_fallback(self):
        with tempfile.TemporaryDirectory() as home_td:
            res, gh_args, decrypt_args = self._run_with_mocks(
                ["my-repo"],
                home_dir=home_td,
                use_py_script_name=True,
            )
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                decrypt_args,
                ["--optional", "-r", "my-repo", "-d", f"{home_td}/my-repo/.env", "-o", "sFactory0"],
            )


if __name__ == "__main__":
    unittest.main()
