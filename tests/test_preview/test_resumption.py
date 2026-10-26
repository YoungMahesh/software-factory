"""Subsystem tests for fast-path sandbox resumption and instant cold starts."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from factory.spawner import (
    PreviewSpawnConfig,
    create_preview_sandbox,
)
from factory.ui.db import StudioDatabase
from factory.ui.registry import (
    PreviewRegistry,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)
from factory.ui.registry._snapshot import (
    resolve_snapshot_image_id,
    spawn_preview_sandbox_with_fallback,
)


class TestPreviewSpawnerResumption(unittest.TestCase):
    """Tests for PreviewSpawnConfig and create_preview_sandbox snapshot support."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_preview_spawn_config_snapshot_defaults(self):
        config = PreviewSpawnConfig(repo="test3")
        self.assertIsNone(config.from_snapshot)
        self.assertFalse(config.snapshot_resume)

    def test_preview_spawn_config_snapshot_explicit(self):
        config = PreviewSpawnConfig(
            repo="test3",
            from_snapshot="im-snap-abc123",
            snapshot_resume=True,
        )
        self.assertEqual(config.from_snapshot, "im-snap-abc123")
        self.assertTrue(config.snapshot_resume)

    @patch("modal.App.lookup")
    @patch("modal.Image.from_id")
    @patch("modal.Sandbox.create")
    @patch("factory.spawner._preview.build_factory_image")
    def test_create_preview_sandbox_from_snapshot(
        self,
        mock_build_image,
        mock_sandbox_create,
        mock_image_from_id,
        mock_app_lookup,
    ):
        mock_app = MagicMock()
        mock_app_lookup.return_value = mock_app

        mock_snapshot_image = MagicMock()
        mock_image_from_id.return_value = mock_snapshot_image

        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://warm-preview.modal.host"
        mock_sandbox = MagicMock()
        mock_sandbox.tunnels.return_value = {3000: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        config = PreviewSpawnConfig(
            repo="test3",
            branch="factory/fast-branch",
            testing=True,
            repo_root=self.repo_root,
            from_snapshot="im-snap-abc123",
            snapshot_resume=True,
        )

        sandbox, url = create_preview_sandbox(config)

        self.assertEqual(sandbox, mock_sandbox)
        self.assertEqual(url, "https://warm-preview.modal.host")

        # Snapshot image resolved directly via from_id
        mock_image_from_id.assert_called_once_with("im-snap-abc123")
        mock_build_image.assert_not_called()

        # Verify Sandbox.create call
        mock_sandbox_create.assert_called_once()
        args, kwargs = mock_sandbox_create.call_args

        # Entrypoint args must have --preview-only, --branch, and --snapshot-resume
        self.assertEqual(args[0], "bash")
        self.assertIn("--preview-only", args)
        self.assertIn("--branch", args)
        self.assertIn("factory/fast-branch", args)
        self.assertIn("--snapshot-resume", args)

        # Keyword arguments: image is the snapshot image
        self.assertEqual(kwargs["image"], mock_snapshot_image)
        self.assertEqual(kwargs["encrypted_ports"], [3000])

        # Environment has SNAPSHOT_RESUME=1
        env = kwargs["env"]
        self.assertEqual(env["SNAPSHOT_RESUME"], "1")
        self.assertEqual(env["DEV_PREVIEW"], "1")
        self.assertEqual(env["PORT"], "3000")
        self.assertEqual(env["BRANCH"], "factory/fast-branch")


class TestRegistrySnapshotResolutionAndFallback(unittest.TestCase):
    """Tests for resolving snapshot IDs and fallback handling in PreviewRegistry."""

    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def test_resolve_snapshot_image_id_from_db(self):
        self.db.save_snapshot_metadata("my-app", "im-snap-db", "commit123")
        resolved = resolve_snapshot_image_id(self.db, "my-app")
        self.assertEqual(resolved, "im-snap-db")

    def test_resolve_snapshot_image_id_from_preview_state(self):
        preview = PreviewState(repo="my-app", snapshot_image_id="im-snap-preview")
        resolved = resolve_snapshot_image_id(None, "my-app", preview=preview)
        self.assertEqual(resolved, "im-snap-preview")

    def test_resolve_snapshot_image_id_none_when_empty(self):
        resolved = resolve_snapshot_image_id(self.db, "nonexistent-app")
        self.assertIsNone(resolved)

    def test_spawn_with_snapshot_fast_path(self):
        self.db.save_snapshot_metadata("fast-app", "im-warm-1", "commit1")
        mock_create = MagicMock()
        mock_sb = MagicMock()
        mock_create.return_value = (mock_sb, "https://fast-app.modal.host")

        log_messages = []
        sb, url = spawn_preview_sandbox_with_fallback(
            create_preview_fn=mock_create,
            repo="fast-app",
            branch="feature-a",
            db=self.db,
            on_log=lambda m: log_messages.append(m),
        )

        self.assertEqual(sb, mock_sb)
        self.assertEqual(url, "https://fast-app.modal.host")
        mock_create.assert_called_once()
        passed_config = mock_create.call_args[0][0]
        self.assertEqual(passed_config.from_snapshot, "im-warm-1")
        self.assertTrue(passed_config.snapshot_resume)
        self.assertEqual(passed_config.branch, "feature-a")
        self.assertTrue(any("Fast-path" in m for m in log_messages))

    def test_spawn_with_fallback_on_expired_or_corrupt_snapshot(self):
        self.db.save_snapshot_metadata("broken-snap-app", "im-expired-999", "commit1")
        mock_sb_fallback = MagicMock()

        call_count = 0

        def side_effect(config: PreviewSpawnConfig):
            nonlocal call_count
            call_count += 1
            if config.from_snapshot:
                raise RuntimeError("Image im-expired-999 not found or expired")
            return mock_sb_fallback, "https://fallback.modal.host"

        mock_create = MagicMock(side_effect=side_effect)

        log_messages = []
        sb, url = spawn_preview_sandbox_with_fallback(
            create_preview_fn=mock_create,
            repo="broken-snap-app",
            branch="main",
            db=self.db,
            on_log=lambda m: log_messages.append(m),
        )

        self.assertEqual(sb, mock_sb_fallback)
        self.assertEqual(url, "https://fallback.modal.host")
        self.assertEqual(mock_create.call_count, 2)

        # First call was snapshot fast-path
        first_config = mock_create.call_args_list[0][0][0]
        self.assertEqual(first_config.from_snapshot, "im-expired-999")
        self.assertTrue(first_config.snapshot_resume)

        # Second call was fallback clean build
        second_config = mock_create.call_args_list[1][0][0]
        self.assertIsNone(second_config.from_snapshot)
        self.assertFalse(second_config.snapshot_resume)

        # Warning logged to preview stream
        self.assertTrue(any("Snapshot resumption failed" in m for m in log_messages))
        self.assertTrue(any("Building base image" in m for m in log_messages))

    def test_spawn_without_snapshot_uses_clean_build(self):
        mock_sb = MagicMock()
        mock_create = MagicMock(return_value=(mock_sb, "https://clean.modal.host"))

        sb, url = spawn_preview_sandbox_with_fallback(
            create_preview_fn=mock_create,
            repo="fresh-app",
            branch="main",
            db=self.db,
        )

        self.assertEqual(sb, mock_sb)
        mock_create.assert_called_once()
        config = mock_create.call_args[0][0]
        self.assertIsNone(config.from_snapshot)
        self.assertFalse(config.snapshot_resume)

    @patch("factory.ui.registry._preview.spawn_preview_sandbox_with_fallback")
    def test_registry_launch_preview_invokes_fallback_spawner(self, mock_fallback_spawner):
        mock_sandbox = MagicMock()
        mock_sandbox.stdout = iter([])
        mock_sandbox.stderr = iter([])
        mock_sandbox.returncode = 0
        mock_fallback_spawner.return_value = (mock_sandbox, "https://preview.modal.host")

        registry = PreviewRegistry(db=self.db)
        self.db.save_snapshot_metadata("test-app", "im-snap-reg", "sha123")

        preview = registry.launch_preview("test-app", branch="main")
        if hasattr(preview, "_thread") and preview._thread is not None:
            preview._thread.join(timeout=2.0)

        mock_fallback_spawner.assert_called_once()
        kwargs = mock_fallback_spawner.call_args[1]
        self.assertEqual(kwargs["repo"], "test-app")
        self.assertEqual(kwargs["branch"], "main")
        self.assertEqual(kwargs["db"], self.db)


class TestContainerEntrypointResumption(unittest.TestCase):
    """Tests for shared/factory_entrypoint.sh snapshot resumption logic."""

    def setUp(self):
        self.script_path = Path(__file__).resolve().parents[2] / "shared" / "factory_entrypoint.sh"

    def test_entrypoint_parses_snapshot_resume_flag(self):
        # Run bash script with -h or --help and check options
        res = subprocess.run(
            ["bash", str(self.script_path), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--snapshot-resume", res.stdout)

    def _create_mock_environment(self, tmpdir_path: Path):
        bin_dir = tmpdir_path / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)

        pnpm_script = bin_dir / "pnpm"
        pnpm_script.write_text(
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = \"dev\" ]; then\n"
            "    echo 'MOCK_PNPM_DEV_STARTED'\n"
            "    exit 0\n"
            "elif [ \"$1\" = \"install\" ]; then\n"
            "    echo \"MOCK_PNPM_INSTALL_CALLED $*\"\n"
            "    exit 0\n"
            "fi\n"
            "exit 0\n"
        )
        pnpm_script.chmod(0o755)

        factory_env = tmpdir_path / ".factory.env"
        factory_env.write_text(
            "export GH_TOKEN=\"dummy_gh_token\"\n"
            "export GH_REPO=\"software-factory-09-test/test-app\"\n"
        )
        factory_env.chmod(0o600)
        return bin_dir, factory_env

    def _init_local_git_repo(self, repo_dir: Path, package_json_content: str = '{"name":"test-app","version":"1.0.0"}'):
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo_dir, check=True)
        (repo_dir / "package.json").write_text(package_json_content)
        (repo_dir / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    def test_entrypoint_snapshot_resume_without_drift(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            bin_dir, _ = self._create_mock_environment(tmpdir)
            repo_dir = tmpdir / "test-app"
            self._init_local_git_repo(repo_dir)

            env = dict(
                os.environ,
                PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
                SANDBOX_ROOT=str(tmpdir),
                HOME=str(tmpdir),
                SNAPSHOT_RESUME="1",
                PREVIEW_ONLY="1",
                DEV_PREVIEW="1",
                DEV_PREVIEW_ONCE="1",
                BRANCH="main",
            )

            res = subprocess.run(
                ["bash", str(self.script_path), "--preview-only", "--snapshot-resume", "--branch", "main"],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(res.returncode, 0, f"Script failed with output:\n{res.stdout}\n{res.stderr}")
            self.assertIn("Snapshot fast-path resumption requested", res.stdout)
            self.assertIn("No dependency manifest drift detected; skipping package installation", res.stdout)
            self.assertIn("Fast-path snapshot resumption successful", res.stdout)
            self.assertIn("MOCK_PNPM_DEV_STARTED", res.stdout)
            self.assertNotIn("Cloning software-factory-09-test/test-app", res.stdout)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_entrypoint_snapshot_resume_with_drift(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            bin_dir, _ = self._create_mock_environment(tmpdir)
            repo_dir = tmpdir / "test-app"
            self._init_local_git_repo(repo_dir, '{"name":"test-app","version":"1.0.0"}')

            # Create a remote bare repository with a new branch having modified package.json
            remote_dir = tmpdir / "remote.git"
            subprocess.run(["git", "clone", "--bare", str(repo_dir), str(remote_dir)], check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", str(remote_dir)], cwd=repo_dir, check=True)

            # Create a second working tree to push a branch update to remote
            worker_dir = tmpdir / "worker"
            subprocess.run(["git", "clone", str(remote_dir), str(worker_dir)], check=True, capture_output=True)
            subprocess.run(["git", "checkout", "-b", "feature-drift"], cwd=worker_dir, check=True, capture_output=True)
            (worker_dir / "package.json").write_text('{"name":"test-app","version":"2.0.0","dependencies":{"react":"18"}}')
            subprocess.run(["git", "add", "package.json"], cwd=worker_dir, check=True)
            subprocess.run(["git", "commit", "-m", "Bump deps"], cwd=worker_dir, check=True)
            subprocess.run(["git", "push", "origin", "feature-drift"], cwd=worker_dir, check=True)

            env = dict(
                os.environ,
                PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
                SANDBOX_ROOT=str(tmpdir),
                HOME=str(tmpdir),
                SNAPSHOT_RESUME="1",
                PREVIEW_ONLY="1",
                DEV_PREVIEW="1",
                DEV_PREVIEW_ONCE="1",
                BRANCH="feature-drift",
            )

            res = subprocess.run(
                ["bash", str(self.script_path), "--preview-only", "--snapshot-resume", "--branch", "feature-drift"],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(res.returncode, 0, f"Script failed with output:\n{res.stdout}\n{res.stderr}")
            self.assertIn("Dependency manifest drift detected", res.stdout)
            self.assertIn("MOCK_PNPM_INSTALL_CALLED install --prefer-offline", res.stdout)
            self.assertIn("Fast-path snapshot resumption successful", res.stdout)
            self.assertIn("MOCK_PNPM_DEV_STARTED", res.stdout)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_entrypoint_snapshot_resume_corrupt_repo_fallback(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            bin_dir, _ = self._create_mock_environment(tmpdir)
            repo_dir = tmpdir / "test-app"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "corrupted_file.txt").write_text("not a git repo")

            env = dict(
                os.environ,
                PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
                SANDBOX_ROOT=str(tmpdir),
                HOME=str(tmpdir),
                SNAPSHOT_RESUME="1",
                PREVIEW_ONLY="1",
                DEV_PREVIEW="1",
                DEV_PREVIEW_ONCE="1",
                BRANCH="main",
            )

            res = subprocess.run(
                ["bash", str(self.script_path), "--preview-only", "--snapshot-resume", "--branch", "main"],
                env=env,
                capture_output=True,
                text=True,
            )

            # Should log corrupt warning and fall back
            combined = res.stdout + res.stderr
            self.assertIn("not a valid git repository; falling back", combined)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
