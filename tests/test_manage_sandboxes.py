"""Unit tests for Modal sandbox management script."""

import json
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from sandbox.lifecycle import resolve_app_name
from scripts.manage_sandboxes import (
    get_sandboxes,
    resolve_instance_name,
    terminate_sandboxes,
)


class TestManageSandboxes(TestCase):
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
        sb_running.get_tags.return_value = {"name": "sf-active"}

        sb_stopped = MagicMock()
        sb_stopped.object_id = "sb-stopped"
        sb_stopped.poll.return_value = 0

        mock_list.return_value = [sb_running, sb_stopped]

        results = get_sandboxes(app_name="software-factory")
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["running"])
        self.assertEqual(results[0]["name"], "sf-active")
        self.assertFalse(results[1]["running"])

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


if __name__ == "__main__":
    main()
