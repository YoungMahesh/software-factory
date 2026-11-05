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
            self.assertIn("sFactory0", res.stdout)
            self.assertIn("destination", res.stdout)

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

    def _run_with_mock_gh(self, args, home_dir=None):
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            record_file = temp_path / "gh_args.txt"

            mock_gh = bin_dir / "gh"
            mock_gh.write_text(
                "#!/usr/bin/env bash\n"
                f'printf "%s\\n" "$@" > "{record_file}"\n'
            )
            mock_gh.chmod(mock_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            if home_dir:
                env["HOME"] = str(home_dir)

            subprocess.run(
                [str(self.ghclone_script)] + args,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            captured_args = record_file.read_text().splitlines()
            return captured_args

    def test_clone_unqualified_repo_defaults_to_sfactory0_and_home_dir(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo"], home_dir=home_td)
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", f"{home_td}/my-repo"]
            )

    def test_clone_qualified_repo_preserves_owner_and_uses_home_dir(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["other-org/project-xyz"], home_dir=home_td)
            self.assertEqual(
                args,
                ["repo", "clone", "other-org/project-xyz", f"{home_td}/project-xyz"],
            )

    def test_clone_with_custom_destination(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "/opt/custom/path"], home_dir=home_td)
            self.assertEqual(
                args, ["repo", "clone", "sFactory0/my-repo", "/opt/custom/path"]
            )

    def test_clone_with_tilde_destination_expansion(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "~/workspace/target"], home_dir=home_td)
            self.assertEqual(
                args,
                ["repo", "clone", "sFactory0/my-repo", f"{home_td}/workspace/target"],
            )

    def test_clone_forwards_additional_git_flags(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(["my-repo", "--", "--depth", "1"], home_dir=home_td)
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

    def test_clone_with_custom_destination_and_additional_flags(self):
        with tempfile.TemporaryDirectory() as home_td:
            args = self._run_with_mock_gh(
                ["other-org/repo", "/tmp/dest", "--", "--branch", "dev"],
                home_dir=home_td,
            )
            self.assertEqual(
                args,
                [
                    "repo",
                    "clone",
                    "other-org/repo",
                    "/tmp/dest",
                    "--",
                    "--branch",
                    "dev",
                ],
            )


if __name__ == "__main__":
    unittest.main()
