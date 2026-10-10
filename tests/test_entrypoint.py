from pathlib import Path
import subprocess
import unittest


class TestFactoryEntrypointScript(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.entrypoint_script = self.repo_root / "shared" / "factory_entrypoint.sh"

    def test_script_exists_and_executable(self):
        self.assertTrue(self.entrypoint_script.is_file())

    def test_bash_syntax_valid(self):
        res = subprocess.run(
            ["bash", "-n", str(self.entrypoint_script)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Bash syntax error: {res.stderr}")

    def test_help_flag(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--feature <slug>", res.stdout)

    def test_missing_feature_fails(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Feature slug is required", res.stderr)

    def test_missing_age_key_fails(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--feature", "test-feat"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("AGE_PRIVATE_KEY is not set", res.stderr)


    def test_help_flag_includes_dev(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--dev", res.stdout)

    def test_dev_preview_banner_displayed(self):
        # Even if it stops at missing AGE_PRIVATE_KEY, the startup banner prints before Step 1
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--feature", "test-feat", "--dev"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertIn("Dev Preview:", res.stdout)
        self.assertIn("Enabled", res.stdout)

    def _setup_mock_sandbox_root(self, tmpdir: Path, pipeline_exit: int = 0, with_cloudflare: bool = True):
        bin_dir = tmpdir / "bin"
        bin_dir.mkdir(parents=True)
        log_file = tmpdir / "mock_calls.log"

        # Mock node
        node_bin = bin_dir / "node"
        node_bin.write_text(f"""#!/usr/bin/env bash
echo "node $@" >> "{log_file}"
exit {pipeline_exit}
""")
        node_bin.chmod(0o755)

        # Mock pnpm
        pnpm_bin = bin_dir / "pnpm"
        pnpm_bin.write_text(f"""#!/usr/bin/env bash
echo "pnpm $@" >> "{log_file}"
if [ "$1" = "dev" ]; then
    echo "pnpm dev started" >> "{log_file}"
    echo "ALLOWED_HOSTS=$__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS" >> "{log_file}"
    # Keep alive until terminated
    while true; do
        sleep 0.1
    done
fi
exit 0
""")
        pnpm_bin.chmod(0o755)

        # Mock git
        git_bin = bin_dir / "git"
        git_bin.write_text(f"""#!/usr/bin/env bash
echo "git $@" >> "{log_file}"
exit 0
""")
        git_bin.chmod(0o755)

        # Mock sops
        sops_bin = bin_dir / "sops"
        sops_bin.write_text("""#!/usr/bin/env bash
if [ "$1" = "decrypt" ]; then
    if [[ "$*" == *"CF_TOKEN"* ]]; then
        echo "mock-cf-token"
    else
        echo "GH_REPO=software-factory-09-test/test-repo"
        echo "GH_TOKEN=dummy-token"
    fi
fi
exit 0
""")
        sops_bin.chmod(0o755)

        # Mock cloudflared
        cf_bin = bin_dir / "cloudflared"
        cf_bin.write_text("""#!/usr/bin/env bash
exit 0
""")
        cf_bin.chmod(0o755)

        # Setup mock directories
        repo_secrets = tmpdir / "secrets" / "repo"
        repo_secrets.mkdir(parents=True)
        (repo_secrets / "fetch.env").write_text("GH_REPO=test-org/test-repo\nGH_TOKEN=fake-token\n")

        if with_cloudflare:
            (tmpdir / "secrets" / "cloudflare.env").write_text("CF_TOKEN=mock-token\n")

        factory_dir = tmpdir / "factory"
        factory_dir.mkdir(parents=True)
        (factory_dir / "node_modules").mkdir(parents=True)
        (factory_dir / "pipeline.ts").write_text("// dummy")

        target_dir = tmpdir / "test-repo"
        target_dir.mkdir(parents=True)
        (target_dir / "node_modules").mkdir(parents=True)
        (target_dir / "package.json").write_text('{"name": "test-repo"}')

        import os
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '/usr/bin:/bin')}"
        env["SANDBOX_ROOT"] = str(tmpdir)
        env["HOME"] = str(tmpdir)
        env["AGE_PRIVATE_KEY"] = "AGE-SECRET-KEY-MOCK"

        return env, log_file, target_dir

    def test_post_verification_dev_server_disabled_by_default(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, log_file, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=0)
            res = subprocess.run(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn("Pipeline completed with exit code: 0", res.stdout)
            logs = log_file.read_text()
            self.assertIn("node", logs)
            self.assertNotIn("pnpm dev", logs)

    def test_post_verification_dev_server_skipped_when_pipeline_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, log_file, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=1)
            res = subprocess.run(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat", "--dev"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Pipeline completed with exit code: 1", res.stdout)
            logs = log_file.read_text()
            self.assertIn("node", logs)
            self.assertNotIn("pnpm dev", logs)

    def test_post_verification_dev_server_launches_and_terminates_cleanly(self):
        import tempfile
        import time
        import signal
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, log_file, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=0)
            proc = subprocess.Popen(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat", "--dev"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            # Wait for dev server to start
            started = False
            for _ in range(50):
                time.sleep(0.1)
                if log_file.exists() and "pnpm dev started" in log_file.read_text():
                    started = True
                    break

            self.assertTrue(started, "Dev server failed to start within timeout.")

            # Process should be alive in keep-alive serving state
            self.assertIsNone(proc.poll(), "Entrypoint terminated prematurely instead of keeping alive.")

            # Terminate entrypoint with SIGTERM (simulating modal.Sandbox.terminate())
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=5)

            self.assertEqual(proc.returncode, 0)
            self.assertIn("Dev Preview Keep-Alive Daemon", stdout)
            self.assertIn("https://3000.mahesh0.dev", stdout)
            self.assertIn("pnpm dev --port 3000 --host 0.0.0.0", log_file.read_text())

    def test_cloudflare_tunnel_configured_in_dev_mode(self):
        import tempfile
        import time
        import signal
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, log_file, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=0)
            # Create mock cloudflare secret
            (tmpdir / "secrets" / "cloudflare.env").write_text("CF_TOKEN=mock-token\n")

            proc = subprocess.Popen(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(env, DEV_PREVIEW="1"),
            )

            # Wait for dev server to start
            for _ in range(50):
                time.sleep(0.1)
                if log_file.exists() and "pnpm dev started" in log_file.read_text():
                    break

            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=5)

            combined = stdout + stderr
            self.assertIn("Cloudflare Tunnel", combined)
            self.assertIn("3000.mahesh0.dev", stdout)
            self.assertIn("port 3000", combined.lower())

    def test_cloudflare_tunnel_missing_secret_fails_fast(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, _, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=0, with_cloudflare=False)
            # Notice: no secrets/cloudflare.env created!

            res = subprocess.run(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat", "--dev"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Cloudflare Tunnel secret file not found", res.stderr)

    def _run_dev_preview_server(self, env_overrides: dict[str, str] | None = None) -> str:
        import signal
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            env, log_file, _ = self._setup_mock_sandbox_root(tmpdir, pipeline_exit=0)
            if env_overrides is not None:
                env.update(env_overrides)
            else:
                env.pop("__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS", None)

            proc = subprocess.Popen(
                ["bash", str(self.entrypoint_script), "--feature", "test-feat", "--dev"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            for _ in range(50):
                time.sleep(0.1)
                if log_file.exists() and "pnpm dev started" in log_file.read_text():
                    break

            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=5)
            return log_file.read_text()

    def test_dev_preview_exports_fallback_allowed_hosts(self):
        logs = self._run_dev_preview_server()
        self.assertIn("ALLOWED_HOSTS=.modal.host,3000.mahesh0.dev", logs)

    def test_dev_preview_preserves_custom_allowed_hosts(self):
        logs = self._run_dev_preview_server(
            {"__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": "custom.modal.host,3000.mahesh0.dev"}
        )
        self.assertIn("ALLOWED_HOSTS=custom.modal.host,3000.mahesh0.dev", logs)


if __name__ == "__main__":
    unittest.main()
