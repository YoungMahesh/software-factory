"""Tests for per-sandbox T3 Code Pairing URL inspection and generation endpoints."""

import base64
from datetime import datetime, timezone
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.lifecycle import (
    _SANDBOX_METADATA_CACHE,
    clear_sandbox_metadata_cache,
    record_sandbox_connection_info,
)
from sandbox.t3_pairing._service import merge_pairing_records
from sandbox.web import app


def _make_exec_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.wait.return_value = returncode
    proc.stdout.read.return_value = stdout
    proc.stderr.read.return_value = stderr
    return proc


class TestSandboxT3PairingAPI(unittest.TestCase):
    def setUp(self):
        clear_sandbox_metadata_cache()
        self.env_patcher = patch.dict(
            os.environ,
            {
                "WEB_UI_USERNAME": "testadmin",
                "WEB_UI_PASSWORD": "testpassword",
            },
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})

    def tearDown(self):
        clear_sandbox_metadata_cache()
        self.env_patcher.stop()

    @patch("sandbox.t3_pairing._service.lookup_sandbox")
    def test_list_links_merges_sources_excludes_factory_handoff_and_orders_chronologically(self, mock_lookup):
        sb = MagicMock()
        sb.object_id = "sb-1"
        sb.poll.return_value = None
        tunnel = MagicMock()
        tunnel.url = "https://t3-custom.modal.host/"
        sb.tunnels.return_value = {4100: tunnel}

        record_sandbox_connection_info(
            "sb-1",
            t3_pair_url="https://t3-custom.modal.host/pair#token=BOOT_TOK",
            has_t3=True,
        )

        probe_payload = {
            "runtime_present": True,
            "runtime_port": 4100,
            "env_t3_port": 4100,
            "server_running": True,
            "boot_record": {
                "id": "id-boot",
                "credential": "BOOT_TOK",
                "expiresAt": "2099-01-01T00:00:00Z",
            },
            "saved_links": [
                {
                    "id": "id-gen-1",
                    "credential": "GEN_TOK_1",
                    "url": "https://old.modal.host/pair#token=GEN_TOK_1",
                    "label": "Dashboard Pairing",
                    "created_at": "2026-11-27T09:10:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            ],
            "db_readable": True,
            "db_rows": [
                {
                    "id": "id-boot",
                    "credential": "BOOT_TOK",
                    "label": None,
                    "created_at": "2026-11-27T09:00:00Z",
                    "expires_at": "2026-11-27T09:05:00Z",
                    "consumed_at": "2026-11-27T09:01:00Z",
                    "revoked_at": None,
                },
                {
                    "id": "id-handoff",
                    "credential": "HANDOFF_TOK",
                    "label": "Factory App Handoff",
                    "created_at": "2026-11-27T09:02:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": None,
                },
                {
                    "id": "id-expired",
                    "credential": "EXPIRED_TOK",
                    "label": "Dashboard Pairing",
                    "created_at": "2026-11-27T09:05:00Z",
                    "expires_at": "2020-01-01T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": None,
                },
                {
                    "id": "id-revoked",
                    "credential": "REVOKED_TOK",
                    "label": "Dashboard Pairing",
                    "created_at": "2026-11-27T09:06:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": "2026-11-27T09:07:00Z",
                },
                {
                    "id": "id-gen-1",
                    "credential": "GEN_TOK_1",
                    "label": "Dashboard Pairing",
                    "created_at": "2026-11-27T09:10:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": None,
                },
            ],
        }
        sb.exec.return_value = _make_exec_proc(0, json.dumps(probe_payload))
        mock_lookup.return_value = (sb, "team-a", None)

        res = self.client.get("/api/sandboxes/sb-1/t3-links?profile=team-a")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        mock_lookup.assert_called_once_with("sb-1", profile="team-a")
        self.assertTrue(data["available"])
        self.assertEqual(data["t3_url"], "https://t3-custom.modal.host")

        links = data["links"]
        self.assertEqual(
            [item["id"] for item in links],
            ["id-boot", "id-expired", "id-revoked", "id-gen-1"],
        )
        self.assertEqual(links[0]["status"], "used")
        self.assertEqual(links[1]["status"], "expired")
        self.assertEqual(links[2]["status"], "expired")
        self.assertEqual(links[3]["status"], "active")
        self.assertEqual(links[3]["url"], "https://t3-custom.modal.host/pair#token=GEN_TOK_1")

    def test_merge_ignores_tokenless_cache_url_and_uses_cli_fallback_when_db_unreadable(self):
        record_sandbox_connection_info("sb-bare", t3_pair_url="https://t3.modal.host", has_t3=True)
        probe = {
            "boot_record": {
                "id": "id-boot",
                "credential": "BOOT1",
                "created_at": "2026-11-27T09:00:00Z",
                "expiresAt": "2099-01-01T00:00:00Z",
            },
            "saved_links": [
                {
                    "id": "id-saved",
                    "credential": "SAVED1",
                    "created_at": "2026-11-27T09:01:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            ],
            "db_readable": False,
            "db_rows": [],
        }
        entries = merge_pairing_records(
            "sb-bare",
            "https://t3.modal.host",
            probe,
            now_dt=datetime(2026, 11, 27, 9, 30, tzinfo=timezone.utc),
            active_cli_ids={"id-saved"},
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].id, "id-boot")
        self.assertEqual(entries[0].status, "used")
        self.assertEqual(entries[1].id, "id-saved")
        self.assertEqual(entries[1].status, "active")

    @patch("sandbox.t3_pairing._service.lookup_sandbox")
    def test_list_links_unavailable_when_stopped_or_t3_not_running(self, mock_lookup):
        sb_stopped = MagicMock()
        sb_stopped.object_id = "sb-stop"
        sb_stopped.poll.return_value = 0
        mock_lookup.return_value = (sb_stopped, "default", None)

        res = self.client.get("/api/sandboxes/sb-stop/t3-links")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["available"])
        self.assertEqual(res.json()["links"], [])

        sb_dead_t3 = MagicMock()
        sb_dead_t3.object_id = "sb-dead-t3"
        sb_dead_t3.poll.return_value = None
        tunnel = MagicMock()
        tunnel.url = "https://t3.modal.host"
        sb_dead_t3.tunnels.return_value = {3775: tunnel}
        sb_dead_t3.exec.return_value = _make_exec_proc(
            0,
            json.dumps({"runtime_present": True, "runtime_port": 3775, "server_running": False}),
        )
        mock_lookup.return_value = (sb_dead_t3, "default", None)

        res2 = self.client.get("/api/sandboxes/sb-dead-t3/t3-links")
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json()["available"])
        self.assertIn("not running", res2.json()["reason"])

    @patch("sandbox.t3_pairing._service.lookup_sandbox")
    def test_list_and_generate_return_404_when_sandbox_missing(self, mock_lookup):
        mock_lookup.return_value = (None, None, "Sandbox not found")
        self.assertEqual(self.client.get("/api/sandboxes/sb-missing/t3-links").status_code, 404)
        self.assertEqual(self.client.post("/api/sandboxes/sb-missing/t3-links").status_code, 404)

    @patch("sandbox.t3_pairing._service.lookup_sandbox")
    def test_generate_link_mints_persists_and_updates_cache(self, mock_lookup):
        sb = MagicMock()
        sb.object_id = "sb-gen"
        sb.poll.return_value = None
        tunnel = MagicMock()
        tunnel.url = "https://t3-gen.modal.host"
        sb.tunnels.return_value = {3775: tunnel}

        record_sandbox_connection_info(
            "sb-gen",
            ssh_command="ssh box",
            t3_pair_url="https://t3-gen.modal.host/pair#token=OLD_BOOT",
            has_t3=True,
        )

        probe_payload = {
            "runtime_present": True,
            "runtime_port": 3775,
            "server_running": True,
        }
        created_payload = {
            "id": "new-link-id",
            "credential": "FRESH_TOK_99",
            "label": "Dashboard Pairing",
            "expiresAt": "2099-01-02T00:00:00Z",
        }
        sb.exec.side_effect = [
            _make_exec_proc(0, json.dumps(probe_payload)),
            _make_exec_proc(0, json.dumps(created_payload)),
            _make_exec_proc(0, ""),
        ]
        mock_lookup.return_value = (sb, "prof-1", None)

        res = self.client.post("/api/sandboxes/sb-gen/t3-links?profile=prof-1")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["id"], "new-link-id")
        self.assertEqual(body["url"], "https://t3-gen.modal.host/pair#token=FRESH_TOK_99")
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["label"], "Dashboard Pairing")
        self.assertEqual(body["expires_at"], "2099-01-02T00:00:00Z")

        self.assertEqual(
            _SANDBOX_METADATA_CACHE["sb-gen"]["t3_pair_url"],
            "https://t3-gen.modal.host/pair#token=FRESH_TOK_99",
        )
        self.assertEqual(_SANDBOX_METADATA_CACHE["sb-gen"]["ssh_command"], "ssh box")

        exec_calls = sb.exec.call_args_list
        self.assertEqual(
            exec_calls[1].args,
            (
                "t3", "auth", "pairing", "create",
                "--base-dir", "/root/.t3",
                "--ttl", "24h",
                "--label", "Dashboard Pairing",
                "--json",
            ),
        )
        self.assertEqual(exec_calls[2].args[0], "python3")
        self.assertEqual(exec_calls[2].args[1], "-c")
        persisted = json.loads(exec_calls[2].args[3])
        self.assertEqual(persisted["credential"], "FRESH_TOK_99")
        self.assertEqual(persisted["id"], "new-link-id")

    @patch("sandbox.t3_pairing._service.lookup_sandbox")
    def test_generate_link_conflicts_when_stopped_or_unavailable_and_502_on_cli_failure(self, mock_lookup):
        sb_stop = MagicMock()
        sb_stop.poll.return_value = 137
        mock_lookup.return_value = (sb_stop, None, None)
        self.assertEqual(self.client.post("/api/sandboxes/sb-stop/t3-links").status_code, 409)

        sb_no_t3 = MagicMock()
        sb_no_t3.poll.return_value = None
        sb_no_t3.tunnels.return_value = {}
        sb_no_t3.exec.return_value = _make_exec_proc(0, json.dumps({"runtime_present": False}))
        mock_lookup.return_value = (sb_no_t3, None, None)
        self.assertEqual(self.client.post("/api/sandboxes/sb-no-t3/t3-links").status_code, 409)

        sb_cli_err = MagicMock()
        sb_cli_err.poll.return_value = None
        tunnel = MagicMock()
        tunnel.url = "https://t3.modal.host"
        sb_cli_err.tunnels.return_value = {3775: tunnel}
        sb_cli_err.exec.side_effect = [
            _make_exec_proc(0, json.dumps({"runtime_present": True, "server_running": True})),
            _make_exec_proc(1, "", "pairing command failed"),
        ]
        mock_lookup.return_value = (sb_cli_err, None, None)
        res_err = self.client.post("/api/sandboxes/sb-err/t3-links")
        self.assertEqual(res_err.status_code, 502)
        self.assertIn("pairing command failed", res_err.json()["detail"])


if __name__ == "__main__":
    unittest.main()
