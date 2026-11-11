"""Tests for T3 Code pair command wrapper and Modal tunnel synchronization."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TestT3PairWrapper(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.wrapper_script = self.repo_root / "shared" / "t3-wrapper.sh"
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_wrapper_file_exists_and_executable(self):
        self.assertTrue(self.wrapper_script.is_file())
        self.assertTrue(os.access(self.wrapper_script, os.X_OK))

    def test_startup_sh_contains_matching_wrapper_and_background_sync(self):
        content = self.startup_sh.read_text()
        self.assertIn("REAL_T3=\"/opt/t3/t3\"", content)
        self.assertIn("T3_PUBLIC_URL", content)
        self.assertIn("/root/.t3/public_url", content)
        self.assertIn("devUrl", content)
        self.assertIn("Background sync loop to ensure server-runtime.json devUrl matches Modal public tunnel URL", content)
        self.assertIn("seq 1 60", content)

    def test_wrapper_injects_dev_url_from_public_url_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            t3_dir = tmp_path / ".t3" / "userdata"
            t3_dir.mkdir(parents=True)
            runtime_json = t3_dir / "server-runtime.json"
            runtime_json.write_text(
                json.dumps({
                    "version": 1,
                    "pid": 9999,
                    "origin": "http://127.0.0.1:3775",
                    "port": 3775,
                })
            )

            public_url_file = tmp_path / ".t3" / "public_url"
            public_url_file.write_text("https://custom-modal-tunnel.modal.host\n")

            mock_bin = tmp_path / "mock_t3"
            mock_bin.write_text("#!/usr/bin/env bash\necho \"MOCK_ARGS: $@\"\n")
            mock_bin.chmod(0o755)

            script = self.wrapper_script.read_text()
            script = script.replace("/root/.t3", str(tmp_path / ".t3"))
            script = script.replace('"/opt/t3/t3"', f'"{mock_bin}"')

            test_wrapper = tmp_path / "t3"
            test_wrapper.write_text(script)
            test_wrapper.chmod(0o755)

            # Running pair without base-dir from root
            res = subprocess.run([str(test_wrapper), "pair"], capture_output=True, text=True, cwd=str(tmp_path))
            self.assertEqual(res.returncode, 0)
            self.assertIn("MOCK_ARGS: pair", res.stdout)

            data = json.loads(runtime_json.read_text())
            self.assertEqual(data["devUrl"], "https://custom-modal-tunnel.modal.host")

    def test_wrapper_auto_injects_base_dir_in_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            t3_root = tmp_path / "root" / ".t3"
            t3_userdata = t3_root / "userdata"
            t3_userdata.mkdir(parents=True)
            runtime_json = t3_userdata / "server-runtime.json"
            runtime_json.write_text(
                json.dumps({
                    "version": 1,
                    "pid": 9999,
                    "origin": "http://127.0.0.1:3775",
                    "port": 3775,
                })
            )

            public_url_file = t3_root / "public_url"
            public_url_file.write_text("https://modal-tunnel.modal.host\n")

            mock_bin = tmp_path / "mock_t3"
            mock_bin.write_text("#!/usr/bin/env bash\necho \"MOCK_ARGS: $@\"\n")
            mock_bin.chmod(0o755)

            # Subdirectory (e.g. linked worktree) without .t3
            worktree_dir = tmp_path / "root" / "my-repo" / "worktree-1"
            worktree_dir.mkdir(parents=True)

            script = self.wrapper_script.read_text()
            script = script.replace("/root/.t3", str(t3_root))
            script = script.replace('"/opt/t3/t3"', f'"{mock_bin}"')

            test_wrapper = tmp_path / "t3"
            test_wrapper.write_text(script)
            test_wrapper.chmod(0o755)

            # Invoking from worktree_dir
            res = subprocess.run(
                [str(test_wrapper), "pair"],
                capture_output=True,
                text=True,
                cwd=str(worktree_dir),
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn(f"MOCK_ARGS: pair --base-dir {t3_root}", res.stdout)

    def test_wrapper_preserves_explicit_base_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            t3_root = tmp_path / "root" / ".t3"
            t3_userdata = t3_root / "userdata"
            t3_userdata.mkdir(parents=True)
            runtime_json = t3_userdata / "server-runtime.json"
            runtime_json.write_text(
                json.dumps({
                    "version": 1,
                    "pid": 9999,
                    "origin": "http://127.0.0.1:3775",
                    "port": 3775,
                })
            )

            mock_bin = tmp_path / "mock_t3"
            mock_bin.write_text("#!/usr/bin/env bash\necho \"MOCK_ARGS: $@\"\n")
            mock_bin.chmod(0o755)

            custom_base = tmp_path / "custom" / ".t3"
            custom_base.mkdir(parents=True)

            script = self.wrapper_script.read_text()
            script = script.replace("/root/.t3", str(t3_root))
            script = script.replace('"/opt/t3/t3"', f'"{mock_bin}"')

            test_wrapper = tmp_path / "t3"
            test_wrapper.write_text(script)
            test_wrapper.chmod(0o755)

            res = subprocess.run(
                [str(test_wrapper), "pair", "--base-dir", str(custom_base)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn(f"MOCK_ARGS: pair --base-dir {custom_base}", res.stdout)
            self.assertNotIn(str(t3_root), res.stdout)

    def test_wrapper_unsets_gh_repo(self):
        content = self.wrapper_script.read_text()
        self.assertIn("unset GH_REPO", content)

    def test_startup_simulation_isolates_bin_and_does_not_mutate_system_t3(self):
        real_t3_bin = Path("/usr/local/bin/t3")
        if not real_t3_bin.exists():
            self.skipTest("/usr/local/bin/t3 does not exist in test runner environment")
        initial_stat = real_t3_bin.stat()
        initial_mtime = initial_stat.st_mtime_ns

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = Path(tmpdir) / "root"
            fake_root.mkdir()
            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()

            test_script = f"""
            export HOME="{fake_root}"
            export NO_REPO="1"
            export APP_NAME="test-isolation"
            export ENABLE_CLOUDFLARE="0"
            export ENABLE_T3="0"
            export PATH="{fake_bin}:$PATH"
            sed -e 's|/root|{fake_root}|g' \
                -e 's|/usr/local/bin|{fake_bin}|g' \
                -e 's|/usr/sbin/sshd|true|g' \
                -e 's|exec sleep infinity|exit 0|g' \
                "{self.startup_sh}" > "{tmpdir}/run_startup.sh"
            bash "{tmpdir}/run_startup.sh"
            """
            res = subprocess.run(["bash", "-c", test_script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Simulated startup failed: {res.stderr}")

        current_stat = real_t3_bin.stat()
        self.assertEqual(
            current_stat.st_mtime_ns,
            initial_mtime,
            "/usr/local/bin/t3 was unexpectedly mutated by startup simulation!",
        )
