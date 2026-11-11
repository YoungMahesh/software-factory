"""
Tests for developer CLI tooling precedence and dynamic dot-directory resolution.
ADR 0089: developer-cli-tooling-precedence-and-dot-directory-resolution
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from shared.image import (
    LOCAL_AGYPROFILE,
    LOCAL_AGYQ,
    LOCAL_DECRYPT_REPO_ENV,
    LOCAL_ENCRYPT_REPO_ENV,
    LOCAL_GHCLONE,
    LOCAL_GHLS,
    LOCAL_GHPR,
    LOCAL_SCRIPTS_DIR,
    _resolve_dir,
    _resolve_file,
)


class TestDynamicDotDirectoryResolution(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_local_tool_paths_exist_in_repository(self):
        for tool_path in (
            LOCAL_AGYQ,
            LOCAL_GHLS,
            LOCAL_GHPR,
            LOCAL_GHCLONE,
            LOCAL_AGYPROFILE,
            LOCAL_DECRYPT_REPO_ENV,
            LOCAL_ENCRYPT_REPO_ENV,
        ):
            self.assertTrue(tool_path.exists(), f"Tool path {tool_path} must exist")

    def test_resolve_dir_prefers_existing_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            dir_a = base / "dir_a"
            dir_b = base / "dir_b"
            dir_b.mkdir()

            resolved = _resolve_dir(dir_a, dir_b)
            self.assertEqual(resolved, dir_b)

            dir_a.mkdir()
            resolved_first = _resolve_dir(dir_a, dir_b)
            self.assertEqual(resolved_first, dir_a)

    def test_resolve_file_finds_file_across_candidate_directories(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            scripts_dir = base / "scripts"
            dot_scripts_dir = base / ".scripts"
            scripts_dir.mkdir()
            dot_scripts_dir.mkdir()

            (dot_scripts_dir / "tool_in_dot").write_text("echo dot")
            (scripts_dir / "tool_in_std").write_text("echo std")

            found_dot = _resolve_file("tool_in_dot", scripts_dir, dot_scripts_dir)
            self.assertEqual(found_dot, dot_scripts_dir / "tool_in_dot")

            found_std = _resolve_file("tool_in_std", scripts_dir, dot_scripts_dir)
            self.assertEqual(found_std, scripts_dir / "tool_in_std")

    def test_control_plane_dot_directory_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dot_scripts = root / ".scripts"
            dot_secrets = root / ".secrets"
            dot_scripts.mkdir()
            dot_secrets.mkdir()

            (dot_scripts / "agyq").write_text("#!/bin/sh\necho test\n")
            (dot_secrets / "opencode.env").write_text("DUMMY=1\n")

            resolved_scripts = _resolve_dir(
                root / "scripts",
                dot_scripts,
                Path("/root/.scripts"),
            )
            self.assertEqual(resolved_scripts, dot_scripts)

            resolved_secrets = _resolve_dir(
                dot_secrets,
                root / "secrets",
                Path("/root/.secrets"),
            )
            self.assertEqual(resolved_secrets, dot_secrets)

            resolved_agyq = _resolve_file("agyq", resolved_scripts, dot_scripts)
            self.assertEqual(resolved_agyq, dot_scripts / "agyq")


class TestToolingPrecedenceInStartupScript(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_startup_sh_contains_precedence_hierarchy_comments_and_logic(self):
        content = self.startup_sh.read_text()
        self.assertIn("Developer CLI Tooling Precedence:", content)
        self.assertIn("Workspace Repository ($TARGET_DIR/scripts)", content)
        self.assertIn("Staged Dot Directory (/root/.scripts)", content)
        self.assertIn("Pre-baked Image Binary (/usr/local/bin)", content)
        self.assertIn('TARGET_DIR/scripts', content)

    def test_precedence_execution_repo_scripts_override_staged_and_base(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fake_root = tmp / "root"
            fake_root.mkdir()
            fake_bin = tmp / "usr_local_bin"
            fake_bin.mkdir()

            # Staged dot directory with tool
            staged_scripts = fake_root / ".scripts"
            staged_scripts.mkdir()
            (staged_scripts / "agyq").write_text("#!/bin/sh\necho staged\n")
            (staged_scripts / "agyq").chmod(0o755)

            # Target repo with updated tool
            target_repo = fake_root / "software-factory"
            target_repo.mkdir()
            (target_repo / ".git").mkdir()
            target_scripts = target_repo / "scripts"
            target_scripts.mkdir()
            (target_scripts / "agyq").write_text("#!/bin/sh\necho repo-latest\n")
            (target_scripts / "agyq").chmod(0o755)

            # Base image binary in /usr/local/bin
            (fake_bin / "agyq").write_text("#!/bin/sh\necho base-image\n")
            (fake_bin / "agyq").chmod(0o755)

            run_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export GH_REPO="sFactory0/software-factory"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmp}/run_startup.sh"
            bash "{tmp}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", run_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")

            # Verify /usr/local/bin/agyq points to target_repo/scripts/agyq
            agyq_bin = fake_bin / "agyq"
            self.assertTrue(agyq_bin.is_symlink())
            self.assertEqual(agyq_bin.resolve(), (target_scripts / "agyq").resolve())

            # Running agyq outputs repo-latest
            output = subprocess.run([str(agyq_bin)], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(output, "repo-latest")

    def test_precedence_execution_staged_scripts_override_base_when_no_repo_scripts(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fake_root = tmp / "root"
            fake_root.mkdir()
            fake_bin = tmp / "usr_local_bin"
            fake_bin.mkdir()

            # Staged dot directory with tool
            staged_scripts = fake_root / ".scripts"
            staged_scripts.mkdir()
            (staged_scripts / "agyq").write_text("#!/bin/sh\necho staged-tool\n")
            (staged_scripts / "agyq").chmod(0o755)

            # Target repo without scripts directory
            target_repo = fake_root / "other-app"
            target_repo.mkdir()
            (target_repo / ".git").mkdir()

            # Base image binary in /usr/local/bin
            (fake_bin / "agyq").write_text("#!/bin/sh\necho base-image\n")
            (fake_bin / "agyq").chmod(0o755)

            run_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export GH_REPO="sFactory0/other-app"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmp}/run_startup.sh"
            bash "{tmp}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", run_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")

            # Verify /usr/local/bin/agyq points to staged_scripts/agyq
            agyq_bin = fake_bin / "agyq"
            self.assertTrue(agyq_bin.is_symlink())
            self.assertEqual(agyq_bin.resolve(), (staged_scripts / "agyq").resolve())

            # Running agyq outputs staged-tool
            output = subprocess.run([str(agyq_bin)], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(output, "staged-tool")

    def test_no_circular_symlinks_between_scripts_and_bin(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fake_root = tmp / "root"
            fake_root.mkdir()
            fake_bin = tmp / "usr_local_bin"
            fake_bin.mkdir()

            staged_scripts = fake_root / ".scripts"
            staged_scripts.mkdir()

            # Pre-baked base binary
            (fake_bin / "agyq").write_text("#!/bin/sh\necho prebaked\n")
            (fake_bin / "agyq").chmod(0o755)

            # Target repo without scripts
            target_repo = fake_root / "test-app"
            target_repo.mkdir()
            (target_repo / ".git").mkdir()

            run_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export GH_REPO="sFactory0/test-app"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmp}/run_startup.sh"
            bash "{tmp}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", run_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")

            agyq_bin = fake_bin / "agyq"
            # Base binary remains regular file
            self.assertFalse(agyq_bin.is_symlink())
            self.assertEqual(agyq_bin.read_text().strip(), "#!/bin/sh\necho prebaked")

            # Convenience link in .scripts points to fake_bin/agyq
            staged_agyq = staged_scripts / "agyq"
            self.assertTrue(staged_agyq.is_symlink())
            self.assertEqual(staged_agyq.resolve(), agyq_bin.resolve())


if __name__ == "__main__":
    unittest.main()
