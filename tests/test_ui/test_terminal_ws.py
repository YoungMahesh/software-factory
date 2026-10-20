"""Subsystem tests for In-Sandbox Interactive Terminal WebSocket endpoint."""

import asyncio
import queue
import threading
import time
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.registry import PreviewRegistry, PreviewState, PreviewStatus


class MockStdin:
    def __init__(self):
        self.written = []
        self.eof_written = False
        self.drain_count = 0

    def write(self, data):
        self.written.append(data)

    def drain(self):
        self.drain_count += 1

    def flush(self):
        pass

    def write_eof(self):
        self.eof_written = True


class MockStreamReader:
    """Simulates an iterable StreamReader from Modal ContainerProcess."""
    def __init__(self, initial_chunks=None):
        self._queue = queue.Queue()
        if initial_chunks:
            for c in initial_chunks:
                self._queue.put(c)
        self._closed = False

    def push(self, chunk):
        self._queue.put(chunk)

    def close(self):
        self._closed = True
        self._queue.put(None)

    def __iter__(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            yield item


class MockProcess:
    def __init__(self, initial_stdout=None):
        self.stdin = MockStdin()
        self.stdout = MockStreamReader(initial_stdout or [])
        self.terminated = False
        self.terminate_called_count = 0

    def terminate(self):
        self.terminated = True
        self.terminate_called_count += 1
        self.stdout.close()

    def wait(self):
        return 0


class MockModalContainerProcess:
    """Accurately mimics Modal SDK 1.6.2 ContainerProcess without synthetic terminate() method."""
    def __init__(self, initial_stdout=None):
        self.stdin = MockStdin()
        self.stdout = MockStreamReader(initial_stdout or [])

    def wait(self):
        return 0


class TestTerminalWebSocket(unittest.TestCase):
    def setUp(self):
        self.preview_reg = PreviewRegistry()
        self.app = create_app(preview_reg=self.preview_reg)
        self.client = TestClient(self.app)

    def test_terminal_ws_when_sandbox_not_running(self):
        """When container is not running, sends informative warning and closes."""
        with self.client.websocket_connect("/api/repos/repo-without-sandbox/terminal/ws") as ws:
            msg = ws.receive_text()
            self.assertIn("Sandbox container is not running", msg)
            self.assertIn("repo-without-sandbox", msg)

    def test_terminal_ws_bidirectional_and_exec_args(self):
        """Connects over WS, launches bash --login in /root/{repo} with pty=True, relays I/O."""
        mock_sandbox = MagicMock()
        mock_proc = MockProcess(["root@sandbox:/root/my-app# "])
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="my-app",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["my-app"] = preview

        with self.client.websocket_connect("/api/repos/software-factory-09-test/my-app/terminal/ws") as ws:
            # Verify initial prompt from stdout
            prompt = ws.receive_text()
            self.assertIn("root@sandbox:/root/my-app#", prompt)

            # Send keystrokes
            ws.send_text("ls -la\r")
            time.sleep(0.05)

            # Verify stdin was written to
            self.assertIn("ls -la\r", mock_proc.stdin.written)

            # Push more output from container
            mock_proc.stdout.push("file1.txt\r\nfile2.txt\r\nroot@sandbox:/root/my-app# ")
            output = ws.receive_text()
            self.assertIn("file1.txt", output)

        # After exiting context (disconnecting WS), process must be terminated immediately
        self.assertTrue(mock_proc.terminated)
        self.assertEqual(mock_proc.terminate_called_count, 1)

        # Verify modal sandbox.exec was called with expected arguments
        mock_sandbox.exec.assert_called_once_with(
            "bash",
            "--login",
            workdir="/root/my-app",
            pty=True,
        )

    def test_terminal_ws_disconnect_terminates_process(self):
        """Disconnecting the WebSocket immediately terminates the backend container process."""
        mock_sandbox = MagicMock()
        mock_proc = MockProcess(["connected\r\n"])
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test-project",
            branch="feature",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test-project"] = preview

        with self.client.websocket_connect("/api/repos/test-project/terminal/ws") as ws:
            msg = ws.receive_text()
            self.assertEqual(msg, "connected\r\n")
            self.assertFalse(mock_proc.terminated)

        # Disconnected
        self.assertTrue(mock_proc.terminated)

    def test_terminal_ws_exec_failure_returns_error(self):
        """When sandbox.exec raises an exception, sends error and closes."""
        mock_sandbox = MagicMock()
        mock_sandbox.exec.side_effect = RuntimeError("Container cgroup failure")

        preview = PreviewState(
            repo="failing-repo",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["failing-repo"] = preview

        with self.client.websocket_connect("/api/repos/failing-repo/terminal/ws") as ws:
            msg = ws.receive_text()
            self.assertIn("Failed to launch interactive shell", msg)
            self.assertIn("Container cgroup failure", msg)

    def test_terminal_ws_ignores_resize_json_frames(self):
        """Resize events sent as JSON are ignored and not written to bash stdin."""
        mock_sandbox = MagicMock()
        mock_proc = MockProcess(["prompt$ "])
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="resize-repo",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["resize-repo"] = preview

        with self.client.websocket_connect("/api/repos/resize-repo/terminal/ws") as ws:
            _ = ws.receive_text()
            # Send resize JSON
            ws.send_text('{"type":"resize","cols":120,"rows":40}')
            time.sleep(0.05)
            # Verify resize json was NOT written to stdin
            self.assertEqual(len(mock_proc.stdin.written), 0)

            # Normal keystroke is written
            ws.send_text("date\r")
            time.sleep(0.05)
            self.assertEqual(mock_proc.stdin.written, ["date\r"])

    def test_terminal_ws_modal_container_process_disconnect_flushes_eof_and_exit(self):
        """Accurately tests against Modal's actual ContainerProcess (no terminate method)."""
        mock_sandbox = MagicMock()
        mock_proc = MockModalContainerProcess(["bash-5.1$ "])
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="modal-repo",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["modal-repo"] = preview

        with self.client.websocket_connect("/api/repos/modal-repo/terminal/ws") as ws:
            _ = ws.receive_text()

        # Disconnected: verify exit was written, write_eof was called, and drain flushed it
        self.assertTrue(mock_proc.stdin.eof_written)
        self.assertGreaterEqual(mock_proc.stdin.drain_count, 1)
        self.assertIn("\x03exit\r\n", mock_proc.stdin.written)
