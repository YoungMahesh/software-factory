"""Startup script snapshot-resume tests for Modal Sandboxes."""

from pathlib import Path
import subprocess
import unittest


class TestStartupScriptResume(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_startup_script_contains_resume_snapshot_branches(self):
        content = self.startup_sh.read_text()
        self.assertIn("RESUME_SNAPSHOT", content)
        self.assertIn("Resuming from filesystem snapshot", content)

    def test_startup_script_skips_git_clone_and_discovers_workspace_on_resume(self):
        content = self.startup_sh.read_text()
        self.assertIn('"${RESUME_SNAPSHOT:-0}"', content)
        self.assertIn("for d in /root/*/", content)

    def test_startup_script_syntax_valid(self):
        res = subprocess.run(["bash", "-n", str(self.startup_sh)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in startup.sh: {res.stderr}")

    def test_startup_script_execution_on_resume(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()
            fake_repo = fake_root / "test-repo"
            fake_repo.mkdir()
            (fake_repo / ".git").mkdir()
            (fake_repo / "pnpm-lock.yaml").write_text("lockfile")

            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()

            (fake_bin / "sshd").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "pnpm").write_text("#!/bin/sh\necho 'PNPM CALLED' >&2\nexit 1\n")
            (fake_bin / "git").write_text("#!/bin/sh\necho 'GIT CALLED' >&2\nexit 1\n")
            for cmd in ["sshd", "pnpm", "git"]:
                (fake_bin / cmd).chmod(0o755)

            test_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            unset GH_REPO VIRTUAL_ENV
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export PATH="{fake_bin}:$PATH"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/etc/workspace-target-dir|{fake_root}/etc-workspace-target-dir|g; s|/etc/software-factory-version.json|{fake_root}/etc-software-factory-version.json|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")
            self.assertIn("Resuming from filesystem snapshot", res.stdout)
            self.assertNotIn("PNPM CALLED", res.stderr)
            self.assertNotIn("GIT CALLED", res.stderr)
            self.assertIn(f"Workspace resolved to {fake_repo}", res.stdout)

    def test_startup_script_prefers_saved_target_dir_on_resume(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()

            # Create a directory that comes first alphabetically
            alpha_first = fake_root / "a-repo"
            alpha_first.mkdir()
            (alpha_first / ".git").mkdir()

            real_repo = fake_root / "my-target-project"
            real_repo.mkdir()
            (real_repo / ".git").mkdir()

            (fake_root / ".workspace-target-dir").write_text(str(real_repo))

            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()
            (fake_bin / "sshd").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "pnpm").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "git").write_text("#!/bin/sh\nexit 0\n")
            for cmd in ["sshd", "pnpm", "git"]:
                (fake_bin / cmd).chmod(0o755)

            test_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            unset GH_REPO VIRTUAL_ENV
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export PATH="{fake_bin}:$PATH"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/etc/workspace-target-dir|{fake_root}/etc-workspace-target-dir|g; s|/etc/software-factory-version.json|{fake_root}/etc-software-factory-version.json|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")
            self.assertIn(f"Workspace resolved to {real_repo}", res.stdout)

    def test_startup_script_ignores_backup_directories_on_resume(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()

            # Backup directory that sorts before the main project
            backup_repo = fake_root / "repo-backups"
            backup_repo.mkdir()
            (backup_repo / ".git").mkdir()

            main_repo = fake_root / "software-factory"
            main_repo.mkdir()
            (main_repo / ".git").mkdir()

            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()
            (fake_bin / "sshd").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "pnpm").write_text("#!/bin/sh\nexit 0\n")
            (fake_bin / "git").write_text("#!/bin/sh\nexit 0\n")
            for cmd in ["sshd", "pnpm", "git"]:
                (fake_bin / cmd).chmod(0o755)

            test_script = f"""
            export HOME="{fake_root}"
            export RESUME_SNAPSHOT="1"
            unset GH_REPO VIRTUAL_ENV
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export ENABLE_ANTIGRAVITY="0"
            export ENABLE_OPENCODE="0"
            export ENABLE_MODAL="0"
            export ENABLE_SOPS="0"
            export ENABLE_PI="0"
            export ENABLE_REACT_NATIVE="0"
            export ENABLE_HERDR="0"
            export PATH="{fake_bin}:$PATH"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/etc/workspace-target-dir|{fake_root}/etc-workspace-target-dir|g; s|/etc/software-factory-version.json|{fake_root}/etc-software-factory-version.json|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"startup.sh failed: {res.stderr}\nstdout: {res.stdout}")
            self.assertIn(f"Workspace resolved to {main_repo}", res.stdout)
