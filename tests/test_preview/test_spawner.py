"""Subsystem tests for Dedicated Preview Sandbox spawner and in-memory registry."""

import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.spawner import (
    FACTORY_CPU,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    PreviewSpawnConfig,
    create_preview_sandbox,
)


class TestPreviewSpawner(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

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
        self.assertEqual(env["__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS"], ".modal.host,3000.mahesh0.dev")


class TestBranchResolution(unittest.TestCase):
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_milestone(self, mock_milestones):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = [{"slug": "user-auth", "state": "open"}]
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "factory/user-auth")

    @patch("factory.ui.registry.fetch_repo_issues")
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_issue(self, mock_milestones, mock_issues):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = []
        mock_issues.return_value = [{"number": 42, "title": "Fix navbar", "state": "open"}]
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "factory/issue-42")

    @patch("factory.ui.registry.fetch_repo_issues")
    @patch("factory.ui.registry.fetch_repo_milestones")
    def test_resolve_active_preview_branch_fallback_to_main_without_scratch(self, mock_milestones, mock_issues):
        from factory.ui.registry import resolve_active_preview_branch
        mock_milestones.return_value = []
        mock_issues.return_value = []
        branch = resolve_active_preview_branch("test3")
        self.assertEqual(branch, "main")
        mock_milestones.assert_called_once_with(repo_name="test3", state="open")
        mock_issues.assert_called_once_with(repo_name="test3", state="open")
        # Ensure registry does not export fetch_repo_scratch_metadata or create_factory_sandbox
        import factory.ui.registry as reg
        self.assertFalse(hasattr(reg, "fetch_repo_scratch_metadata"))
        self.assertFalse(hasattr(reg, "create_factory_sandbox"))
