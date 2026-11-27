"""Unit tests for Control-Plane-backed Cloudflare Pages documentation deployment."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.apps._store import FactoryStateStore, set_default_store
from sandbox.docs_deploy import (
    DocsDeployConflictError,
    DocsDeployRecord,
    build_docs_site,
    execute_docs_deploy,
    publish_docs_to_cloudflare,
    set_docs_deploy_dispatcher,
    write_deploy_info_json,
)
from sandbox.function import web_app

AUTH_ENV = {
    "WEB_UI_USERNAME": "admin",
    "WEB_UI_PASSWORD": "secretpassword",
}
BASIC_AUTH = {
    "Authorization": f"Basic {base64.b64encode(b'admin:secretpassword').decode('utf-8')}",
}


class TestDocsDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.store = FactoryStateStore(self.tmp_path / "state")
        set_default_store(self.store)
        set_docs_deploy_dispatcher(None)

    def tearDown(self):
        set_docs_deploy_dispatcher(None)
        set_default_store(None)
        self.tmp.cleanup()

    def test_store_create_single_flight_stale_and_dashboard_independence(self):
        dash = self.store.create_dashboard_deploy(control_plane_url="https://cp.modal.run")
        self.assertEqual(dash.status, "queued")

        rec = self.store.create_docs_deploy()
        self.assertTrue(rec.deploy_id.startswith("docs-"))
        self.assertEqual(rec.status, "queued")
        self.assertEqual(self.store.get_latest_docs_deploy().deploy_id, rec.deploy_id)

        with self.assertRaises(DocsDeployConflictError):
            self.store.create_docs_deploy()

        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
        self.store.update_docs_deploy(rec.deploy_id, updated_at=stale_ts)
        rec2 = self.store.create_docs_deploy()
        self.assertNotEqual(rec2.deploy_id, rec.deploy_id)

    def test_write_deploy_info_json(self):
        site_dir = self.tmp_path / "site"
        site_dir.mkdir(parents=True)
        info_path = write_deploy_info_json(
            site_dir,
            commit="1234567890abcdef",
            commit_short="1234567",
            deployed_at="2026-11-27T12:00:00Z",
        )
        parsed = json.loads(info_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed,
            {
                "commit": "1234567890abcdef",
                "commit_short": "1234567",
                "deployed_at": "2026-11-27T12:00:00Z",
            },
        )

    @patch("sandbox.docs_deploy.subprocess.run")
    @patch("sandbox.docs_deploy.resolve_docs_builder", return_value="/usr/local/bin/zensical")
    def test_build_docs_site_writes_deploy_info_and_handles_failure(self, _mock_builder, mock_run):
        repo_dir = self.tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")

        def _fake_build(cmd, **_kwargs):
            (repo_dir / "site").mkdir(exist_ok=True)
            (repo_dir / "site" / "index.html").write_text("<h1>Docs</h1>", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "Built cleanly\n", "")

        mock_run.side_effect = _fake_build
        logs: list[str] = []
        site_dir = build_docs_site(repo_dir, commit="deadbeefcafe", commit_short="deadbee", log_cb=logs.append)
        self.assertEqual(site_dir, repo_dir / "site")
        info = json.loads((site_dir / "deploy-info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["commit"], "deadbeefcafe")
        self.assertEqual(info["commit_short"], "deadbee")
        self.assertIn("Built cleanly", logs)

        mock_run.side_effect = None
        mock_run.return_value = subprocess.CompletedProcess([], 1, "", "Broken link")
        with self.assertRaises(RuntimeError) as ctx:
            build_docs_site(repo_dir, commit="deadbeefcafe", commit_short="deadbee", log_cb=logs.append)
        self.assertIn("Documentation build failed", str(ctx.exception))

    @patch("sandbox.docs_deploy.subprocess.run")
    @patch("sandbox.docs_deploy.resolve_wrangler_command", return_value=["wrangler"])
    def test_publish_docs_to_cloudflare_invokes_wrangler(self, _mock_wrangler, mock_run):
        site_dir = self.tmp_path / "site"
        site_dir.mkdir()
        mock_run.return_value = subprocess.CompletedProcess([], 0, "Success!\n", "")
        logs: list[str] = []
        publish_docs_to_cloudflare(
            site_dir,
            project_name="modal-sandboxes-docs",
            branch="main",
            account_id="acct-123",
            api_token="cf-secret-tok",
            repo_dir=self.tmp_path,
            log_cb=logs.append,
        )
        args = mock_run.call_args.args[0]
        self.assertEqual(
            args,
            [
                "wrangler",
                "pages",
                "deploy",
                str(site_dir),
                "--project-name=modal-sandboxes-docs",
                "--branch=main",
                "--commit-dirty=true",
            ],
        )
        env_passed = mock_run.call_args.kwargs["env"]
        self.assertEqual(env_passed["CI"], "1")
        self.assertEqual(env_passed["CLOUDFLARE_ACCOUNT_ID"], "acct-123")
        self.assertEqual(env_passed["CLOUDFLARE_API_TOKEN"], "cf-secret-tok")

    def test_execute_docs_deploy_success_and_missing_credentials(self):
        rec = self.store.create_docs_deploy()
        env = {
            "GH_ORG_NAME": "sFactory0",
            "GH_TOKEN": "ghp_tok",
            "CLOUDFLARE_ACCOUNT_ID": "acct-1",
            "CLOUDFLARE_API_TOKEN": "cf-tok",
            "APPS_BASE_DOMAIN": "apps.example.com",
        }
        seen_publish: list[dict] = []

        def _fake_build(repo_dir: Path, **kwargs) -> Path:
            site = repo_dir / "site"
            site.mkdir(parents=True, exist_ok=True)
            write_deploy_info_json(site, commit=kwargs["commit"], commit_short=kwargs["commit_short"])
            kwargs["log_cb"]("Zensical ok")
            return site

        def _fake_publish(site_dir: Path, **kwargs) -> None:
            seen_publish.append({"site_dir": site_dir, **kwargs})
            kwargs["log_cb"]("Wrangler ok")

        with patch.dict(os.environ, env, clear=True):
            done = execute_docs_deploy(
                rec.deploy_id,
                store=self.store,
                clone_fn=lambda dest, **_kw: "deadbee",
                build_fn=_fake_build,
                publish_fn=_fake_publish,
            )

        self.assertEqual(done.status, "ready")
        self.assertEqual(done.target_url, "https://docs.apps.example.com")
        self.assertEqual(done.project_name, "modal-sandboxes-docs")
        self.assertEqual(done.branch, "main")
        self.assertEqual(done.commit_short, "deadbee")
        self.assertIn("Zensical ok", done.logs)
        self.assertIn("Wrangler ok", done.logs)
        self.assertEqual(seen_publish[0]["account_id"], "acct-1")
        self.assertEqual(seen_publish[0]["api_token"], "cf-tok")

        rec_fail = self.store.create_docs_deploy()
        with patch.dict(os.environ, {"GH_ORG_NAME": "sFactory0", "GH_TOKEN": "ghp_tok"}, clear=True):
            failed = execute_docs_deploy(rec_fail.deploy_id, store=self.store)
        self.assertEqual(failed.status, "failed")
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", failed.error or "")

    def test_api_routes_queue_conflict_and_status(self):
        dispatched: list[str] = []
        set_docs_deploy_dispatcher(lambda deploy_id: dispatched.append(deploy_id))
        with patch.dict(os.environ, AUTH_ENV, clear=True):
            client = TestClient(web_app)
            empty_res = client.get("/api/docs/deploy", headers=BASIC_AUTH)
            self.assertEqual(empty_res.status_code, 200)
            self.assertIsNone(empty_res.json()["deploy"])

            create_res = client.post("/api/docs/deploy", headers=BASIC_AUTH)
            self.assertEqual(create_res.status_code, 202)
            body = DocsDeployRecord.model_validate(create_res.json())
            self.assertEqual(dispatched, [body.deploy_id])

            conflict_res = client.post("/api/docs/deploy", headers=BASIC_AUTH)
            self.assertEqual(conflict_res.status_code, 409)

            get_res = client.get(f"/api/docs/deploy/{body.deploy_id}", headers=BASIC_AUTH)
            self.assertEqual(get_res.status_code, 200)
            self.assertEqual(get_res.json()["deploy_id"], body.deploy_id)

            missing_res = client.get("/api/docs/deploy/missing-id", headers=BASIC_AUTH)
            self.assertEqual(missing_res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
