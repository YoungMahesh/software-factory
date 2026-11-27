"""Tests for LaunchCoordinator orchestration, step-resume retry, failure cleanup, and app lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from sandbox.apps import (
    AppNotFoundError,
    AppSandboxStoppedError,
    CreateAppPayload,
    FactoryAppRecord,
    FactoryStateStore,
    LaunchCoordinator,
)
from sandbox.apps._sandbox_t3 import wait_for_t3_ready
from sandbox.core import LaunchResponse


class _FakeSandbox:
    def __init__(
        self,
        sandbox_id: str = "sb-live-1",
        *,
        running: bool = True,
        fail_cmd: str | None = None,
        fail_first_thread_start: bool = False,
    ):
        self.object_id = sandbox_id
        self.running = running
        self.fail_cmd = fail_cmd
        self.fail_first_thread_start = fail_first_thread_start
        self.thread_start_attempts = 0
        self.thread_created = False
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self.terminated = False

    def poll(self):
        return None if self.running else 137

    def terminate(self):
        self.terminated = True
        self.running = False

    def exec(self, *cmd: str, **_kwargs):
        cmd_str = " ".join(cmd)
        proc = MagicMock()
        stdin_chunks: list[str] = []
        proc.stdin = MagicMock()
        proc.stdin.write.side_effect = lambda data: stdin_chunks.append(
            data.decode("utf-8") if isinstance(data, bytes) else str(data)
        )

        def _wait():
            stdin_payload = "".join(stdin_chunks)
            self.calls.append((cmd, stdin_payload or None))
            if self.fail_first_thread_start and cmd[:3] == ("t3", "thread", "start"):
                self.thread_start_attempts += 1
                self.thread_created = True
                return 1
            if self.fail_cmd and self.fail_cmd in cmd_str:
                return 1
            return 0

        proc.wait.side_effect = _wait
        proc.stderr.read.return_value = f"failed: {cmd_str}" if (self.fail_cmd and self.fail_cmd in cmd_str) else ""

        if "create-app" in cmd_str:
            proc.stdout.read.return_value = "Scaffolded OK"
        elif "server-runtime.json" in cmd_str and "environment-id" in cmd_str:
            proc.stdout.read.return_value = json.dumps(
                {
                    "environment_id": "env-01",
                    "settings": {
                        "providerInstances": {
                            "antigravity": {"driver": "antigravity", "enabled": True},
                        }
                    },
                    "caches": {
                        "antigravity": {
                            "auth": {"status": "authenticated"},
                            "models": [
                                {"slug": "gemini-4-hydrogen", "isDefault": True},
                                {"slug": "gemini-3.8-flash"},
                            ],
                        }
                    },
                }
            )
        elif cmd[:3] == ("t3", "project", "add"):
            proc.stdout.read.return_value = ""
        elif cmd[:3] == ("t3", "thread", "list"):
            threads = (
                [{"threadId": "thread:recovered-1", "projectId": "proj-1"}] if self.thread_created else []
            )
            proc.stdout.read.side_effect = lambda: json.dumps({"threads": threads})
        elif cmd[:3] == ("t3", "thread", "start"):
            proc.stdout.read.return_value = json.dumps(
                {"threadId": "thread:abc-1", "projectId": "proj-1", "runId": "run-1"}
            )
        elif cmd[:3] == ("t3", "auth", "pairing"):
            proc.stdout.read.return_value = json.dumps({"credential": "pair-tok-xyz"})
        else:
            proc.stdout.read.return_value = ""
        return proc


class TestLaunchCoordinator(unittest.TestCase):
    def test_execute_launch_happy_path_nextjs_with_optional_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_volume = MagicMock()
            store = FactoryStateStore(root_dir=Path(tmpdir), volume=mock_volume)
            fake_sb = _FakeSandbox("sb-100")
            launch_resp = LaunchResponse(
                sandbox_id="sb-100",
                app_name="habit-tracker",
                sandbox_name="habit-tracker-deadbeef",
                t3_url="https://ta-100-3775.w.modal.host",
                t3_port=3775,
            )

            def _launch_with_many_logs(_req, *, log_cb=None):
                if log_cb is not None:
                    for i in range(25):
                        log_cb(f"boot line {i}")
                return fake_sb, launch_resp

            mock_launch = MagicMock(side_effect=_launch_with_many_logs)
            mock_db = MagicMock(
                return_value=SimpleNamespace(
                    name="habit_tracker",
                    connection_string="postgresql://u:p@db.example.com:5432/habit_tracker?sslmode=verify-full",
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                create_db_fn=mock_db,
                env={
                    "RESOURCE_PLANE_DOMAIN": "https://rp.example.com",
                    "RESOURCE_PLANE_ADMIN_TOKEN": "rp-secret",
                },
            )

            dispatched: list[str] = []
            _, req = coord.create_and_dispatch(
                CreateAppPayload(prompt="Habit tracker", thought_level="high"),
                dispatch_fn=dispatched.append,
            )
            self.assertEqual(dispatched, [req.request_id])
            commits_before = mock_volume.commit.call_count

            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.request.status, "ready")
            self.assertIsNotNone(res.request.handoff_expires_at)
            self.assertEqual(
                res.request.handoff_url,
                "https://ta-100-3775.w.modal.host/env-01/thread%3Aabc-1#token=pair-tok-xyz",
            )
            self.assertEqual(res.app.status, "ready")
            self.assertTrue(res.app.workspace_ready)
            self.assertIsNone(res.app.failed_step)
            self.assertEqual(res.app.database_name, "habit_tracker")
            self.assertLess(mock_volume.commit.call_count - commits_before, 16)

            launch_req_arg = mock_launch.call_args[0][0]
            self.assertTrue(launch_req_arg.no_cloudflare)
            self.assertTrue(launch_req_arg.t3)
            self.assertTrue(launch_req_arg.modal)
            self.assertTrue(launch_req_arg.sops)
            self.assertTrue(launch_req_arg.vm)
            self.assertEqual(launch_req_arg.memory, 1)
            self.assertIsNone(launch_req_arg.repo)

            cmds = [" ".join(cmd) for cmd, _ in fake_sb.calls]
            create_cmds = [c for c in cmds if c.startswith("create-app /root/habit-tracker -y")]
            self.assertEqual(len(create_cmds), 1)
            self.assertNotIn("--force", create_cmds[0])

            thread_start_call = next((cmd, stdin) for cmd, stdin in fake_sb.calls if cmd[:3] == ("t3", "thread", "start"))
            self.assertIn("gemini-4-hydrogen", thread_start_call[0])
            self.assertIn("thought_level=high", thread_start_call[0])
            self.assertTrue(thread_start_call[1].startswith("Habit tracker"))
            self.assertIn("pnpm run dev", thread_start_call[1])

    def test_execute_launch_blank_template_initializes_git_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fake_sb = _FakeSandbox("sb-200")
            mock_launch = MagicMock(
                return_value=(
                    fake_sb,
                    LaunchResponse(
                        sandbox_id="sb-200",
                        app_name="scratch",
                        sandbox_name="scratch-1234",
                        t3_url="https://ta-200-3775.w.modal.host",
                    ),
                )
            )
            mock_db = MagicMock()
            coord = LaunchCoordinator(store=store, launch_fn=mock_launch, create_db_fn=mock_db, env={})

            _, req = coord.create_and_dispatch(
                CreateAppPayload(prompt="Static HTML game", name="scratch", template="blank")
            )
            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.request.status, "ready")
            mock_db.assert_not_called()
            cmds = [" ".join(cmd) for cmd, _ in fake_sb.calls]
            self.assertFalse(any("create-app" in c for c in cmds))
            self.assertTrue(any("git init -b main" in c and "/root/scratch" in c for c in cmds))

    def test_idempotent_recovery_after_uncertain_thread_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fake_sb = _FakeSandbox("sb-retry", fail_first_thread_start=True)
            mock_launch = MagicMock(
                return_value=(
                    fake_sb,
                    LaunchResponse(
                        sandbox_id="sb-retry",
                        app_name="retry-app",
                        sandbox_name="retry-app-1234",
                        t3_url="https://ta-retry-3775.w.modal.host",
                    ),
                )
            )
            coord = LaunchCoordinator(store=store, launch_fn=mock_launch, env={})

            _, req = coord.create_and_dispatch(CreateAppPayload(prompt="Retry app", template="blank"))
            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.request.status, "ready")
            self.assertEqual(res.app.thread_id, "thread:recovered-1")

    def test_superseded_or_deleted_launch_aborts_without_clobbering_or_leaking_sandbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fake_sb = _FakeSandbox("sb-stale")
            mock_terminate = MagicMock(return_value={"id": "sb-stale", "status": "terminated"})

            def _launch_and_supersede(_req, *, log_cb=None):
                store.update_app(app.app_id, latest_request_id="req_newer")
                return fake_sb, LaunchResponse(
                    sandbox_id="sb-stale",
                    app_name="superseded",
                    sandbox_name="superseded-1234",
                    t3_url="https://ta-stale-3775.w.modal.host",
                )

            coord = LaunchCoordinator(
                store=store,
                launch_fn=MagicMock(side_effect=_launch_and_supersede),
                terminate_fn=mock_terminate,
                env={},
            )
            app, req = coord.create_and_dispatch(CreateAppPayload(prompt="Superseded app", template="blank"))
            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.request.status, "failed")
            self.assertEqual(store.get_app(app.app_id).latest_request_id, "req_newer")
            self.assertEqual(store.get_app(app.app_id).status, "provisioning")
            mock_terminate.assert_called_once_with("sb-stale", profile=None)

    def test_pre_boot_failure_terminates_partial_sandbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fake_sb = _FakeSandbox("sb-no-url")
            mock_launch = MagicMock(
                return_value=(
                    fake_sb,
                    LaunchResponse(
                        sandbox_id="sb-no-url",
                        app_name="broken-app",
                        sandbox_name="broken-app-1234",
                        t3_url=None,
                    ),
                )
            )
            mock_terminate = MagicMock(return_value={"id": "sb-no-url", "status": "terminated"})
            coord = LaunchCoordinator(store=store, launch_fn=mock_launch, terminate_fn=mock_terminate, env={})

            _, req = coord.create_and_dispatch(CreateAppPayload(prompt="No URL app"))
            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.request.status, "failed")
            self.assertIsNone(res.app.sandbox_id)
            self.assertEqual(res.app.failed_step, "launching_sandbox")
            mock_terminate.assert_called_once_with("sb-no-url", profile=None)

    def test_post_boot_failure_preserves_sandbox_and_retry_resumes_from_failed_step(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fake_sb = _FakeSandbox("sb-resume", running=True, fail_cmd="t3 thread start")
            mock_launch = MagicMock(
                return_value=(
                    fake_sb,
                    LaunchResponse(
                        sandbox_id="sb-resume",
                        app_name="resume-app",
                        sandbox_name="resume-app-1234",
                        t3_url="https://ta-resume-3775.w.modal.host",
                    ),
                )
            )
            mock_terminate = MagicMock(return_value={"id": "sb-resume", "status": "terminated"})
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                terminate_fn=mock_terminate,
                sandbox_from_id_fn=MagicMock(return_value=fake_sb),
                env={},
            )

            app, req = coord.create_and_dispatch(CreateAppPayload(prompt="Resume app"))
            failed = coord.execute_launch_request(req.request_id)
            self.assertEqual(failed.request.status, "failed")
            self.assertEqual(failed.request.failed_step, "starting_thread")
            self.assertEqual(failed.app.status, "failed")
            self.assertEqual(failed.app.sandbox_id, "sb-resume")
            self.assertTrue(failed.app.workspace_ready)
            self.assertEqual(failed.app.failed_step, "starting_thread")
            mock_terminate.assert_not_called()

            # Clear injected failure and click Retry (resume=True): should reuse sb-resume and skip launch/create-app
            fake_sb.fail_cmd = None
            calls_before_retry = len(fake_sb.calls)
            resumed_app, retry_req = coord.relaunch_factory_app(app.app_id, resume=True)
            self.assertEqual(retry_req.resume_from_step, "starting_thread")
            self.assertEqual(resumed_app.sandbox_id, "sb-resume")

            retried = coord.execute_launch_request(retry_req.request_id)
            self.assertEqual(retried.request.status, "ready")
            self.assertEqual(retried.app.status, "ready")
            self.assertIsNone(retried.app.failed_step)
            self.assertEqual(mock_launch.call_count, 1)
            retry_cmds = [" ".join(cmd) for cmd, _ in fake_sb.calls[calls_before_retry:]]
            self.assertFalse(any("create-app" in c for c in retry_cmds))
            self.assertFalse(any("server-runtime.json" in c for c in retry_cmds))
            self.assertTrue(any(c.startswith("t3 thread start") for c in retry_cmds))

    def test_retry_falls_back_to_fresh_launch_if_preserved_sandbox_stopped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            dead_sb = _FakeSandbox("sb-dead", running=False)
            fresh_sb = _FakeSandbox("sb-fresh", running=True)
            app = FactoryAppRecord(
                app_id="app_dead_retry",
                slug="dead-retry",
                title="Dead Retry",
                prompt="Retry",
                status="failed",
                failed_step="waiting_t3",
                workspace_ready=True,
                sandbox_id="sb-dead",
                t3_url="https://ta-dead-3775.w.modal.host",
            )
            store.save_app(app)
            mock_launch = MagicMock(
                return_value=(
                    fresh_sb,
                    LaunchResponse(
                        sandbox_id="sb-fresh",
                        app_name="dead-retry",
                        sandbox_name="dead-retry-9999",
                        t3_url="https://ta-fresh-3775.w.modal.host",
                    ),
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                sandbox_from_id_fn=MagicMock(return_value=dead_sb),
                env={},
            )
            _, retry_req = coord.relaunch_factory_app("app_dead_retry", resume=True)
            self.assertIsNone(retry_req.resume_from_step)
            res = coord.execute_launch_request(retry_req.request_id)
            self.assertEqual(res.request.status, "ready")
            self.assertEqual(res.app.sandbox_id, "sb-fresh")

    def test_wait_for_t3_ready_timeout_includes_probe_and_t3_log_diagnostics(self):
        sb = MagicMock()

        def _exec(*cmd, **_kwargs):
            proc = MagicMock()
            if cmd[0] == "python3":
                proc.wait.return_value = 1
                proc.stdout.read.return_value = ""
                proc.stderr.read.return_value = "missing: settings.json"
            else:
                proc.wait.return_value = 0
                proc.stdout.read.return_value = "T3 booting..."
                proc.stderr.read.return_value = ""
            return proc

        sb.exec.side_effect = _exec
        with self.assertRaises(TimeoutError) as ctx:
            wait_for_t3_ready(sb, timeout_secs=0)
        self.assertIn("missing: settings.json", str(ctx.exception))
        self.assertIn("T3 booting...", str(ctx.exception))

    def test_open_factory_app_mints_fresh_token_and_handles_stopped_with_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            app = FactoryAppRecord(
                app_id="app_1",
                slug="demo",
                title="Demo",
                prompt="Demo",
                status="ready",
                sandbox_id="sb-live-1",
                environment_id="env-01",
                thread_id="thread:1",
                t3_url="https://ta-1-3775.w.modal.host",
                chat_url="https://ta-1-3775.w.modal.host/env-01/thread%3A1",
            )
            store.save_app(app)

            live_sb = _FakeSandbox("sb-live-1", running=True)
            coord = LaunchCoordinator(
                store=store,
                sandbox_from_id_fn=MagicMock(return_value=live_sb),
                list_snapshots_fn=MagicMock(
                    return_value=[{"image_id": "im-snap-1", "sandbox_id": "sb-live-1", "name": "demo-snap"}]
                ),
            )

            opened = coord.open_factory_app("app_1")
            self.assertEqual(
                opened.handoff_url,
                "https://ta-1-3775.w.modal.host/env-01/thread%3A1#token=pair-tok-xyz",
            )

            live_sb.running = False
            with self.assertRaises(AppSandboxStoppedError) as ctx:
                coord.open_factory_app("app_1")
            self.assertEqual(ctx.exception.snapshot_image_id, "im-snap-1")

            with self.assertRaises(AppNotFoundError):
                coord.open_factory_app("missing-id")

    def test_delete_and_relaunch_factory_app(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            app = FactoryAppRecord(
                app_id="app_del",
                slug="del-app",
                title="Del App",
                prompt="Original prompt",
                status="ready",
                sandbox_id="sb-del-1",
            )
            store.save_app(app)

            live_sb = _FakeSandbox("sb-del-1", running=True)
            mock_terminate = MagicMock(return_value={"id": "sb-del-1", "status": "terminated"})
            coord = LaunchCoordinator(
                store=store,
                sandbox_from_id_fn=MagicMock(return_value=live_sb),
                terminate_fn=mock_terminate,
            )

            deleted = coord.delete_factory_app("app_del", terminate_active_sandbox=True)
            self.assertTrue(deleted)
            mock_terminate.assert_called_once_with("sb-del-1", profile=None)
            self.assertIsNone(store.get_app("app_del"))

            stopped_app = FactoryAppRecord(
                app_id="app_rel",
                slug="rel-app",
                title="Rel App",
                prompt="Original prompt",
                status="ready",
                sandbox_id="sb-stopped",
            )
            store.save_app(stopped_app)
            dispatched: list[str] = []
            relaunched_app, relaunch_req = coord.relaunch_factory_app("app_rel", dispatch_fn=dispatched.append)
            self.assertEqual(relaunch_req.kind, "relaunch")
            self.assertEqual(relaunched_app.status, "provisioning")
            self.assertIsNone(relaunched_app.sandbox_id)
            self.assertEqual(dispatched, [relaunch_req.request_id])
