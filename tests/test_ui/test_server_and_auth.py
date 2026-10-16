"""Subsystem tests for Factory Testing Console and Studio UI."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from fastapi.testclient import TestClient

from factory.run import main, parse_args
from factory.ui.app import create_app
from factory.ui.github import (
    DEFAULT_TEST_ORG,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_milestones_and_issues,
    check_tanstack_start_compatibility,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    get_test_org_token,
    instantiate_repo_from_template,
    map_github_issue_status,
    parse_github_blocked_by,
    RepoCreationError,
    validate_github_repo_name,
    create_repo_milestone,
    create_repo_issue,
    resolve_or_create_milestone,
    synthesize_ticket_content,
    synthesize_and_create_issue,
    _normalize_github_issue,
    fetch_repo_pull_requests,
    merge_repo_pull_request,
    PullRequestMergeError,
    fetch_repo_branches,
    reopen_repo_issue_for_rollback,
    update_local_markdown_issue_for_rollback,
)
from factory.ui.db import StudioDatabase
from factory.ui.registry import (
    JobRegistry,
    JobStage,
    JobStatus,
    PreviewRegistry,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)


class TestCompiledSpaRootRouteServing(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_root_requires_authentication(self):
        unauth_client = TestClient(self.app)
        resp = unauth_client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)

    def test_root_serves_spa_shell_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp.text)
        self.assertIn("Software Factory", resp.text)

    def test_client_routing_fallback_on_root(self):
        resp = self.client.get("/console")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp.text)

        resp2 = self.client.get("/studio/repo/my-app")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("text/html", resp2.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp2.text)

        resp3 = self.client.get("/arbitrary/nested/deep-link")
        self.assertEqual(resp3.status_code, 200)
        self.assertIn("text/html", resp3.headers["content-type"])
        self.assertIn('<div id="root"></div>', resp3.text)

        resp_api_404 = self.client.get("/api/unknown_endpoint")
        self.assertEqual(resp_api_404.status_code, 404)

    def test_v2_redirects_to_root(self):
        # Without follow_redirects, verify HTTP 307/308 redirect and query preservation
        resp = self.client.get("/v2", follow_redirects=False)
        self.assertIn(resp.status_code, (307, 308))
        self.assertEqual(resp.headers["location"], "/")

        resp_query = self.client.get("/v2?feature=test", follow_redirects=False)
        self.assertIn(resp_query.status_code, (307, 308))
        self.assertEqual(resp_query.headers["location"], "/?feature=test")

        resp_sub = self.client.get("/v2/console?tab=1", follow_redirects=False)
        self.assertIn(resp_sub.status_code, (307, 308))
        self.assertEqual(resp_sub.headers["location"], "/console?tab=1")

        # With follow_redirects, verify redirect resolves to compiled SPA
        resp_followed = self.client.get("/v2", follow_redirects=True)
        self.assertEqual(resp_followed.status_code, 200)
        self.assertIn('<div id="root"></div>', resp_followed.text)

    def test_compiled_bundle_delivery(self):
        from factory.ui.app import STATIC_DIST_DIR

        assets_dir = STATIC_DIST_DIR / "assets"
        js_files = list(assets_dir.glob("*.js"))
        css_files = list(assets_dir.glob("*.css"))

        if js_files:
            js_name = js_files[0].name
            resp_js = self.client.get(f"/assets/{js_name}")
            self.assertEqual(resp_js.status_code, 200)
            self.assertIn("javascript", resp_js.headers["content-type"])

        if css_files:
            css_name = css_files[0].name
            resp_css = self.client.get(f"/assets/{css_name}")
            self.assertEqual(resp_css.status_code, 200)
            self.assertIn("text/css", resp_css.headers["content-type"])

    def test_fallback_when_dist_index_missing(self):
        with patch("pathlib.Path.is_file", return_value=False):
            resp = self.client.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("Compiled SPA bundle not found", resp.text)

    def test_static_assets_serving(self):
        from factory.ui.app import STATIC_DIST_DIR

        # Create a mock asset in STATIC_DIST_DIR/assets
        assets_dir = STATIC_DIST_DIR / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        test_asset = assets_dir / "test-bundle.js"
        test_asset.write_text("console.log('spa bundle');", encoding="utf-8")
        try:
            resp = self.client.get("/assets/test-bundle.js")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("javascript", resp.headers["content-type"])
            self.assertEqual(resp.text, "console.log('spa bundle');")

            # Legacy /v2/assets path redirects to /assets
            resp_v2 = self.client.get("/v2/assets/test-bundle.js", follow_redirects=False)
            self.assertIn(resp_v2.status_code, (307, 308))
            self.assertEqual(resp_v2.headers["location"], "/assets/test-bundle.js")

            resp_v2_followed = self.client.get("/v2/assets/test-bundle.js", follow_redirects=True)
            self.assertEqual(resp_v2_followed.status_code, 200)
            self.assertEqual(resp_v2_followed.text, "console.log('spa bundle');")

            # Also verify via /static/dist/assets/test-bundle.js
            resp_dist = self.client.get("/static/dist/assets/test-bundle.js")
            self.assertEqual(resp_dist.status_code, 200)
            self.assertIn("javascript", resp_dist.headers["content-type"])
        finally:
            if test_asset.exists():
                test_asset.unlink()


class TestCliDispatcherUiFlag(unittest.TestCase):
    def test_parse_args_ui_flags(self):
        with patch.dict("os.environ", {}, clear=True):
            args1 = parse_args(["--ui"])
            self.assertTrue(args1.ui)
            self.assertEqual(args1.port, 3010)
            self.assertEqual(args1.host, "127.0.0.1")

        args2 = parse_args(["--console", "--port", "9090", "--host", "0.0.0.0"])
        self.assertTrue(args2.ui)
        self.assertEqual(args2.port, 9090)
        self.assertEqual(args2.host, "0.0.0.0")

    def test_parse_args_ui_port_env_var(self):
        with patch.dict("os.environ", {"PORT": "4567"}):
            args = parse_args(["--ui"])
            self.assertEqual(args.port, 4567)

    def test_parse_args_ui_port_cli_precedence(self):
        with patch.dict("os.environ", {"PORT": "4567"}):
            args = parse_args(["--ui", "--port", "8989"])
            self.assertEqual(args.port, 8989)

    @patch("factory.ui.server.start_server")
    def test_main_with_ui_flag(self, mock_start_server):
        code = main(["--ui", "--port", "8888"])
        self.assertEqual(code, 0)
        mock_start_server.assert_called_once_with(host="127.0.0.1", port=8888, open_browser=True)


class TestServerRunner(unittest.TestCase):
    def test_get_default_port_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 3010)

    def test_get_default_port_env(self):
        with patch.dict("os.environ", {"PORT": "4000"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 4000)

    def test_get_default_port_invalid_env(self):
        with patch.dict("os.environ", {"PORT": "invalid"}):
            from factory.ui.server import get_default_port
            self.assertEqual(get_default_port(), 3010)

    @patch("factory.ui.server.start_server")
    def test_server_main_defaults(self, mock_start_server):
        from factory.ui.server import main as server_main
        with patch.dict("os.environ", {}, clear=True):
            server_main([])
            mock_start_server.assert_called_once_with(host="127.0.0.1", port=3010, open_browser=False)

    @patch("factory.ui.server.start_server")
    def test_server_main_custom_args(self, mock_start_server):
        from factory.ui.server import main as server_main
        server_main(["--host", "0.0.0.0", "-p", "5000", "--open"])
        mock_start_server.assert_called_once_with(host="0.0.0.0", port=5000, open_browser=True)

    @patch("uvicorn.run")
    def test_start_server_warning_fallback(self, mock_uvicorn_run):
        from factory.ui.server import start_server
        import io
        from contextlib import redirect_stdout

        with patch.dict("os.environ", {}, clear=True):
            f = io.StringIO()
            with redirect_stdout(f):
                start_server(host="127.0.0.1", port=3010)
            output = f.getvalue()
            self.assertIn("Factory Studio", output)
            self.assertIn("3010", output)
            self.assertIn("Compiled Vite React SPA", output)
            self.assertIn("SECURITY WARNING: Using local dev fallback", output)
            mock_uvicorn_run.assert_called_once()

    @patch("uvicorn.run")
    def test_start_server_configured_auth(self, mock_uvicorn_run):
        from factory.ui.server import start_server
        import io
        from contextlib import redirect_stdout

        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "produser", "FACTORY_AUTH_PASS": "secret"}, clear=True):
            f = io.StringIO()
            with redirect_stdout(f):
                start_server(host="127.0.0.1", port=3010)
            output = f.getvalue()
            self.assertIn("Compiled Vite React SPA", output)
            self.assertIn("HTTP Basic Auth enabled (user: 'produser')", output)
            mock_uvicorn_run.assert_called_once()


class TestAuthCredentials(unittest.TestCase):
    def test_get_auth_credentials_from_env(self):
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "myuser", "FACTORY_AUTH_PASS": "mypass123"}, clear=True):
            from factory.ui.auth import get_auth_credentials
            user, password, is_fallback = get_auth_credentials()
            self.assertEqual(user, "myuser")
            self.assertEqual(password, "mypass123")
            self.assertFalse(is_fallback)

    def test_get_auth_credentials_fallback_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            from factory.ui.auth import get_auth_credentials
            with self.assertLogs("factory.ui.auth", level="WARNING") as log_cm:
                user, password, is_fallback = get_auth_credentials()
                self.assertEqual(user, "admin")
                self.assertEqual(password, "admin")
                self.assertTrue(is_fallback)
                self.assertTrue(any("FACTORY_AUTH_USER" in msg for msg in log_cm.output))

    def test_get_auth_credentials_fallback_when_partial(self):
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "myuser"}, clear=True):
            from factory.ui.auth import get_auth_credentials
            with self.assertLogs("factory.ui.auth", level="WARNING") as log_cm:
                user, password, is_fallback = get_auth_credentials()
                self.assertEqual(user, "admin")
                self.assertEqual(password, "admin")
                self.assertTrue(is_fallback)
                self.assertTrue(any("FACTORY_AUTH_PASS" in msg for msg in log_cm.output))


class TestBasicAuthSecurity(unittest.TestCase):
    def test_unauthenticated_request_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)
        self.assertIn('Basic realm="Factory Studio"', resp.headers["www-authenticate"])

        resp_api = client.get("/api/repos")
        self.assertEqual(resp_api.status_code, 401)
        self.assertIn("www-authenticate", resp_api.headers)

    def test_invalid_credentials_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/", auth=("wronguser", "wrongpass"))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("www-authenticate", resp.headers)

    def test_malformed_auth_header_returns_401(self):
        registry = JobRegistry()
        app = create_app(registry=registry)
        client = TestClient(app)

        resp = client.get("/", headers={"Authorization": "Bearer not-a-basic-token"})
        self.assertEqual(resp.status_code, 401)

        resp_bad_b64 = client.get("/", headers={"Authorization": "Basic !!!not-valid-b64!!!"})
        self.assertEqual(resp_bad_b64.status_code, 401)

        resp_no_colon = client.get("/", headers={"Authorization": "Basic YWRtaW4="})  # 'admin' without ':'
        self.assertEqual(resp_no_colon.status_code, 401)

    def test_authenticated_request_with_env_credentials(self):
        with patch.dict(
            "os.environ",
            {"FACTORY_AUTH_USER": "custom_user", "FACTORY_AUTH_PASS": "custom_pass"},
            clear=True,
        ):
            registry = JobRegistry()
            app = create_app(registry=registry)
            client = TestClient(app)

            # Incorrect credentials fail
            resp_fail = client.get("/api/repos", auth=("admin", "admin"))
            self.assertEqual(resp_fail.status_code, 401)

            # Correct credentials succeed
            resp_ok = client.get("/api/repos", auth=("custom_user", "custom_pass"))
            self.assertEqual(resp_ok.status_code, 200)

    def test_authenticated_request_with_dev_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            registry = JobRegistry()
            app = create_app(registry=registry)
            client = TestClient(app)

            resp = client.get("/api/repos", auth=("admin", "admin"))
            self.assertEqual(resp.status_code, 200)

    def test_sse_stream_unauthenticated_returns_401(self):
        registry = JobRegistry()
        job = registry.create_job(repo="test3", feature="test-feature")
        job.status = JobStatus.SUCCESS
        app = create_app(registry=registry)
        client = TestClient(app)

        with client.stream("GET", f"/api/jobs/{job.id}/stream") as resp:
            self.assertEqual(resp.status_code, 401)
            self.assertIn("www-authenticate", resp.headers)

    def test_sse_stream_authenticated_succeeds(self):
        with patch.dict(
            "os.environ",
            {"FACTORY_AUTH_USER": "stream_user", "FACTORY_AUTH_PASS": "stream_pass"},
            clear=True,
        ):
            registry = JobRegistry()
            job = registry.create_job(repo="test3", feature="test-feature")
            job.status = JobStatus.SUCCESS
            registry.append_log(job.id, "Stream line 1\n")
            app = create_app(registry=registry)
            client = TestClient(app)

            with client.stream(
                "GET",
                f"/api/jobs/{job.id}/stream",
                auth=("stream_user", "stream_pass"),
            ) as response:
                self.assertEqual(response.status_code, 200)
                for chunk in response.iter_lines():
                    if chunk.startswith("data: "):
                        data = json.loads(chunk[len("data: "):])
                        self.assertEqual(data["event"], "init")
                        break

    def test_case_insensitive_basic_scheme(self):
        import base64
        with patch.dict("os.environ", {"FACTORY_AUTH_USER": "u", "FACTORY_AUTH_PASS": "p"}, clear=True):
            app = create_app()
            client = TestClient(app)
            raw = base64.b64encode(b"u:p").decode("ascii")

            # Lowercase "basic <b64>"
            resp_lower = client.get("/api/repos", headers={"Authorization": f"basic {raw}"})
            self.assertEqual(resp_lower.status_code, 200)

            # Mixed case "bAsIc <b64>"
            resp_mixed = client.get("/api/repos", headers={"Authorization": f"bAsIc {raw}"})
            self.assertEqual(resp_mixed.status_code, 200)

    def test_static_asset_protection(self):
        import tempfile
        from starlette.staticfiles import StaticFiles

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "style.css"
            test_file.write_text("body { color: red; }")

            app = create_app()
            app.mount("/static", StaticFiles(directory=tmpdir), name="static")
            client = TestClient(app)

            # Unauthenticated access to static asset is blocked with 401
            resp_unauth = client.get("/static/style.css")
            self.assertEqual(resp_unauth.status_code, 401)
            self.assertIn("www-authenticate", resp_unauth.headers)

            # Authenticated access to static asset succeeds with 200
            resp_auth = client.get("/static/style.css", auth=("admin", "admin"))
            self.assertEqual(resp_auth.status_code, 200)
            self.assertIn("color: red", resp_auth.text)
