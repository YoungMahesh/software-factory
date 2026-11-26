"""Tests for cached GitHub repo picker, Prime Sandbox repo launch, idle threads, and web_app toggle."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.apps import (
    CachedGitHubRepo,
    CreateAppPayload,
    FactoryStateStore,
    LaunchCoordinator,
    RepositoryCatalogCache,
    build_initial_thread_prompt,
    derive_app_slug,
    derive_app_title,
    fetch_github_org_repos,
    normalize_repo_spec,
    set_coordinator_factory,
    set_launch_dispatcher,
)
from sandbox.apps._prompts import GENERIC_REPO_OPEN_PROMPT
from sandbox.core import LaunchResponse
from sandbox.env_store import VaultBundle
from sandbox.web import app as web_router_app


class _RepoFakeSandbox:
    """Fake Modal sandbox supporting git clone, vault unpack, dep install, T3 WS idle thread, and start."""

    def __init__(self, sandbox_id: str = "sb-repo-1", *, fail_idle_ws: bool = False):
        self.object_id = sandbox_id
        self.running = True
        self.fail_idle_ws = fail_idle_ws
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self._thread_seq = 0

    def poll(self):
        return None if self.running else 137

    def exec(self, *cmd: str, **_kwargs):
        cmd_str = " ".join(cmd)
        proc = MagicMock()
        stdin_chunks: list[str] = []
        proc.stdin = MagicMock()
        proc.stdin.write.side_effect = lambda data: stdin_chunks.append(
            data.decode("utf-8") if isinstance(data, bytes) else str(data)
        )

        stdout_val = ""
        stderr_val = ""
        rc = 0

        if "server-runtime.json" in cmd_str and "environment-id" in cmd_str:
            stdout_val = json.dumps(
                {
                    "environment_id": "env-repo",
                    "settings": {"providerInstances": {"antigravity": {"driver": "antigravity", "enabled": True}}},
                    "caches": {
                        "antigravity": {
                            "auth": {"status": "authenticated"},
                            "models": [{"slug": "gemini-4-hydrogen", "isDefault": True}],
                        }
                    },
                }
            )
        elif cmd[:3] == ("t3", "project", "add"):
            app_dir = cmd[-1]
            stdout_val = f"Added project proj:{app_dir} (Repo) at {app_dir}.\n"
        elif cmd[:3] == ("t3", "thread", "list"):
            stdout_val = json.dumps({"threads": []})
        elif cmd[:2] == ("node", "-e"):
            if self.fail_idle_ws:
                rc = 1
                stderr_val = "ws rpc unavailable"
            else:
                self._thread_seq += 1
                stdout_val = json.dumps({"threadId": f"idle-thread-{self._thread_seq}", "projectId": "proj:ws"})
        elif cmd[:3] == ("t3", "thread", "start"):
            self._thread_seq += 1
            stdout_val = json.dumps({"threadId": f"thread:{self._thread_seq}", "projectId": "proj:cli"})
        elif cmd[:3] == ("t3", "auth", "pairing"):
            stdout_val = json.dumps({"credential": "tok-repo-pair"})

        def _wait():
            self.calls.append((cmd, "".join(stdin_chunks) or None))
            return rc

        proc.wait.side_effect = _wait
        proc.stdout.read.return_value = stdout_val
        proc.stderr.read.return_value = stderr_val
        return proc


class _FakeHttpResponse:
    def __init__(self, body: object, *, status: int = 200, headers: dict[str, str] | None = None):
        self._raw = json.dumps(body).encode("utf-8")
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestGitHubRepoPickerAndWebAppToggle(unittest.TestCase):
    def test_normalize_repo_spec_and_slug_derivation(self):
        self.assertEqual(normalize_repo_spec("acme-api", default_org="my-org"), ("my-org/acme-api", "my-org", "acme-api"))
        self.assertEqual(
            normalize_repo_spec("https://github.com/other/cool.git"),
            ("other/cool", "other", "cool"),
        )
        with self.assertRaises(ValueError):
            normalize_repo_spec("acme-api", default_org=None)
        with self.assertRaises(ValueError):
            normalize_repo_spec("a/b/c")

        self.assertEqual(derive_app_slug("", repo="my-org/acme-api", existing_slugs={"acme-api"}), "acme-api-2")
        self.assertEqual(derive_app_title("", repo="my-org/acme-api"), "acme-api")

    def test_payload_web_app_defaults_and_prompt_builder(self):
        scratch_next = CreateAppPayload(prompt="Build CRM")
        self.assertTrue(scratch_next.resolved_web_app())

        scratch_blank = CreateAppPayload(prompt="CLI tool", template="blank")
        self.assertFalse(scratch_blank.resolved_web_app())

        repo_empty = CreateAppPayload(repo="my-org/acme-api")
        self.assertEqual(repo_empty.prompt, "")
        self.assertFalse(repo_empty.resolved_web_app())

        raw = "Refactor auth middleware"
        self.assertEqual(
            build_initial_thread_prompt(raw, template="nextjs", app_dir="/root/app", dev_port=3001, web_app=False),
            raw,
        )
        repo_web = build_initial_thread_prompt(
            raw, template="nextjs", app_dir="/root/acme", dev_port=3002, web_app=True, repo="my-org/acme"
        )
        self.assertIn("PORT=3002", repo_web)
        self.assertIn("http://localhost:3002", repo_web)

        empty_repo_web = build_initial_thread_prompt(
            "", template="nextjs", app_dir="/root/acme", dev_port=3003, web_app=True, repo="my-org/acme"
        )
        self.assertIn("run-app", empty_repo_web)
        self.assertIn("3003", empty_repo_web)

    def test_fetch_github_org_repos_paginates_filters_archived_and_infra_repos(self):
        def _fake_urlopen(req, timeout=20.0):
            url = req.full_url
            if url.endswith("/users/my-org"):
                return _FakeHttpResponse({"login": "my-org", "type": "Organization"})
            if "orgs/my-org/repos" in url and "page=2" not in url:
                return _FakeHttpResponse(
                    [
                        {"name": "config", "full_name": "my-org/config", "owner": {"login": "my-org"}, "archived": False, "updated_at": "2026-11-26T10:00:00Z"},
                        {"name": "env-store", "full_name": "my-org/env-store", "owner": {"login": "my-org"}, "archived": False, "updated_at": "2026-11-26T10:00:00Z"},
                        {"name": "caddy-store", "full_name": "my-org/caddy-store", "owner": {"login": "my-org"}, "archived": False, "updated_at": "2026-11-26T10:00:00Z"},
                        {"name": "old-repo", "full_name": "my-org/old-repo", "owner": {"login": "my-org"}, "archived": True, "updated_at": "2026-11-26T10:00:00Z"},
                        {"name": "alpha", "full_name": "my-org/alpha", "owner": {"login": "my-org"}, "private": True, "default_branch": "main", "updated_at": "2026-11-25T10:00:00Z"},
                    ],
                    headers={"Link": '<https://api.github.com/orgs/my-org/repos?page=2>; rel="next"'},
                )
            if "page=2" in url:
                return _FakeHttpResponse(
                    [
                        {"name": "beta", "full_name": "my-org/beta", "owner": {"login": "my-org"}, "private": False, "default_branch": "develop", "updated_at": "2026-11-26T12:00:00Z"},
                    ]
                )
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("sandbox.apps._github_repos.urllib.request.urlopen", side_effect=_fake_urlopen):
            repos = fetch_github_org_repos("my-org", "ghp_secret")
        self.assertEqual([r.full_name for r in repos], ["my-org/beta", "my-org/alpha"])
        self.assertEqual(repos[0].default_branch, "develop")
        self.assertTrue(repos[1].private)

    def test_store_persists_repo_catalog_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_vol = MagicMock()
            store = FactoryStateStore(root_dir=Path(tmpdir), volume=mock_vol)
            empty = store.get_repo_catalog()
            self.assertEqual(empty.repos, [])
            self.assertIsNone(empty.refreshed_at)

            catalog = RepositoryCatalogCache(
                org="my-org",
                refreshed_at="2026-11-26T12:00:00+00:00",
                repos=[CachedGitHubRepo(full_name="my-org/api", name="api", owner="my-org")],
            )
            store.save_repo_catalog(catalog)
            loaded = store.get_repo_catalog()
            self.assertEqual(loaded.org, "my-org")
            self.assertEqual(len(loaded.repos), 1)
            self.assertEqual(loaded.repos[0].full_name, "my-org/api")
            self.assertGreaterEqual(mock_vol.commit.call_count, 1)

    def test_open_repo_without_prompt_clones_injects_vault_and_creates_idle_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _RepoFakeSandbox("sb-prime-repo")
            mock_launch = MagicMock(
                return_value=(
                    sb,
                    LaunchResponse(
                        sandbox_id="sb-prime-repo",
                        app_name="prime-sandbox",
                        sandbox_name="prime-repo-1",
                        t3_url="https://ta-repo-3775.w.modal.host",
                    ),
                )
            )
            mock_db = MagicMock()
            mock_bundle = MagicMock(
                return_value=VaultBundle(
                    dotenv_b64=base64.b64encode(b"SECRET_KEY=xyz\n").decode("ascii"),
                    git_author_name="Repo Bot",
                    git_author_email="bot@example.com",
                )
            )
            coord = LaunchCoordinator(
                store=store,
                launch_fn=mock_launch,
                create_db_fn=mock_db,
                sandbox_from_id_fn=lambda _sid, **_kw: sb,
                resolve_bundle_fn=mock_bundle,
                env={"GH_ORG_NAME": "my-org", "GH_TOKEN": "ghp_tok123"},
            )

            app1, req1 = coord.create_and_dispatch(CreateAppPayload(repo="acme-api", branch="develop"))
            res1 = coord.execute_launch_request(req1.request_id)
            self.assertEqual(res1.request.status, "ready")
            self.assertEqual(res1.app.repo, "my-org/acme-api")
            self.assertEqual(res1.app.branch, "develop")
            self.assertIsNone(res1.app.dev_port)
            self.assertEqual(res1.app.thread_id, "idle-thread-1")
            mock_db.assert_not_called()

            # Verify token never leaked into command args, only stdin
            for cmd, _ in sb.calls:
                self.assertNotIn("ghp_tok123", " ".join(cmd))
            self.assertFalse(any(c[:3] == ("t3", "thread", "start") for c, _ in sb.calls))
            self.assertTrue(any(c[:2] == ("node", "-e") for c, _ in sb.calls))
            self.assertTrue(any("pnpm-lock.yaml" in " ".join(c) for c, _ in sb.calls))
            vault_calls = [stdin for c, stdin in sb.calls if stdin and "SECRET_KEY=xyz" in base64.b64decode(json.loads(stdin).get("dotenv_b64", "") or "e30=").decode("utf-8", "ignore") if c[:2] == ("python3", "-c") and "encoded_bundle" in stdin]
            self.assertEqual(len(vault_calls), 1)

            # Re-opening same repo isolates into /root/acme-api-2 on same Prime Sandbox
            app2, req2 = coord.create_and_dispatch(
                CreateAppPayload(repo="my-org/acme-api", prompt="Run dev server", web_app=True)
            )
            res2 = coord.execute_launch_request(req2.request_id)
            self.assertEqual(mock_launch.call_count, 1)
            self.assertEqual(app2.slug, "acme-api-2")
            self.assertEqual(res2.app.dev_port, 3001)
            self.assertFalse(any("chore: bind web dev port" in " ".join(c) for c, _ in sb.calls))
            t_start = next((c, s) for c, s in sb.calls if c[:3] == ("t3", "thread", "start"))
            self.assertEqual(t_start[0][3], "/root/acme-api-2")
            self.assertIn("PORT=3001", t_start[1])

    def test_idle_thread_fallback_and_webapp_false_skips_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            sb = _RepoFakeSandbox("sb-fallback", fail_idle_ws=True)
            coord = LaunchCoordinator(
                store=store,
                launch_fn=MagicMock(
                    return_value=(
                        sb,
                        LaunchResponse(
                            sandbox_id="sb-fallback",
                            app_name="prime-sandbox",
                            sandbox_name="prime-fb",
                            t3_url="https://ta-fb-3775.w.modal.host",
                        ),
                    )
                ),
                resolve_bundle_fn=MagicMock(return_value=None),
                env={"GH_ORG_NAME": "my-org", "GH_TOKEN": "ghp_tok"},
            )

            _, req_repo = coord.create_and_dispatch(CreateAppPayload(repo="my-org/cli-tool"))
            res_repo = coord.execute_launch_request(req_repo.request_id)
            self.assertEqual(res_repo.request.status, "ready")
            t_fb = next((c, s) for c, s in sb.calls if c[:3] == ("t3", "thread", "start"))
            self.assertEqual(t_fb[1], GENERIC_REPO_OPEN_PROMPT)

            _, req_noweb = coord.create_and_dispatch(
                CreateAppPayload(prompt="Build Python CLI", template="nextjs", web_app=False)
            )
            res_noweb = coord.execute_launch_request(req_noweb.request_id)
            self.assertIsNone(res_noweb.app.dev_port)
            t_noweb = [s for c, s in sb.calls if c[:3] == ("t3", "thread", "start")][-1]
            self.assertEqual(t_noweb, "Build Python CLI")

    def test_github_repo_routes_and_dashboard_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            fetch_mock = MagicMock(
                return_value=[
                    CachedGitHubRepo(full_name="my-org/web-app", name="web-app", owner="my-org", default_branch="main")
                ]
            )
            coord = LaunchCoordinator(
                store=store,
                fetch_github_repos_fn=fetch_mock,
                env={"GH_ORG_NAME": "my-org", "GH_TOKEN": "ghp_test"},
            )
            set_coordinator_factory(lambda: coord)
            set_launch_dispatcher(lambda _req_id: None)
            try:
                with patch.dict(os.environ, {"WEB_UI_USERNAME": "u", "WEB_UI_PASSWORD": "p"}):
                    auth = base64.b64encode(b"u:p").decode("utf-8")
                    client = TestClient(web_router_app, headers={"Authorization": f"Basic {auth}"})

                    # GET never calls GitHub
                    cached = client.get("/api/github/repos")
                    self.assertEqual(cached.status_code, 200)
                    self.assertEqual(cached.json()["repos"], [])
                    fetch_mock.assert_not_called()

                    # POST refresh calls GitHub and persists cache
                    refreshed = client.post("/api/github/repos/refresh")
                    self.assertEqual(refreshed.status_code, 200)
                    self.assertEqual(len(refreshed.json()["repos"]), 1)
                    fetch_mock.assert_called_once_with("my-org", "ghp_test")

                    # Subsequent GET reads persisted cache without calling GitHub again
                    cached_after = client.get("/api/github/repos")
                    self.assertEqual(len(cached_after.json()["repos"]), 1)
                    fetch_mock.assert_called_once()

                    # Launch empty-prompt repo via HTTP route
                    created = client.post("/api/apps", json={"repo": "my-org/web-app", "branch": "main", "web_app": False})
                    self.assertEqual(created.status_code, 202)
                    self.assertEqual(created.json()["app"]["repo"], "my-org/web-app")
                    self.assertFalse(created.json()["app"]["web_app"])

                    html = client.get("/").text
                    self.assertIn("github-repos-panel", html)
                    self.assertIn("refresh-github-repos-btn", html)
                    self.assertIn("builder-webapp-checkbox", html)
                    self.assertIn("/api/github/repos/refresh", html)
            finally:
                set_coordinator_factory(None)
                set_launch_dispatcher(None)
