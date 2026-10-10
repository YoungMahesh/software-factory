"""Unit tests for Dedicated Preview Sandbox spawner and in-memory registry."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from factory.spawner import (
    FACTORY_CPU,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    PreviewSpawnConfig,
    create_preview_sandbox,
)


class TestPreviewSpawner(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    @patch("modal.App.lookup")
    @patch("modal.Sandbox.create")
    def test_create_preview_sandbox_configuration(self, mock_sandbox_create, mock_app_lookup):
        mock_app = MagicMock()
        mock_app_lookup.return_value = mock_app

        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://preview-sandbox-3000.modal.host"
        mock_sandbox = MagicMock()
        mock_sandbox.tunnels.return_value = {3000: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        config = PreviewSpawnConfig(
            repo="test3",
            branch="factory/preview-feature",
            testing=True,
            repo_root=self.repo_root,
        )

        sandbox, preview_url = create_preview_sandbox(config)

        self.assertEqual(sandbox, mock_sandbox)
        self.assertEqual(preview_url, "https://preview-sandbox-3000.modal.host")

        # Verify Sandbox.create call
        mock_sandbox_create.assert_called_once()
        args, kwargs = mock_sandbox_create.call_args

        # Arguments: entrypoint runs with --preview-only
        self.assertEqual(args[0], "bash")
        self.assertEqual(args[1], "/root/factory_entrypoint.sh")
        self.assertIn("--preview-only", args)
        self.assertIn("--branch", args)
        self.assertIn("factory/preview-feature", args)
        # Must not invoke agent pipeline
        self.assertNotIn("--model", args)

        # Keyword arguments: encrypted_ports=[3000], idle_timeout=1800, ENABLE_CLOUDFLARE=0
        self.assertEqual(kwargs["encrypted_ports"], [3000])
        self.assertEqual(kwargs["idle_timeout"], 1800)
        self.assertEqual(kwargs["timeout"], FACTORY_TIMEOUT_SECS)
        self.assertEqual(kwargs["memory"], FACTORY_STANDARD_MEMORY)
        self.assertEqual(kwargs["cpu"], FACTORY_CPU)

        env = kwargs["env"]
        self.assertEqual(env["ENABLE_CLOUDFLARE"], "0")
        self.assertEqual(env["DEV_PREVIEW"], "1")
        self.assertEqual(env["PORT"], "3000")
        self.assertEqual(env["BRANCH"], "factory/preview-feature")


class TestBranchResolution(unittest.TestCase):
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_milestone(self, mock_milestones):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = [{"slug": "user-auth", "state": "open"}]
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "factory/user-auth")

    @patch("factory.ui.registry.fetch_repo_scratch_metadata")
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_scratch(self, mock_milestones, mock_scratch):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = []
        mock_scratch.return_value = {"features": [{"slug": "dashboard"}]}
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "factory/dashboard")

    @patch("factory.ui.registry.fetch_repo_scratch_metadata")
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_fallback(self, mock_milestones, mock_scratch):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = []
        mock_scratch.return_value = {"features": []}
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "main")


class TestPreviewRegistry(unittest.TestCase):
    def setUp(self):
        from factory.ui.registry import PreviewRegistry
        self.registry = PreviewRegistry()

    def test_get_preview_nonexistent(self):
        self.assertIsNone(self.registry.get_preview("unknown-repo"))

    @patch("factory.ui.registry.create_preview_sandbox")
    def test_launch_and_stop_preview_lifecycle(self, mock_create):
        import threading
        import time

        stop_event = threading.Event()
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-12345"
        mock_sandbox.stdout = iter(["Ready in 250ms\n"])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.side_effect = lambda **kwargs: stop_event.wait(timeout=2.0)
        mock_sandbox.terminate.side_effect = lambda: stop_event.set()
        mock_sandbox.returncode = 0
        mock_create.return_value = (mock_sandbox, "https://sb-12345-3000.modal.host")

        preview = self.registry.launch_preview("test3", branch="factory/feature-1")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.repo, "test3")
        self.assertEqual(preview.branch, "factory/feature-1")

        # Wait for worker thread to reach SERVING state
        for _ in range(20):
            p = self.registry.get_preview("test3")
            if p and p.status == "SERVING":
                break
            time.sleep(0.05)

        p = self.registry.get_preview("test3")
        self.assertIsNotNone(p)
        self.assertEqual(p.status, "SERVING")
        self.assertEqual(p.preview_url, "https://sb-12345-3000.modal.host")
        self.assertEqual(p.sandbox_id, "sb-12345")

        # Stop preview
        stopped = self.registry.stop_preview("test3")
        self.assertTrue(stopped)
        mock_sandbox.terminate.assert_called_once()
        self.assertEqual(p.status, "STOPPED")
