"""Unit tests for the deep SandboxLauncher module and RunningSandbox domain model."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sandbox.core import LaunchRequest, LaunchResponse
from sandbox.launcher import RunningSandbox, SandboxLauncher, launch_sandbox


class TestRunningSandbox(unittest.TestCase):
    def setUp(self):
        self.mock_sandbox = MagicMock()
        self.mock_sandbox.object_id = "sb-12345678"
        self.mock_sandbox.poll.return_value = None
        self.response = LaunchResponse(
            sandbox_id="sb-12345678",
            app_name="test-app",
            sandbox_name="test-app-abcdef",
            ssh_info=("ssh.host", 2222),
            ssh_command="ssh -p 2222 root@ssh.host",
            opencode_url="https://opencode.modal.run",
            metro_url="https://metro.modal.run",
            t3_url="https://t3.modal.run",
            t3_pair_url="https://t3.modal.run/pair#abc",
        )
        self.running = RunningSandbox(sandbox=self.mock_sandbox, response=self.response)

    def test_properties(self):
        self.assertEqual(self.running.sandbox_id, "sb-12345678")
        self.assertEqual(self.running.app_name, "test-app")
        self.assertEqual(self.running.sandbox_name, "test-app-abcdef")
        self.assertEqual(self.running.ssh_info, ("ssh.host", 2222))
        self.assertEqual(self.running.ssh_command, "ssh -p 2222 root@ssh.host")
        self.assertEqual(self.running.opencode_url, "https://opencode.modal.run")
        self.assertEqual(self.running.metro_url, "https://metro.modal.run")
        self.assertEqual(self.running.t3_url, "https://t3.modal.run")
        self.assertEqual(self.running.t3_pair_url, "https://t3.modal.run/pair#abc")

    def test_to_response(self):
        resp = self.running.to_response()
        self.assertIs(resp, self.response)

    def test_unpacking_compatibility(self):
        sb, resp = self.running
        self.assertIs(sb, self.mock_sandbox)
        self.assertIs(resp, self.response)

    def test_delegated_methods(self):
        self.assertIsNone(self.running.poll())
        self.mock_sandbox.poll.assert_called_once()

        self.running.terminate()
        self.mock_sandbox.terminate.assert_called_once()

        self.mock_sandbox.exec.return_value = "exec_result"
        res = self.running.exec("ls", "-la")
        self.assertEqual(res, "exec_result")
        self.mock_sandbox.exec.assert_called_once_with("ls", "-la")

        self.mock_sandbox.tunnels.return_value = {22: MagicMock()}
        tunnels = self.running.tunnels()
        self.assertIn(22, tunnels)


class TestSandboxLauncher(unittest.TestCase):
    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_dependency_injection(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-launcher-1"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {22: MagicMock(tcp_socket=("10.0.0.1", 2200))}
        mock_create.return_value = mock_sandbox

        custom_pubkey = MagicMock(return_value="ssh-rsa custom_key")
        custom_builder = MagicMock(return_value=MagicMock())
        custom_append = MagicMock(return_value=True)

        launcher = SandboxLauncher(
            build_image_fn=custom_builder,
            load_pubkey_fn=custom_pubkey,
            append_ssh_fn=custom_append,
            repo_root=Path("/fake/root"),
        )

        req = LaunchRequest(name="custom-launch")
        running = launcher.launch(req, register_ssh_config=True)

        custom_pubkey.assert_called_once()
        custom_builder.assert_called_once()
        custom_append.assert_called_once_with(
            instance_name=running.sandbox_name,
            ssh_host="10.0.0.1",
            ssh_port=2200,
        )
        self.assertEqual(running.sandbox_id, "sb-launcher-1")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_skips_ssh_config_when_disabled(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-launcher-2"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {22: MagicMock(tcp_socket=("10.0.0.1", 2200))}
        mock_create.return_value = mock_sandbox

        custom_append = MagicMock()
        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            append_ssh_fn=custom_append,
        )

        req = LaunchRequest(name="no-ssh-reg")
        launcher.launch(req, register_ssh_config=False)

        custom_append.assert_not_called()

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_container_exit_raises_runtime_error(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-fail"
        mock_sandbox.poll.return_value = 1
        mock_sandbox.stderr.read.return_value = "Fatal error on startup"
        mock_create.return_value = mock_sandbox

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
        )
        req = LaunchRequest(name="failing-box")

        with self.assertRaises(RuntimeError) as ctx:
            launcher.launch(req)
        self.assertIn("Container terminated with exit code 1", str(ctx.exception))

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launch_sandbox_convenience_function(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-func-1"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        req = LaunchRequest(name="func-app")
        sb, resp = launch_sandbox(
            req,
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
        )

        self.assertEqual(sb.object_id, "sb-func-1")
        self.assertEqual(resp.sandbox_id, "sb-func-1")


if __name__ == "__main__":
    unittest.main()
