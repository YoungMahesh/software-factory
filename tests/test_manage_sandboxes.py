"""Unit tests for Modal sandbox management script."""

import json
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from sandbox.lifecycle import (
    clear_sandbox_metadata_cache,
    resolve_app_name,
    resolve_sandbox_connection_info,
)
from scripts.manage_sandboxes import (
    get_sandboxes,
    resolve_instance_name,
    terminate_sandboxes,
)


class TestManageSandboxes(TestCase):
    def setUp(self):
        clear_sandbox_metadata_cache()

    def tearDown(self):
        clear_sandbox_metadata_cache()

    def test_resolve_instance_name_from_tags(self):
        sb = MagicMock()
        sb.get_tags.return_value = {"instance_name": "software-factory-custom"}
        name = resolve_instance_name(sb)
        self.assertEqual(name, "software-factory-custom")

    def test_resolve_instance_name_from_remote_control_log(self):
        sb = MagicMock()
        sb.get_tags.return_value = {}
        proc = MagicMock()
        proc.stdout.read.return_value = (
            'Instance name set to "software-factory-abc12345".\n'
            'Open https://antigravity.google.com and look for "software-factory-abc12345".\n'
        )
        sb.exec.return_value = proc

        name = resolve_instance_name(sb)
        self.assertEqual(name, "software-factory-abc12345")

    def test_resolve_instance_name_from_config_json(self):
        sb = MagicMock()
        sb.get_tags.return_value = {}

        def mock_exec(*args, **kwargs):
            proc = MagicMock()
            if "/tmp/agy-remote-control.log" in args:
                proc.stdout.read.return_value = "No match"
            elif "/root/.gemini/config/config.json" in args:
                proc.stdout.read.return_value = json.dumps({
                    "userSettings": {
                        "cliRemoteControlHostname": "software-factory-from-config"
                    }
                })
            else:
                proc.stdout.read.return_value = ""
            return proc

        sb.exec.side_effect = mock_exec

        name = resolve_instance_name(sb)
        self.assertEqual(name, "software-factory-from-config")

    def test_resolve_instance_name_from_env(self):
        sb = MagicMock()
        sb.get_tags.return_value = {}

        def mock_exec(*args, **kwargs):
            proc = MagicMock()
            if "printenv" in args:
                proc.stdout.read.return_value = "FOO=BAR\nSANDBOX_NAME=t3-antigravity-test-env\n"
            else:
                proc.stdout.read.return_value = ""
            return proc

        sb.exec.side_effect = mock_exec

        name = resolve_instance_name(sb)
        self.assertEqual(name, "t3-antigravity-test-env")

    def test_resolve_app_name_from_tags(self):
        sb = MagicMock()
        sb.get_tags.return_value = {"app_name": "resumed-sandbox"}
        app_name = resolve_app_name(sb)
        self.assertEqual(app_name, "resumed-sandbox")

    def test_resolve_app_name_from_env(self):
        sb = MagicMock()
        sb.get_tags.return_value = {}
        proc = MagicMock()
        proc.stdout.read.return_value = "resumed-snapshot-abc\n"
        sb.exec.return_value = proc

        app_name = resolve_app_name(sb, fallback="fallback-app")
        self.assertEqual(app_name, "resumed-snapshot-abc")

    def test_resolve_app_name_fallback(self):
        sb = MagicMock()
        sb.get_tags.return_value = {}
        sb.exec.side_effect = Exception("failed")

        app_name = resolve_app_name(sb, fallback="ap-12345")
        self.assertEqual(app_name, "ap-12345")

    def test_terminate_sandboxes_dry_run(self):
        results = terminate_sandboxes(["sb-1", "sb-2"], dry_run=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "dry-run")
        self.assertEqual(results[1]["status"], "dry-run")

    @patch("modal.Sandbox.from_id")
    def test_terminate_sandboxes_live(self, mock_from_id):
        mock_sb = MagicMock()
        mock_sb.poll.return_value = 137
        mock_from_id.return_value = mock_sb

        results = terminate_sandboxes(["sb-test-123"], dry_run=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "terminated")
        self.assertEqual(results[0]["exit_code"], 137)
        mock_sb.terminate.assert_called_once_with(wait=True)

    @patch("modal.App.lookup")
    @patch("modal.Sandbox.list")
    def test_get_sandboxes_running_and_stopped(self, mock_list, mock_app_lookup):
        mock_app = MagicMock()
        mock_app.app_id = "ap-123"
        mock_app_lookup.return_value = mock_app

        sb_running = MagicMock()
        sb_running.object_id = "sb-running"
        sb_running.poll.return_value = None
        sb_running.get_tags.return_value = {
            "name": "sf-active",
            "created_at": "2026-11-12T12:00:00Z",
            "timeout_secs": "79200",
        }

        # Configure tunnels
        mock_ssh_tunnel = MagicMock()
        mock_ssh_tunnel.tcp_socket = ("r479.modal.host", 36511)
        mock_t3_tunnel = MagicMock()
        mock_t3_tunnel.url = "https://ta-01m6wzp5m0w6nvdxkf82b19hpv-3775-i9leqkuiv35e5ifa64rpynvkw.w.modal.host"
        sb_running.tunnels.return_value = {22: mock_ssh_tunnel, 3775: mock_t3_tunnel}

        # Mock pairing file exec
        exec_proc = MagicMock()
        exec_proc.wait.return_value = 0
        exec_proc.stdout.read.return_value = json.dumps({"credential": "LDF3EM8HZ4G8"})
        sb_running.exec.return_value = exec_proc

        sb_stopped = MagicMock()
        sb_stopped.object_id = "sb-stopped"
        sb_stopped.poll.return_value = 0

        mock_list.return_value = [sb_running, sb_stopped]

        results = get_sandboxes(app_name="software-factory")
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["running"])
        self.assertEqual(results[0]["name"], "sf-active")
        self.assertEqual(
            results[0]["ssh_command"],
            "ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p 36511 root@r479.modal.host",
        )
        self.assertEqual(
            results[0]["ssh_config"],
            (
                "Host sf-active\n"
                "  HostName r479.modal.host\n"
                "  Port 36511\n"
                "  User root\n"
                "  IdentityFile ~/.ssh/modal-sandbox\n"
                "  StrictHostKeyChecking no\n"
                "  UserKnownHostsFile /dev/null\n"
            ),
        )
        self.assertEqual(
            results[0]["t3_pair_url"],
            "https://ta-01m6wzp5m0w6nvdxkf82b19hpv-3775-i9leqkuiv35e5ifa64rpynvkw.w.modal.host/pair#token=LDF3EM8HZ4G8",
        )
        self.assertEqual(results[0]["created_at"], "2026-11-12T12:00:00Z")
        self.assertEqual(results[0]["timeout_secs"], 79200)
        self.assertFalse(results[1]["running"])
        self.assertIsNone(results[1]["ssh_command"])
        self.assertIsNone(results[1]["ssh_config"])
        self.assertIsNone(results[1]["t3_pair_url"])

    @patch("modal.Sandbox.list")
    def test_get_sandboxes_all_apps_includes_snapshots(self, mock_list):
        sb_repo = MagicMock()
        sb_repo.object_id = "sb-repo"
        sb_repo.poll.return_value = None
        sb_repo.get_tags.return_value = {"instance_name": "software-factory-123", "app_name": "software-factory"}

        sb_snap = MagicMock()
        sb_snap.object_id = "sb-snap"
        sb_snap.poll.return_value = None
        sb_snap.get_tags.return_value = {"instance_name": "resumed-snapshot-abc", "app_name": "resumed-snapshot"}

        mock_list.return_value = [sb_repo, sb_snap]

        results = get_sandboxes(all_apps=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "software-factory-123")
        self.assertEqual(results[0]["app_name"], "software-factory")
        self.assertEqual(results[1]["name"], "resumed-snapshot-abc")
        self.assertEqual(results[1]["app_name"], "resumed-snapshot")

    def test_resolve_sandbox_connection_info_caching(self):
        sb = MagicMock()
        sb.object_id = "sb-cache-test"
        mock_ssh_tunnel = MagicMock()
        mock_ssh_tunnel.tcp_socket = ("r100.modal.host", 2222)
        mock_t3_tunnel = MagicMock()
        mock_t3_tunnel.url = "https://t3-cached.modal.host"
        sb.tunnels.return_value = {22: mock_ssh_tunnel, 3775: mock_t3_tunnel}

        exec_proc = MagicMock()
        exec_proc.wait.return_value = 0
        exec_proc.stdout.read.return_value = json.dumps({"credential": "TOKEN_CACHED"})
        sb.exec.return_value = exec_proc

        cmd1, url1 = resolve_sandbox_connection_info(sb)
        self.assertEqual(cmd1, "ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p 2222 root@r100.modal.host")
        self.assertEqual(url1, "https://t3-cached.modal.host/pair#token=TOKEN_CACHED")
        self.assertEqual(sb.tunnels.call_count, 1)

        # Second call hits cache; sb.tunnels is NOT called again
        cmd2, url2 = resolve_sandbox_connection_info(sb)
        self.assertEqual(cmd2, cmd1)
        self.assertEqual(url2, url1)
        self.assertEqual(sb.tunnels.call_count, 1)

        # After clearing cache, sb.tunnels is called again
        clear_sandbox_metadata_cache(sb.object_id)
        cmd3, url3 = resolve_sandbox_connection_info(sb)
        self.assertEqual(cmd3, cmd1)
        self.assertEqual(sb.tunnels.call_count, 2)

    def test_resolve_sandbox_connection_info_fallback(self):
        sb = MagicMock()
        sb.object_id = "sb-no-tunnels"
        sb.tunnels.return_value = {}

        cmd, url = resolve_sandbox_connection_info(sb)
        self.assertEqual(cmd, "modal shell sb-no-tunnels")
        self.assertIsNone(url)


if __name__ == "__main__":
    main()
