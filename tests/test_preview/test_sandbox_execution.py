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


class TestInSandboxRegistryExecution(unittest.TestCase):
    def setUp(self):
        from factory.ui.registry import JobRegistry, PreviewRegistry
        self.preview_reg = PreviewRegistry()
        self.job_reg = JobRegistry(preview_registry=self.preview_reg)

    def test_job_registry_delegates_to_active_preview_sandbox(self):
        import time
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter([
            "__SF_EVENT__:{\"type\":\"stage\",\"stage\":\"PLANNER\"}\n",
            "Planning implementation for ticket 42...\n",
            "__SF_EVENT__:{\"type\":\"stage\",\"stage\":\"COMPLETED\"}\n",
        ])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test3",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            preview_url="https://test3-3000.modal.host",
            sandbox=mock_sandbox,
            sandbox_id="sb-test3",
        )
        self.preview_reg._previews["test3"] = preview
        preview_listener = self.preview_reg.add_listener("test3")

        job = self.job_reg.create_job(
            repo="test3",
            feature="feature-unified",
            issue="42",
            model="deepseek-v4.1-flash",
        )
        job_listener = self.job_reg.add_listener(job.id)

        self.job_reg.start_job(job.id)

        # Wait for job worker to finish
        for _ in range(50):
            time.sleep(0.05)
            j = self.job_reg.get_job(job.id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break

        j = self.job_reg.get_job(job.id)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "SUCCESS")
        self.assertEqual(j.stage, "COMPLETED")
        self.assertTrue(j.is_in_sandbox_exec)
        self.assertEqual(j.preview_url, "https://test3-3000.modal.host")

        # Must invoke sandbox.exec
        mock_sandbox.exec.assert_called_once()
        exec_args, exec_kwargs = mock_sandbox.exec.call_args
        self.assertEqual(exec_args[0], "bash")
        self.assertEqual(exec_args[1], "-c")
        exec_cmd = exec_args[2]

        # Verify command sources /root/.factory.env and runs pipeline
        self.assertIn("source /root/.factory.env", exec_cmd)
        self.assertIn("/root/factory/pipeline.ts", exec_cmd)
        self.assertIn("--workspace /root/test3", exec_cmd)
        self.assertIn("--feature feature-unified", exec_cmd)
        self.assertIn("--issue 42", exec_cmd)
        self.assertIn("--studio", exec_cmd)
        self.assertIn("STUDIO_MODE=1", exec_cmd)

        # Verify preview branch was updated in-place without restart
        self.assertEqual(preview.branch, "factory/feature-unified")

        # Collect job events
        job_events = []
        while not job_listener.empty():
            job_events.append(job_listener.get_nowait())

        # Verify logs were streamed
        log_events = [e for e in job_events if e.get("event") == "log"]
        self.assertTrue(any("Planning implementation" in e.get("data", "") for e in log_events))

        # Verify preview_refresh event was broadcast
        refresh_events = [e for e in job_events if e.get("event") == "preview_refresh"]
        self.assertEqual(len(refresh_events), 1)
        self.assertEqual(refresh_events[0]["repo"], "test3")

        # Verify preview listener also received preview_refresh
        preview_events = []
        while not preview_listener.empty():
            preview_events.append(preview_listener.get_nowait())
        preview_refresh = [e for e in preview_events if e.get("event") == "preview_refresh"]
        self.assertEqual(len(preview_refresh), 1)

    def test_job_registry_auto_provisions_unified_sandbox_when_no_active_studio_sandbox(self):
        import time
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter(["Step 1 complete\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        def fake_launch(repo, branch=None):
            preview = PreviewState(
                repo=repo,
                branch=branch or "main",
                status=PreviewStatus.SERVING,
                stage=PreviewStage.SERVING,
                sandbox=mock_sandbox,
                preview_url="https://auto-prov-3000.modal.host",
            )
            self.preview_reg._previews[repo] = preview
            return preview

        self.preview_reg.launch_preview = MagicMock(side_effect=fake_launch)

        job = self.job_reg.create_job(
            repo="no-active-repo",
            feature="feature-standalone",
        )
        self.job_reg.start_job(job.id)

        for _ in range(50):
            time.sleep(0.05)
            j = self.job_reg.get_job(job.id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break

        j = self.job_reg.get_job(job.id)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "SUCCESS")
        self.assertTrue(j.is_in_sandbox_exec)
        self.preview_reg.launch_preview.assert_called_once_with("no-active-repo", branch="factory/feature-standalone")
        mock_sandbox.exec.assert_called_once()

    def test_job_registry_waits_for_serving_when_preview_is_provisioning(self):
        import time
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter(["Step 1 complete\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-prov",
            status=PreviewStatus.PROVISIONING,
            stage=PreviewStage.PROVISIONING,
            sandbox=None,
        )
        self.preview_reg._previews["test-prov"] = preview

        def fake_wait(repo, timeout=60.0, poll_interval=0.05):
            preview.status = PreviewStatus.SERVING
            preview.stage = PreviewStage.SERVING
            preview.sandbox = mock_sandbox
            preview.preview_url = "https://test-prov-3000.modal.host"
            return mock_sandbox, preview.preview_url

        self.preview_reg.wait_for_serving_sync = MagicMock(side_effect=fake_wait)

        job = self.job_reg.create_job(
            repo="test-prov",
            feature="feat-prov",
        )
        self.job_reg.start_job(job.id)

        for _ in range(50):
            time.sleep(0.05)
            j = self.job_reg.get_job(job.id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break

        j = self.job_reg.get_job(job.id)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "SUCCESS")
        self.assertTrue(j.is_in_sandbox_exec)
        mock_sandbox.exec.assert_called_once()

    def test_job_registry_fails_when_sandbox_fails_to_serve(self):
        import time
        from factory.ui.registry import PreviewState, PreviewStatus

        def fake_launch(repo, branch=None):
            preview = PreviewState(
                repo=repo,
                branch=branch or "main",
                status=PreviewStatus.FAILED,
                error_message="Vite compilation error",
            )
            self.preview_reg._previews[repo] = preview
            return preview

        self.preview_reg.launch_preview = MagicMock(side_effect=fake_launch)

        job = self.job_reg.create_job(
            repo="fail-prov-repo",
            feature="feat-fail",
        )
        self.job_reg.start_job(job.id)

        for _ in range(50):
            time.sleep(0.05)
            j = self.job_reg.get_job(job.id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break

        j = self.job_reg.get_job(job.id)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "FAILED")
        self.assertIn("Unified Studio Sandbox failed to reach serving status", j.error_message)

    def test_in_sandbox_execution_failure_emits_no_refresh(self):
        import time
        from factory.ui.registry import PreviewStage, PreviewState, PreviewStatus

        mock_sandbox = MagicMock()
        mock_process = MagicMock()
        mock_process.stdout = iter(["Error in pipeline\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 1
        mock_process.returncode = 1
        mock_sandbox.exec.return_value = mock_process

        preview = PreviewState(
            repo="test-fail",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            sandbox=mock_sandbox,
        )
        self.preview_reg._previews["test-fail"] = preview

        job = self.job_reg.create_job(
            repo="test-fail",
            feature="feat-fail",
        )
        job_listener = self.job_reg.add_listener(job.id)

        self.job_reg.start_job(job.id)

        for _ in range(50):
            time.sleep(0.05)
            j = self.job_reg.get_job(job.id)
            if j and j.status in ("SUCCESS", "FAILED"):
                break

        j = self.job_reg.get_job(job.id)
        self.assertEqual(j.status, "FAILED")
        self.assertTrue(j.is_in_sandbox_exec)

        job_events = []
        while not job_listener.empty():
            job_events.append(job_listener.get_nowait())
        refresh_events = [e for e in job_events if e.get("event") == "preview_refresh"]
        self.assertEqual(len(refresh_events), 0)
