"""Tests for auto-pruning Factory App cards on sandbox termination and shared repo cleanup."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import modal

from sandbox.apps import (
    FactoryAppRecord,
    FactoryStateStore,
    LaunchCoordinator,
    LaunchRequestRecord,
    PrimeSandboxRecord,
    set_coordinator_factory,
    set_default_store,
    set_launch_dispatcher,
)
from sandbox.web import app


class TestWorktreeAndTerminationSync(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {"WEB_UI_USERNAME": "testadmin", "WEB_UI_PASSWORD": "testpassword"},
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})

    def tearDown(self):
        set_coordinator_factory(None)
        set_launch_dispatcher(None)
        set_default_store(None)
        self.env_patcher.stop()

    def test_terminate_sandbox_deletes_bound_factory_apps_and_keeps_others(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            set_default_store(store)
            store.save_prime(
                PrimeSandboxRecord(prime_key="k1", status="ready", sandbox_id="sb-dead")
            )
            app1 = FactoryAppRecord(
                app_id="app_1",
                slug="a1",
                title="A1",
                status="ready",
                sandbox_id="sb-dead",
                latest_request_id="req_1",
            )
            app2 = FactoryAppRecord(
                app_id="app_2",
                slug="a2",
                title="A2",
                status="ready",
                sandbox_id="sb-dead",
                latest_request_id="req_2",
            )
            app_other = FactoryAppRecord(
                app_id="app_other",
                slug="other",
                title="Other",
                status="ready",
                sandbox_id="sb-alive",
                latest_request_id="req_other",
            )
            for rec, req_id in ((app1, "req_1"), (app2, "req_2"), (app_other, "req_other")):
                store.create_app_and_launch(
                    rec,
                    LaunchRequestRecord(request_id=req_id, app_id=rec.app_id, status="ready"),
                )

            with patch("sandbox.web.terminate_sandbox", return_value={"id": "sb-dead", "status": "terminated"}):
                res = self.client.post("/api/sandboxes/sb-dead/terminate")
                self.assertEqual(res.status_code, 200)

            self.assertIsNone(store.get_app("app_1"))
            self.assertIsNone(store.get_app("app_2"))
            self.assertIsNone(store.get_launch("req_1"))
            self.assertIsNotNone(store.get_app("app_other"))
            self.assertEqual(store.get_prime("k1").status, "stopped")

    def test_list_apps_auto_prunes_terminated_or_missing_ready_sandboxes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb_alive = MagicMock(poll=MagicMock(return_value=None))
            sb_exited = MagicMock(poll=MagicMock(return_value=137))

            def _lookup(sid, **_kw):
                if sid == "sb-alive":
                    return sb_alive
                if sid == "sb-exited":
                    return sb_exited
                if sid == "sb-gone":
                    raise modal.exception.NotFoundError("not found")
                raise RuntimeError("transient network error")

            store.save_app(FactoryAppRecord(app_id="app_alive", slug="alive", title="Alive", status="ready", sandbox_id="sb-alive"))
            store.save_app(FactoryAppRecord(app_id="app_exited", slug="exited", title="Exited", status="ready", sandbox_id="sb-exited"))
            store.save_app(FactoryAppRecord(app_id="app_gone", slug="gone", title="Gone", status="ready", sandbox_id="sb-gone"))
            store.save_app(FactoryAppRecord(app_id="app_flaky", slug="flaky", title="Flaky", status="ready", sandbox_id="sb-err"))
            store.save_app(FactoryAppRecord(app_id="app_prov", slug="prov", title="Prov", status="provisioning", sandbox_id="sb-exited"))

            coord = LaunchCoordinator(store=store, sandbox_from_id_fn=_lookup, list_snapshots_fn=lambda **_kw: [], env={})
            views = coord.list_apps_with_status()
            ids = {v.app_id for v in views}
            self.assertEqual(ids, {"app_alive", "app_flaky", "app_prov"})
            self.assertIsNone(store.get_app("app_exited"))
            self.assertIsNone(store.get_app("app_gone"))

    def test_delete_worktree_app_preserves_shared_base_repo_for_sibling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = MagicMock()
            sb.poll.return_value = None
            calls = []

            def _exec(*cmd, **_kw):
                calls.append(cmd)
                proc = MagicMock()
                proc.wait.return_value = 0
                proc.stdout.read.return_value = ""
                proc.stderr.read.return_value = ""
                return proc

            sb.exec.side_effect = _exec
            store.save_prime(PrimeSandboxRecord(prime_key="k", status="ready", sandbox_id="sb-1"))
            a1 = FactoryAppRecord(
                app_id="a1", slug="repo-1", title="R1", repo="org/repo", prime_key="k",
                repo_base_path="/root/repo", workspace_path="/root/.t3/worktrees/repo/wt1",
                status="ready", sandbox_id="sb-1",
            )
            a2 = FactoryAppRecord(
                app_id="a2", slug="repo-2", title="R2", repo="org/repo", prime_key="k",
                repo_base_path="/root/repo", workspace_path="/root/.t3/worktrees/repo/wt2",
                status="ready", sandbox_id="sb-1",
            )
            store.save_app(a1)
            store.save_app(a2)

            coord = LaunchCoordinator(store=store, sandbox_from_id_fn=lambda _s, **_kw: sb, env={})
            self.assertTrue(coord.delete_factory_app("a1"))
            cmd_strs = [" ".join(c) for c in calls]
            self.assertTrue(any("git -C /root/repo worktree remove --force /root/.t3/worktrees/repo/wt1" in s for s in cmd_strs))
            self.assertFalse(any("t3 project remove" in s for s in cmd_strs))
            self.assertFalse(any(s == "rm -rf /root/repo" for s in cmd_strs))
