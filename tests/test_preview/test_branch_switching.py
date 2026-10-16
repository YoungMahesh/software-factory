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


class TestInContainerBranchSwitching(unittest.TestCase):
    def setUp(self):
        from factory.ui.registry import PreviewRegistry
        self.registry = PreviewRegistry()

    def test_switch_preview_branch_success_in_place(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-active-preview"
        mock_process = MagicMock()
        mock_process.stdout = iter(["Switched to branch 'factory/user-auth'\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-app",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            sandbox=mock_sandbox,
            preview_url="https://preview.modal.host",
        )
        self.registry._previews["test-app"] = preview
        q = self.registry.add_listener("test-app")
        self.assertIsNotNone(q)

        updated = self.registry.switch_preview_branch("test-app", "factory/user-auth")

        self.assertEqual(updated.branch, "factory/user-auth")
        self.assertEqual(updated.status, PreviewStatus.SERVING)

        # Verify sandbox.exec call
        mock_sandbox.exec.assert_called_once()
        exec_args, _ = mock_sandbox.exec.call_args
        self.assertEqual(exec_args[0], "bash")
        self.assertEqual(exec_args[1], "-c")
        exec_cmd = exec_args[2]

        # Verify workspace directory
        self.assertIn("/root/test-app", exec_cmd)
        # Verify clean working tree reset before checkout
        self.assertIn("git reset --hard && git clean -fd", exec_cmd)
        # Verify checkout and pull of target branch
        self.assertIn("git checkout factory/user-auth && git pull origin factory/user-auth", exec_cmd)

        # Verify SSE events broadcasted
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        branch_events = [e for e in events if e.get("event") == "branch"]
        self.assertEqual(len(branch_events), 1)
        self.assertEqual(branch_events[0]["branch"], "factory/user-auth")
        self.assertEqual(branch_events[0]["repo"], "test-app")

        refresh_events = [e for e in events if e.get("event") == "preview_refresh"]
        self.assertEqual(len(refresh_events), 1)
        self.assertEqual(refresh_events[0]["repo"], "test-app")

        # Verify logs were appended
        self.assertTrue(any("Switched to branch" in log for log in updated.logs))

    def test_switch_preview_branch_diff_triggers_pnpm_install(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-diff-preview"
        mock_process = MagicMock()
        mock_process.stdout = iter([
            "Switched to branch 'factory/new-deps'\n",
            "📦 Dependency changes detected in package.json/pnpm-lock.yaml. Running pnpm install --prefer-offline...\n",
            "Packages: +12\n",
            "Progress: resolved 150, reused 150, downloaded 0, added 12\n",
        ])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-deps-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            sandbox=mock_sandbox,
            preview_url="https://preview.modal.host",
        )
        self.registry._previews["test-deps-repo"] = preview

        updated = self.registry.switch_preview_branch("test-deps-repo", "factory/new-deps")

        self.assertEqual(updated.branch, "factory/new-deps")

        # Verify command asserts package.json / pnpm-lock.yaml diff and pnpm install --prefer-offline
        _, kwargs_or_args = mock_sandbox.exec.call_args
        exec_args = mock_sandbox.exec.call_args[0]
        exec_cmd = exec_args[2]
        self.assertIn("package.json pnpm-lock.yaml", exec_cmd)
        self.assertIn("pnpm install --prefer-offline", exec_cmd)

        # Verify stdout lines were captured in logs
        self.assertTrue(any("Dependency changes detected" in l for l in updated.logs))
        self.assertTrue(any("Packages: +12" in l for l in updated.logs))

    def test_switch_preview_branch_failure_retains_container_and_branch(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-fail-preview"
        mock_sandbox.terminate = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter(["git checkout factory/broken-branch\n"])
        mock_process.stderr = iter(["fatal: Remote branch factory/broken-branch not found in upstream origin\n"])
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-fail-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            sandbox=mock_sandbox,
            preview_url="https://preview.modal.host",
        )
        self.registry._previews["test-fail-repo"] = preview

        with self.assertRaises(RuntimeError) as ctx:
            self.registry.switch_preview_branch("test-fail-repo", "factory/broken-branch")

        self.assertIn("failed (exit code 1)", str(ctx.exception))
        self.assertIn("Remote branch factory/broken-branch not found", str(ctx.exception))

        # Invariant checks:
        # 1. Container status remains SERVING (not STOPPED or FAILED)
        self.assertEqual(preview.status, PreviewStatus.SERVING)
        # 2. Container sandbox was NOT terminated
        mock_sandbox.terminate.assert_not_called()
        # 3. Branch remains on original branch 'main'
        self.assertEqual(preview.branch, "main")
        # 4. Error output appended to preview logs
        self.assertTrue(any("fatal: Remote branch" in l or "failed" in l for l in preview.logs))

    def test_switch_preview_branch_pnpm_install_failure_preserves_container_and_branch(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-pnpm-fail"
        mock_sandbox.terminate = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter([
            "Switched to branch 'factory/broken-deps'\n",
            "📦 Dependency changes detected in package.json/pnpm-lock.yaml. Running pnpm install --prefer-offline...\n",
        ])
        mock_process.stderr = iter([
            "ERR_PNPM_PEER_DEP_ISSUES: Unmet peer dependencies\n",
            "⚠️ Rolling back container working tree to previous branch state...\n",
        ])
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-pnpm-fail-repo",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            branch="main",
            sandbox=mock_sandbox,
            preview_url="https://preview.modal.host",
        )
        self.registry._previews["test-pnpm-fail-repo"] = preview

        with self.assertRaises(RuntimeError) as ctx:
            self.registry.switch_preview_branch("test-pnpm-fail-repo", "factory/broken-deps")

        self.assertIn("failed (exit code 1)", str(ctx.exception))
        self.assertIn("ERR_PNPM_PEER_DEP_ISSUES", str(ctx.exception))

        # Invariant checks:
        self.assertEqual(preview.status, PreviewStatus.SERVING)
        mock_sandbox.terminate.assert_not_called()
        self.assertEqual(preview.branch, "main")
        self.assertTrue(any("ERR_PNPM_PEER_DEP_ISSUES" in l for l in preview.logs))
