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
        mock_sandbox.terminate = MagicMock()
        mock_sandbox.terminate.aio = AsyncMock(side_effect=lambda: stop_event.set())
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

        # Stop preview asynchronously
        stopped = asyncio.run(self.registry.stop_preview("test3"))
        self.assertTrue(stopped)
        mock_sandbox.terminate.aio.assert_awaited_once()
        self.assertEqual(p.status, "STOPPED")

    def test_preview_state_to_dict_includes_logs(self):
        from factory.ui.registry import PreviewState
        preview = PreviewState(repo="test3")
        preview.add_log("Starting preview server...\n")
        d = preview.to_dict()
        self.assertIn("logs", d)
        self.assertEqual(d["logs"], ["Starting preview server...\n"])
        self.assertEqual(d["log_count"], 1)

    def test_preview_stage_enum_and_state_to_dict(self):
        from factory.ui.registry import PreviewStage, PreviewState
        preview = PreviewState(repo="test3", stage=PreviewStage.INSTALLING_DEPS)
        d = preview.to_dict()
        self.assertIn("stage", d)
        self.assertEqual(d["stage"], "INSTALLING_DEPS")

    def test_preview_registry_append_log_detects_stage_transitions(self):
        import queue
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus
        preview = PreviewState(
            repo="test-stages",
            branch="main",
            status=PreviewStatus.PROVISIONING,
            stage=PreviewStage.PROVISIONING,
        )
        self.registry._previews["test-stages"] = preview
        q = self.registry.add_listener("test-stages")
        self.assertIsNotNone(q)

        # 1. Initially in PROVISIONING
        self.assertEqual(preview.stage, PreviewStage.PROVISIONING)

        # 2. Append dependency installation log
        self.registry.append_log("test-stages", "📦 Installing target repository dependencies (pnpm)...\n")
        self.assertEqual(preview.stage, PreviewStage.INSTALLING_DEPS)

        # 3. Append dev server start log
        self.registry.append_log("test-stages", "🌟 Launching Dev Preview Keep-Alive Daemon\n")
        self.assertEqual(preview.stage, PreviewStage.STARTING_DEV)

        # 4. Append Vite dev server ready log
        self.registry.append_log("test-stages", "  VITE v5.4.2  ready in 180 ms\n")
        self.assertEqual(preview.stage, PreviewStage.SERVING)
        self.assertEqual(preview.status, PreviewStatus.SERVING)

        # Verify broadcast events
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        stage_events = [e for e in events if e.get("event") == "stage"]
        stages = [e["stage"] for e in stage_events]
        self.assertIn("INSTALLING_DEPS", stages)
        self.assertIn("STARTING_DEV", stages)
        self.assertIn("SERVING", stages)

        status_events = [e for e in events if e.get("event") == "status"]
        statuses = [e["status"] for e in status_events]
        self.assertIn("SERVING", statuses)

    def test_preview_registry_append_log_detects_compilation_error(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus
        preview = PreviewState(
            repo="test-compile-err",
            branch="main",
            status=PreviewStatus.PROVISIONING,
            stage=PreviewStage.STARTING_DEV,
        )
        self.registry._previews["test-compile-err"] = preview
        q = self.registry.add_listener("test-compile-err")
        self.assertIsNotNone(q)

        err_line = "[vite:esbuild] SyntaxError: Unexpected token 'export' (12:4)\n"
        self.registry.append_log("test-compile-err", err_line)

        self.assertEqual(preview.status, PreviewStatus.FAILED)
        self.assertEqual(preview.error_message, err_line.strip())

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        status_events = [e for e in events if e.get("event") == "status"]
        self.assertTrue(len(status_events) > 0)
        self.assertEqual(status_events[0]["status"], "FAILED")
        self.assertEqual(status_events[0]["error"], err_line.strip())

    def test_preview_state_buffer_and_extract_lines(self):
        from factory.ui.registry import PreviewState
        preview = PreviewState(repo="test-buffering")

        lines1 = preview.buffer_and_extract_lines("hello ")
        self.assertEqual(lines1, [])

        lines2 = preview.buffer_and_extract_lines("world\nsecond line\nthird ")
        self.assertEqual(lines2, ["hello world\n", "second line\n"])

        lines3 = preview.buffer_and_extract_lines("line completed\n")
        self.assertEqual(lines3, ["third line completed\n"])

        # Flush incomplete trailing buffer
        preview.buffer_and_extract_lines("incomplete footer")
        lines_flushed = preview.buffer_and_extract_lines("", flush=True)
        self.assertEqual(lines_flushed, ["incomplete footer"])

    @patch("factory.ui.registry.create_preview_sandbox")
    def test_idle_preview_target_branch_persistence_and_launch(self, mock_create):
        from factory.ui.db import StudioDatabase
        from factory.ui.registry import PreviewRegistry, PreviewStatus
        db = StudioDatabase(":memory:")
        registry = PreviewRegistry(db=db)

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-idle-launch"
        mock_sandbox.stdout = iter([])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.return_value = 0
        mock_sandbox.returncode = 0
        mock_create.return_value = (mock_sandbox, "https://sb-idle-3000.modal.host")

        # 1. Update target branch when no preview exists yet (idle)
        registry.update_branch("test-idle-repo", "factory/my-preselected-branch")

        preview = registry.get_preview("test-idle-repo")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.branch, "factory/my-preselected-branch")
        self.assertEqual(preview.status, PreviewStatus.IDLE)

        # Verify DB persistence
        db_record = db.get_preview("test-idle-repo")
        self.assertIsNotNone(db_record)
        self.assertEqual(db_record["branch"], "factory/my-preselected-branch")

        # 2. Launch preview without specifying branch -> must launch on preselected branch
        launched = registry.launch_preview("test-idle-repo")
        self.assertEqual(launched.branch, "factory/my-preselected-branch")
        if getattr(launched, "_thread", None) is not None:
            launched._thread.join(timeout=2.0)

        mock_create.assert_called_once()
        spawn_cfg = mock_create.call_args[0][0]
        self.assertEqual(spawn_cfg.branch, "factory/my-preselected-branch")

    @patch("factory.ui.registry.create_preview_sandbox")
    def test_stopped_preview_target_branch_update_and_relaunch(self, mock_create):
        from factory.ui.db import StudioDatabase
        from factory.ui.registry import PreviewRegistry, PreviewState, PreviewStatus
        db = StudioDatabase(":memory:")
        registry = PreviewRegistry(db=db)

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-stopped-launch"
        mock_sandbox.stdout = iter([])
        mock_sandbox.stderr = iter([])
        mock_sandbox.wait.return_value = 0
        mock_sandbox.returncode = 0
        mock_create.return_value = (mock_sandbox, "https://sb-stopped-3000.modal.host")

        # 1. Start with a stopped preview on main
        stopped_preview = PreviewState(
            repo="stopped-repo",
            status=PreviewStatus.STOPPED,
            branch="main",
        )
        registry._previews["stopped-repo"] = stopped_preview
        registry._persist_preview(stopped_preview)

        # 2. Update target branch while stopped
        registry.update_branch("stopped-repo", "factory/feature-v2")
        self.assertEqual(stopped_preview.branch, "factory/feature-v2")

        # 3. Relaunch without branch argument -> must use updated branch
        relaunch = registry.launch_preview("stopped-repo")
        self.assertEqual(relaunch.branch, "factory/feature-v2")
        if getattr(relaunch, "_thread", None) is not None:
            relaunch._thread.join(timeout=2.0)

        mock_create.assert_called_once()
        spawn_cfg = mock_create.call_args[0][0]
        self.assertEqual(spawn_cfg.branch, "factory/feature-v2")

    def test_database_rehydration_preserves_idle_target_branch(self):
        from factory.ui.db import StudioDatabase
        from factory.ui.registry import PreviewRegistry, PreviewStatus
        db = StudioDatabase(":memory:")
        db.save_preview({
            "repo": "persisted-repo",
            "branch": "factory/persisted-feature",
            "status": "STOPPED",
            "stage": "IDLE",
            "preview_url": None,
        })

        new_registry = PreviewRegistry(db=db)
        new_registry.rehydrate()

        preview = new_registry.get_preview("persisted-repo")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.branch, "factory/persisted-feature")
        self.assertEqual(preview.status, PreviewStatus.STOPPED)

    def test_wait_for_serving_sync_returns_immediately_if_already_serving(self):
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus
        mock_sandbox = MagicMock()
        self.registry._previews["repo-serving"] = PreviewState(
            repo="repo-serving",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://repo-serving-3000.modal.host",
            sandbox=mock_sandbox,
        )
        sb, url = self.registry.wait_for_serving_sync("repo-serving", timeout=1.0)
        self.assertEqual(sb, mock_sandbox)
        self.assertEqual(url, "https://repo-serving-3000.modal.host")

    def test_wait_for_serving_sync_breaks_on_failed_status(self):
        from factory.ui.registry import PreviewState, PreviewStatus
        self.registry._previews["repo-failed"] = PreviewState(
            repo="repo-failed",
            status=PreviewStatus.FAILED,
            error_message="Vite build failed",
        )
        sb, url = self.registry.wait_for_serving_sync("repo-failed", timeout=1.0, poll_interval=0.01)
        self.assertIsNone(sb)
        self.assertIsNone(url)
