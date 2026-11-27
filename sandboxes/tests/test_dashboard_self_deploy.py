"""Unit tests for Control-Plane-backed dashboard self-deployment."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.apps._store import FactoryStateStore, set_default_store
from sandbox.dashboard_self_deploy import (
    DashboardDeployConflictError,
    DashboardDeployRecord,
    clone_latest_main,
    ensure_headless_ssh_config,
    execute_dashboard_self_deploy,
    resolve_control_plane_ssh_private_key,
    set_dashboard_deploy_dispatcher,
)
from sandbox.function import web_app

AUTH_ENV = {
    "WEB_UI_USERNAME": "admin",
    "WEB_UI_PASSWORD": "secretpassword",
}
BASIC_AUTH = {
    "Authorization": f"Basic {base64.b64encode(b'admin:secretpassword').decode('utf-8')}",
}


class TestDashboardSelfDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.store = FactoryStateStore(self.tmp_path / "state")
        set_default_store(self.store)
        set_dashboard_deploy_dispatcher(None)

    def tearDown(self):
        set_dashboard_deploy_dispatcher(None)
        set_default_store(None)
        self.tmp.cleanup()

    def test_store_create_single_flight_and_stale_recovery(self):
        rec = self.store.create_dashboard_deploy("subdomain", control_plane_url="https://cp.modal.run")
        self.assertEqual(rec.target, "subdomain")
        self.assertEqual(rec.status, "queued")
        self.assertEqual(self.store.get_latest_dashboard_deploy().deploy_id, rec.deploy_id)

        with self.assertRaises(DashboardDeployConflictError):
            self.store.create_dashboard_deploy("apex")

        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
        self.store.update_dashboard_deploy(rec.deploy_id, updated_at=stale_ts)
        rec2 = self.store.create_dashboard_deploy("apex")
        self.assertEqual(rec2.target, "apex")
        self.assertNotEqual(rec2.deploy_id, rec.deploy_id)

    def test_resolve_control_plane_ssh_private_key_env_and_vault(self):
        with patch.dict(os.environ, {"RESOURCE_PLANE_SSH_PRIVATE_KEY": "KEY_DATA\n"}, clear=True):
            self.assertEqual(resolve_control_plane_ssh_private_key(), "KEY_DATA\n")

        with (
            patch.dict(
                os.environ,
                {"GH_ORG_NAME": "org", "GH_TOKEN": "tok", "AGE_PRIVATE_KEY": "AGE-SECRET"},
                clear=True,
            ),
            patch("sandbox.dashboard_self_deploy.fetch_vault_env_raw", return_value="VAULT_KEY\n") as mock_fetch,
        ):
            self.assertEqual(resolve_control_plane_ssh_private_key(), "VAULT_KEY\n")
            mock_fetch.assert_called_once_with(
                "software-factory",
                org_name="org",
                gh_token="tok",
                age_key="AGE-SECRET",
                target_filename="resource_plane_ssh",
            )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                resolve_control_plane_ssh_private_key()

    def test_ensure_headless_ssh_config_is_idempotent(self):
        ssh_dir = self.tmp_path / "ssh"
        ensure_headless_ssh_config(ssh_dir)
        cfg = ssh_dir / "config"
        first = cfg.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking accept-new", first)
        ensure_headless_ssh_config(ssh_dir)
        self.assertEqual(cfg.read_text(encoding="utf-8"), first)

    @patch("sandbox.dashboard_self_deploy.subprocess.run")
    def test_clone_latest_main_returns_short_sha(self, mock_run):
        mock_run.side_effect = [
            type("CP", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
            type("CP", (), {"returncode": 0, "stdout": "abc1234\n", "stderr": ""})(),
        ]
        sha = clone_latest_main(self.tmp_path / "repo", org_name="sFactory0", gh_token="ghp_test")
        self.assertEqual(sha, "abc1234")
        clone_args = mock_run.call_args_list[0].args[0]
        self.assertIn("https://github.com/sFactory0/software-factory.git", clone_args)
        self.assertIn("main", clone_args)

    def test_execute_dashboard_self_deploy_success_and_failure(self):
        rec = self.store.create_dashboard_deploy("subdomain", control_plane_url="https://cp.modal.run")
        env = {
            "GH_ORG_NAME": "sFactory0",
            "GH_TOKEN": "ghp_tok",
            "RESOURCE_PLANE_SSH_HOST": "1.2.3.4",
            "APPS_BASE_DOMAIN": "apps.example.com",
            "WEB_UI_USERNAME": "admin",
            "WEB_UI_PASSWORD": "pw",
        }
        seen_calls: list[dict] = []

        def _fake_deploy(vps_cfg, **kwargs):
            seen_calls.append({"vps": vps_cfg, **kwargs})
            kwargs["log_cb"]("Deployed staging")
            return 0

        with patch.dict(os.environ, env, clear=True), patch("sandbox.dashboard_self_deploy.ensure_headless_ssh_config"):
            done = execute_dashboard_self_deploy(
                rec.deploy_id,
                store=self.store,
                clone_fn=lambda dest, **_kw: "deadbee",
                resolve_ssh_key_fn=lambda: "-----BEGIN TEST-----\n",
                deploy_fn=_fake_deploy,
            )
        self.assertEqual(done.status, "ready")
        self.assertEqual(done.target_url, "https://dashboard.apps.example.com")
        self.assertEqual(done.commit_short, "deadbee")
        self.assertTrue(seen_calls[0]["subdomain"])
        self.assertEqual(seen_calls[0]["dashboard_commit"], "deadbee")
        self.assertFalse(seen_calls[0]["vps"].key_path.exists())

        rec_fail = self.store.create_dashboard_deploy("apex")
        with patch.dict(os.environ, env, clear=True), patch("sandbox.dashboard_self_deploy.ensure_headless_ssh_config"):
            failed = execute_dashboard_self_deploy(
                rec_fail.deploy_id,
                store=self.store,
                clone_fn=lambda dest, **_kw: "cafebabe",
                resolve_ssh_key_fn=lambda: "-----BEGIN TEST-----\n",
                deploy_fn=lambda _vps, **kwargs: (kwargs["log_cb"]("SSH error"), 1)[1],
            )
        self.assertEqual(failed.status, "failed")
        self.assertIn("SSH error", failed.error or "")

    def test_api_routes_queue_conflict_and_status(self):
        dispatched: list[str] = []
        set_dashboard_deploy_dispatcher(lambda deploy_id: dispatched.append(deploy_id))
        with patch.dict(os.environ, AUTH_ENV, clear=True):
            client = TestClient(web_app)
            empty_res = client.get("/api/dashboard/deploy", headers=BASIC_AUTH)
            self.assertEqual(empty_res.status_code, 200)
            self.assertIsNone(empty_res.json()["deploy"])

            create_res = client.post(
                "/api/dashboard/deploy",
                headers=BASIC_AUTH,
                json={"target": "subdomain"},
            )
            self.assertEqual(create_res.status_code, 202)
            body = DashboardDeployRecord.model_validate(create_res.json())
            self.assertEqual(dispatched, [body.deploy_id])

            conflict_res = client.post(
                "/api/dashboard/deploy",
                headers=BASIC_AUTH,
                json={"target": "apex"},
            )
            self.assertEqual(conflict_res.status_code, 409)

            get_res = client.get(f"/api/dashboard/deploy/{body.deploy_id}", headers=BASIC_AUTH)
            self.assertEqual(get_res.status_code, 200)
            self.assertEqual(get_res.json()["deploy_id"], body.deploy_id)

            missing_res = client.get("/api/dashboard/deploy/missing-id", headers=BASIC_AUTH)
            self.assertEqual(missing_res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
