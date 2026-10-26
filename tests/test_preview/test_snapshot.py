"""Subsystem tests for automatic filesystem snapshot capture on serving state."""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from factory.ui.db import StudioDatabase
from factory.ui.registry import (
    PreviewRegistry,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)
from factory.ui.registry._snapshot import (
    DEFAULT_SNAPSHOT_TTL_SECONDS,
    capture_snapshot_for_preview,
    is_snapshot_needed,
    query_container_commit_sha,
    trigger_background_snapshot,
)


class TestSnapshotCapture(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def _create_mock_sandbox(self, commit_sha="1111222233334444555566667777888899990000"):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-test-serving-1"

        mock_git_proc = MagicMock()
        mock_git_proc.stdout = iter([f"{commit_sha}\n".encode("utf-8")])
        mock_git_proc.wait.return_value = 0
        mock_git_proc.returncode = 0

        mock_sync_proc = MagicMock()
        mock_sync_proc.wait.return_value = 0
        mock_sync_proc.returncode = 0

        def mock_exec(*args, **kwargs):
            if args and "git" in str(args):
                return mock_git_proc
            if args and "sync" in str(args):
                return mock_sync_proc
            m = MagicMock()
            m.wait.return_value = 0
            m.returncode = 0
            return m

        mock_sandbox.exec.side_effect = mock_exec

        mock_image = MagicMock()
        mock_image.object_id = "im-snap-test-456"
        mock_sandbox.snapshot_filesystem.return_value = mock_image
        return mock_sandbox, mock_sync_proc, mock_image

    def test_query_container_commit_sha(self):
        commit_sha = "abcdef0123456789abcdef0123456789abcdef01"
        mock_sandbox, _, _ = self._create_mock_sandbox(commit_sha=commit_sha)

        resolved_sha = query_container_commit_sha(mock_sandbox, "my-repo")
        self.assertEqual(resolved_sha, commit_sha)

    def test_query_container_commit_sha_handles_failure(self):
        mock_sandbox = MagicMock()
        mock_sandbox.exec.side_effect = RuntimeError("Sandbox connection dropped")
        self.assertIsNone(query_container_commit_sha(mock_sandbox, "my-repo"))

    def test_is_snapshot_needed(self):
        commit_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        commit_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

        # No snapshot in DB
        self.assertTrue(is_snapshot_needed(self.db, "repo-1", commit_a))

        # Save snapshot for commit_a
        self.db.save_snapshot_metadata("repo-1", "im-1", commit_a)

        # Same commit -> no snapshot needed
        self.assertFalse(is_snapshot_needed(self.db, "repo-1", commit_a))

        # Different commit -> snapshot needed
        self.assertTrue(is_snapshot_needed(self.db, "repo-1", commit_b))

    def test_capture_snapshot_executes_sync_and_snapshot_filesystem(self):
        commit_sha = "1111222233334444555566667777888899990000"
        mock_sandbox, mock_sync_proc, mock_image = self._create_mock_sandbox(commit_sha=commit_sha)

        preview = PreviewState(
            repo="test-app",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            sandbox=mock_sandbox,
        )

        image_id = capture_snapshot_for_preview(preview, db=self.db)
        self.assertEqual(image_id, "im-snap-test-456")

        # Assert sync was invoked and waited
        mock_sandbox.exec.assert_any_call("sync")
        mock_sync_proc.wait.assert_called_once()

        # Assert snapshot_filesystem called with 30-day retention
        mock_sandbox.snapshot_filesystem.assert_called_once_with(ttl=DEFAULT_SNAPSHOT_TTL_SECONDS)
        self.assertEqual(DEFAULT_SNAPSHOT_TTL_SECONDS, 30 * 86400)

        # Assert active container NOT terminated
        mock_sandbox.terminate.assert_not_called()

        # Assert preview state updated
        self.assertEqual(preview.snapshot_image_id, "im-snap-test-456")
        self.assertEqual(preview.snapshot_commit_sha, commit_sha)
        self.assertIsNotNone(preview.snapshot_captured_at)

        # Assert persisted to DB
        meta = self.db.get_snapshot_metadata("test-app")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["snapshot_image_id"], "im-snap-test-456")
        self.assertEqual(meta["snapshot_commit_sha"], commit_sha)

    def test_capture_snapshot_skips_when_already_up_to_date(self):
        commit_sha = "2222333344445555666677778888999900001111"
        self.db.save_snapshot_metadata("test-app-warm", "im-existing-789", commit_sha)

        mock_sandbox, _, _ = self._create_mock_sandbox(commit_sha=commit_sha)
        preview = PreviewState(
            repo="test-app-warm",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            sandbox=mock_sandbox,
        )

        image_id = capture_snapshot_for_preview(preview, db=self.db)
        self.assertIsNone(image_id)
        mock_sandbox.snapshot_filesystem.assert_not_called()

    def test_capture_snapshot_errors_do_not_crash_preview(self):
        mock_sandbox, _, _ = self._create_mock_sandbox()
        mock_sandbox.snapshot_filesystem.side_effect = RuntimeError("Modal rate limit or storage error")

        preview = PreviewState(
            repo="test-app-fail",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            sandbox=mock_sandbox,
        )

        image_id = capture_snapshot_for_preview(preview, db=self.db)
        self.assertIsNone(image_id)

        # Active preview remains SERVING and running
        self.assertEqual(preview.status, PreviewStatus.SERVING)
        mock_sandbox.terminate.assert_not_called()

    def test_stage_transition_to_serving_triggers_snapshot(self):
        commit_sha = "3333444455556666777788889999000011112222"
        mock_sandbox, _, _ = self._create_mock_sandbox(commit_sha=commit_sha)

        registry = PreviewRegistry(db=self.db)
        preview = PreviewState(
            repo="test-auto-snap",
            status=PreviewStatus.PROVISIONING,
            stage=PreviewStage.STARTING_DEV,
            sandbox=mock_sandbox,
        )
        registry._previews["test-auto-snap"] = preview

        # Simulate Vite ready log line triggering stage transition to SERVING
        registry.append_log("test-auto-snap", "  VITE v5.4.2  ready in 200 ms\n")

        self.assertEqual(preview.stage, PreviewStage.SERVING)
        self.assertEqual(preview.status, PreviewStatus.SERVING)

        # Background snapshot thread was dispatched
        self.assertIsNotNone(preview._snapshot_thread)
        preview._snapshot_thread.join(timeout=3.0)

        # Verified snapshot was captured and stored
        self.assertEqual(preview.snapshot_image_id, "im-snap-test-456")
        meta = self.db.get_snapshot_metadata("test-auto-snap")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["snapshot_image_id"], "im-snap-test-456")
        self.assertEqual(meta["snapshot_commit_sha"], commit_sha)

    def test_configurable_snapshot_ttl(self):
        commit_sha = "4444555566667777888899990000111122223333"
        mock_sandbox, _, _ = self._create_mock_sandbox(commit_sha=commit_sha)
        preview = PreviewState(
            repo="test-ttl-snap",
            status=PreviewStatus.SERVING,
            stage=PreviewStage.SERVING,
            sandbox=mock_sandbox,
        )

        # 1. Configurable via FACTORY_SNAPSHOT_TTL_DAYS
        with patch.dict("os.environ", {"FACTORY_SNAPSHOT_TTL_DAYS": "7"}):
            capture_snapshot_for_preview(preview, db=self.db)
            mock_sandbox.snapshot_filesystem.assert_called_with(ttl=7 * 86400)

        # 2. Configurable via FACTORY_SNAPSHOT_TTL_SECONDS
        mock_sandbox.reset_mock()
        with patch.dict("os.environ", {"FACTORY_SNAPSHOT_TTL_SECONDS": "3600"}):
            preview.snapshot_commit_sha = None
            mock_sandbox.snapshot_filesystem.return_value = MagicMock(object_id="im-ttl-2")
            capture_snapshot_for_preview(preview, db=None)
            mock_sandbox.snapshot_filesystem.assert_called_with(ttl=3600)
