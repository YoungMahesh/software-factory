"""Tests for Prime Sandbox reuse, compatibility keying, concurrency, port isolation, and cleanup."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.apps import (
    DEFAULT_APP_BASE_PORT,
    CreateAppPayload,
    FactoryAppRecord,
    FactoryStateStore,
    LaunchCoordinator,
    PrimeSandboxRecord,
    build_initial_thread_prompt,
    prime_compatibility_key,
    set_coordinator_factory,
    set_default_store,
    set_launch_dispatcher,
)
from sandbox.core import LaunchResponse
from sandbox.web import app as web_router_app


class _MultiAppFakeSandbox:
    """Fake Modal sandbox simulating multiple apps, T3 projects/threads, and port config."""

    def __init__(self, sandbox_id: str = "sb-prime-1", *, running: bool = True, t3_alive: bool = True):
        self.object_id = sandbox_id
        self.running = running
        self.t3_alive = t3_alive
        self.terminated = False
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self._lock = threading.Lock()
        self._thread_seq = 0

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

        with self._lock:
            if cmd[:3] == ("t3", "thread", "start"):
                self._thread_seq += 1
                seq = self._thread_seq
                app_dir = cmd[3]
                stdout_val = json.dumps(
                    {"threadId": f"thread:{seq}", "projectId": f"proj:{app_dir}", "runId": f"run:{seq}"}
                )
            elif "server-runtime.json" in cmd_str and "environment-id" in cmd_str:
                stdout_val = json.dumps(
                    {
                        "environment_id": "env-prime",
                        "settings": {"providerInstances": {"antigravity": {"driver": "antigravity", "enabled": True}}},
                        "caches": {
                            "antigravity": {
                                "auth": {"status": "authenticated"},
                                "models": [{"slug": "gemini-4-hydrogen", "isDefault": True}],
                            }
                        },
                    }
                )
            elif cmd[:3] == ("t3", "thread", "list"):
                stdout_val = json.dumps({"threads": []})
            elif cmd[:3] == ("t3", "auth", "pairing"):
                stdout_val = json.dumps({"credential": "prime-pair-tok"})
            else:
                stdout_val = ""

        def _wait():
            self.calls.append((cmd, "".join(stdin_chunks) or None))
            if "server-runtime.json" in cmd_str and not self.t3_alive:
                return 1
            return 0

        proc.wait.side_effect = _wait
        proc.stdout.read.return_value = stdout_val
        proc.stderr.read.return_value = "t3 offline" if ("server-runtime.json" in cmd_str and not self.t3_alive) else ""
        return proc


class TestPrimeSandbox(unittest.TestCase):
    def test_compatibility_key_and_prompt_port_wiring(self):
        k_def = prime_compatibility_key(None, False, False)
        k_vm = prime_compatibility_key(None, True, False)
        k_mob = prime_compatibility_key(None, False, True)
        k_prof_a = prime_compatibility_key("team.alpha", False, False)
        k_prof_b = prime_compatibility_key("team/alpha", False, False)
        self.assertEqual(len({k_def, k_vm, k_mob, k_prof_a, k_prof_b}), 5)

        prompt_next = build_initial_thread_prompt("Build CRM", template="nextjs", app_dir="/root/crm", dev_port=3002)
        self.assertIn("http://localhost:3002", prompt_next)
        self.assertIn("port 3002", prompt_next)

        prompt_blank = build_initial_thread_prompt("Static site", template="blank", app_dir="/root/site", dev_port=3003)
        self.assertIn("PORT=3003", prompt_blank)
        self.assertIn("http://localhost:3003", prompt_blank)

    def test_subsequent_prompts_reuse_prime_sandbox_with_distinct_ports_and_threads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _MultiAppFakeSandbox("sb-prime-1")
            sandboxes = {"sb-prime-1": sb}
            mock_launch = MagicMock(
                return_value=(
                    sb,
                    LaunchResponse(
                        sandbox_id="sb-prime-1",
                        app_name="prime-sandbox",
                        sandbox_name="prime-sandbox-aaa111",
                        t3_url="https://ta-prime-3775.w.modal.host",
                    ),
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                sandbox_from_id_fn=lambda sid, **_kw: sandboxes[sid],
                env={},
            )

            app1, req1 = coord.create_and_dispatch(CreateAppPayload(prompt="First app"))
            res1 = coord.execute_launch_request(req1.request_id)
            self.assertEqual(res1.app.sandbox_id, "sb-prime-1")
            self.assertEqual(res1.app.dev_port, DEFAULT_APP_BASE_PORT)
            self.assertEqual(res1.app.thread_id, "thread:1")

            app2, req2 = coord.create_and_dispatch(CreateAppPayload(prompt="Second app"))
            res2 = coord.execute_launch_request(req2.request_id)
            self.assertEqual(mock_launch.call_count, 1)
            self.assertEqual(res2.app.sandbox_id, "sb-prime-1")
            self.assertEqual(res2.app.dev_port, DEFAULT_APP_BASE_PORT + 1)
            self.assertEqual(res2.app.thread_id, "thread:2")
            self.assertIn("3002", next(s for c, s in sb.calls if c[:3] == ("t3", "thread", "start") and c[3] == "/root/second-app"))

            # Verify port configuration script ran for both apps
            port_scripts = [c for c, _ in sb.calls if c[:2] == ("python3", "-c") and len(c) >= 5 and c[3].startswith("/root/")]
            self.assertEqual([(c[3], c[4]) for c in port_scripts], [("/root/first-app", "3001"), ("/root/second-app", "3002")])

            primes = coord.list_primes_with_status()
            self.assertEqual(len(primes), 1)
            self.assertEqual(primes[0].runtime_status, "running")
            self.assertEqual(primes[0].app_count, 2)
            self.assertEqual(set(primes[0].app_ids), {app1.app_id, app2.app_id})

    def test_capability_mismatch_creates_separate_prime_sandbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb_std = _MultiAppFakeSandbox("sb-std")
            sb_vm = _MultiAppFakeSandbox("sb-vm")
            registry = {"sb-std": sb_std, "sb-vm": sb_vm}

            def _launch(req, *, log_cb=None):
                sid = "sb-vm" if req.vm else "sb-std"
                return registry[sid], LaunchResponse(
                    sandbox_id=sid,
                    app_name=req.name or "prime",
                    sandbox_name=f"{req.name}-1",
                    t3_url=f"https://{sid}-3775.w.modal.host",
                )

            coord = LaunchCoordinator(
                store=store,
                launch_fn=MagicMock(side_effect=_launch),
                sandbox_from_id_fn=lambda sid, **_kw: registry[sid],
                env={},
            )
            _, req_std = coord.create_and_dispatch(CreateAppPayload(prompt="Web app", vm=False))
            res_std = coord.execute_launch_request(req_std.request_id)

            _, req_vm = coord.create_and_dispatch(CreateAppPayload(prompt="Docker app", vm=True))
            res_vm = coord.execute_launch_request(req_vm.request_id)

            self.assertEqual(res_std.app.sandbox_id, "sb-std")
            self.assertEqual(res_std.app.dev_port, 3001)
            self.assertEqual(res_vm.app.sandbox_id, "sb-vm")
            self.assertEqual(res_vm.app.dev_port, 3001)
            self.assertEqual(len(coord.list_primes_with_status()), 2)

    def test_concurrent_cold_starts_coordinate_into_single_prime_sandbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _MultiAppFakeSandbox("sb-concurrent")
            launch_entered = threading.Event()
            allow_finish = threading.Event()

            def _slow_launch(req, *, log_cb=None):
                launch_entered.set()
                allow_finish.wait(timeout=5.0)
                return sb, LaunchResponse(
                    sandbox_id="sb-concurrent",
                    app_name="prime-sandbox",
                    sandbox_name="prime-concurrent",
                    t3_url="https://ta-conc-3775.w.modal.host",
                )

            mock_launch = MagicMock(side_effect=_slow_launch)
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                sandbox_from_id_fn=lambda sid, **_kw: sb,
                env={},
                prime_wait_timeout_secs=10.0,
                prime_poll_interval_secs=0.05,
            )

            _, req1 = coord.create_and_dispatch(CreateAppPayload(prompt="App One"))
            _, req2 = coord.create_and_dispatch(CreateAppPayload(prompt="App Two"))

            with ThreadPoolExecutor(max_workers=2) as pool:
                fut1 = pool.submit(coord.execute_launch_request, req1.request_id)
                self.assertTrue(launch_entered.wait(timeout=3.0))
                fut2 = pool.submit(coord.execute_launch_request, req2.request_id)
                threading.Timer(0.15, allow_finish.set).start()
                res1 = fut1.result(timeout=10.0)
                res2 = fut2.result(timeout=10.0)

            self.assertEqual(mock_launch.call_count, 1)
            self.assertEqual(res1.request.status, "ready")
            self.assertEqual(res2.request.status, "ready")
            self.assertEqual(res1.app.sandbox_id, "sb-concurrent")
            self.assertEqual(res2.app.sandbox_id, "sb-concurrent")
            self.assertEqual({res1.app.dev_port, res2.app.dev_port}, {3001, 3002})

    def test_concurrent_waiter_takes_over_when_first_boot_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb2 = _MultiAppFakeSandbox("sb-recovery")
            attempt = {"n": 0}
            first_started = threading.Event()
            release_first = threading.Event()

            def _flaky_launch(req, *, log_cb=None):
                attempt["n"] += 1
                if attempt["n"] == 1:
                    first_started.set()
                    release_first.wait(timeout=5.0)
                    raise RuntimeError("Modal container boot transient error")
                return sb2, LaunchResponse(
                    sandbox_id="sb-recovery",
                    app_name="prime-sandbox",
                    sandbox_name="prime-recovery",
                    t3_url="https://ta-rec-3775.w.modal.host",
                )

            coord = LaunchCoordinator(
                store=store,
                launch_fn=MagicMock(side_effect=_flaky_launch),
                sandbox_from_id_fn=lambda sid, **_kw: sb2,
                env={},
                prime_wait_timeout_secs=10.0,
                prime_poll_interval_secs=0.05,
            )

            _, req1 = coord.create_and_dispatch(CreateAppPayload(prompt="Flaky One"))
            _, req2 = coord.create_and_dispatch(CreateAppPayload(prompt="Takeover Two"))

            with ThreadPoolExecutor(max_workers=2) as pool:
                fut1 = pool.submit(coord.execute_launch_request, req1.request_id)
                self.assertTrue(first_started.wait(timeout=3.0))
                fut2 = pool.submit(coord.execute_launch_request, req2.request_id)
                threading.Timer(0.1, release_first.set).start()
                res1 = fut1.result(timeout=10.0)
                res2 = fut2.result(timeout=10.0)

            self.assertEqual(res1.request.status, "failed")
            self.assertEqual(res2.request.status, "ready")
            self.assertEqual(res2.app.sandbox_id, "sb-recovery")

    def test_stopped_or_unhealthy_prime_sandbox_triggers_fresh_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            dead_sb = _MultiAppFakeSandbox("sb-old", running=True, t3_alive=False)
            fresh_sb = _MultiAppFakeSandbox("sb-new", running=True, t3_alive=True)
            registry = {"sb-old": dead_sb, "sb-new": fresh_sb}

            prime_key = prime_compatibility_key(None, False, False)
            store.save_prime(
                PrimeSandboxRecord(
                    prime_key=prime_key,
                    status="ready",
                    sandbox_id="sb-old",
                    sandbox_name="prime-old",
                    t3_url="https://ta-old-3775.w.modal.host",
                    environment_id="env-old",
                    next_port=3005,
                )
            )
            mock_launch = MagicMock(
                return_value=(
                    fresh_sb,
                    LaunchResponse(
                        sandbox_id="sb-new",
                        app_name="prime-sandbox",
                        sandbox_name="prime-new",
                        t3_url="https://ta-new-3775.w.modal.host",
                    ),
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                sandbox_from_id_fn=lambda sid, **_kw: registry[sid],
                env={},
            )

            _, req = coord.create_and_dispatch(CreateAppPayload(prompt="Fresh after dead T3"))
            res = coord.execute_launch_request(req.request_id)
            self.assertEqual(res.app.sandbox_id, "sb-new")
            self.assertEqual(res.app.dev_port, 3001)
            self.assertEqual(mock_launch.call_count, 1)

    def test_delete_and_relaunch_keep_prime_sandbox_alive_and_clean_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _MultiAppFakeSandbox("sb-shared")
            registry = {"sb-shared": sb}
            mock_terminate = MagicMock()
            mock_launch = MagicMock(
                return_value=(
                    sb,
                    LaunchResponse(
                        sandbox_id="sb-shared",
                        app_name="prime-sandbox",
                        sandbox_name="prime-shared",
                        t3_url="https://ta-shared-3775.w.modal.host",
                    ),
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                terminate_fn=mock_terminate,
                sandbox_from_id_fn=lambda sid, **_kw: registry[sid],
                env={},
            )

            app1, req1 = coord.create_and_dispatch(CreateAppPayload(prompt="Keep me"))
            app2, req2 = coord.create_and_dispatch(CreateAppPayload(prompt="Delete me"))
            coord.execute_launch_request(req1.request_id)
            coord.execute_launch_request(req2.request_id)

            # Deleting app2 even with terminate_active_sandbox=True must NOT kill the Prime Sandbox
            self.assertTrue(coord.delete_factory_app(app2.app_id, terminate_active_sandbox=True))
            mock_terminate.assert_not_called()
            self.assertFalse(sb.terminated)
            cmds = [" ".join(c) for c, _ in sb.calls]
            self.assertTrue(any("t3 project remove --force /root/delete-me" in c for c in cmds))
            self.assertTrue(any(c == "rm -rf /root/delete-me" for c in cmds))

            # Relaunching app1 cleans up its workspace and reuses sb-shared with a fresh port
            _, rel_req = coord.relaunch_factory_app(app1.app_id, resume=False)
            rel_res = coord.execute_launch_request(rel_req.request_id)
            mock_terminate.assert_not_called()
            self.assertEqual(rel_res.app.sandbox_id, "sb-shared")
            self.assertEqual(rel_res.app.dev_port, 3003)

    def test_primes_route_and_terminate_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _MultiAppFakeSandbox("sb-route")
            prime_key = prime_compatibility_key(None, False, False)
            store.save_prime(
                PrimeSandboxRecord(
                    prime_key=prime_key,
                    status="ready",
                    sandbox_id="sb-route",
                    sandbox_name="prime-route",
                    t3_url="https://ta-route-3775.w.modal.host",
                    environment_id="env-1",
                )
            )
            store.save_app(
                FactoryAppRecord(
                    app_id="app_r1",
                    slug="r1",
                    title="R1",
                    prompt="R1",
                    status="ready",
                    sandbox_id="sb-route",
                    prime_key=prime_key,
                    dev_port=3001,
                )
            )
            coord = LaunchCoordinator(store=store, sandbox_from_id_fn=MagicMock(return_value=sb), env={})
            set_default_store(store)
            set_coordinator_factory(lambda: coord)
            set_launch_dispatcher(lambda _req: None)
            try:
                with patch.dict(os.environ, {"WEB_UI_USERNAME": "u", "WEB_UI_PASSWORD": "p"}):
                    auth = base64.b64encode(b"u:p").decode("utf-8")
                    client = TestClient(web_router_app, headers={"Authorization": f"Basic {auth}"})
                    primes_res = client.get("/api/primes")
                    self.assertEqual(primes_res.status_code, 200)
                    body = primes_res.json()
                    self.assertEqual(len(body), 1)
                    self.assertEqual(body[0]["runtime_status"], "running")
                    self.assertEqual(body[0]["app_count"], 1)

                    html = client.get("/").text
                    self.assertIn("/api/primes", html)
                    self.assertIn("Snapshot Sandbox", html)
                    self.assertNotIn("New Prime Sandbox", html)

                    with patch("sandbox.web.terminate_sandbox", return_value={"id": "sb-route", "status": "terminated"}):
                        term = client.post("/api/sandboxes/sb-route/terminate")
                        self.assertEqual(term.status_code, 200)
                    self.assertEqual(store.get_prime(prime_key).status, "stopped")
            finally:
                set_coordinator_factory(None)
                set_launch_dispatcher(None)
                set_default_store(None)
