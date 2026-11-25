"""Unit tests for host-only Hosted App deployment (deploy-app) and Caddy app routing."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sandbox.app_deploy import (
    build_remote_app_env,
    check_app_route_collision,
    render_app_route,
    resolve_app_domain,
    resolve_deploy_target,
    serialize_dotenv,
)
from sandbox.app_deploy._cli import main as deploy_app_main
from sandbox.infra_deploy import VpsSshConfig
from sandbox.main import main as sandbox_main


class TestAppDeployConfigAndCaddy(unittest.TestCase):
    """Tests target resolution, domain rules, env synthesis, and per-app Caddy snippets."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.dummy_key = self.tmp_path / "vps_key"
        self.dummy_key.write_text("dummy", encoding="utf-8")
        self.dummy_key.chmod(0o600)
        self.vps_config = VpsSshConfig(host="1.2.3.4", key_path=self.dummy_key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_deploy_target_local_github_and_factory_guard(self):
        app_dir = self.tmp_path / "my-saas"
        app_dir.mkdir()
        (app_dir / "package.json").write_text('{"name":"my-saas"}', encoding="utf-8")

        t_local = resolve_deploy_target(None, None, cwd=app_dir, default_org="sFactory0")
        self.assertEqual(t_local.source_mode, "local")
        self.assertEqual(t_local.bare_repo, "my-saas")
        self.assertEqual(t_local.local_dir, app_dir.resolve())

        t_gh = resolve_deploy_target(None, "custom-org/billing-app", cwd=app_dir, default_org="sFactory0")
        self.assertEqual(t_gh.source_mode, "github")
        self.assertEqual(t_gh.org_name, "custom-org")
        self.assertEqual(t_gh.bare_repo, "billing-app")

        t_pos_gh = resolve_deploy_target("remote-only-app", None, cwd=self.tmp_path, default_org="sFactory0")
        self.assertEqual(t_pos_gh.source_mode, "github")
        self.assertEqual(t_pos_gh.bare_repo, "remote-only-app")

        with self.assertRaises(FileNotFoundError):
            resolve_deploy_target("./does-not-exist", None, cwd=self.tmp_path)

        factory_root = Path(__file__).resolve().parents[2]
        with self.assertRaises(ValueError):
            resolve_deploy_target(None, None, cwd=factory_root)

    def test_resolve_app_domain_and_build_remote_app_env(self):
        sub, fqdn = resolve_app_domain("my-app", "sf.mahesh0.dev")
        self.assertEqual((sub, fqdn), ("my-app", "my-app.sf.mahesh0.dev"))

        sub2, fqdn2 = resolve_app_domain("my-app", "sf.mahesh0.dev", subdomain="demo.sf.mahesh0.dev")
        self.assertEqual((sub2, fqdn2), ("demo", "demo.sf.mahesh0.dev"))

        env_dict = build_remote_app_env(
            {
                "NODE_ENV": "development",
                "NEXT_PUBLIC_APP_URL": "http://localhost:3000",
                "DATABASE_URL": "postgresql://u:p@db-host.mahesh0.dev:54320/app?sslmode=verify-full&sslrootcert=/home/dev/.config/resource-plane/ca.crt",
                "BETTER_AUTH_SECRET": "sec123",
            },
            fqdn="my-app.sf.mahesh0.dev",
            container_name="my-app-web",
        )
        self.assertEqual(env_dict["NODE_ENV"], "production")
        self.assertEqual(env_dict["NEXT_PUBLIC_APP_URL"], "https://my-app.sf.mahesh0.dev")
        self.assertEqual(env_dict["EXPO_PUBLIC_API_URL"], "https://my-app.sf.mahesh0.dev")
        self.assertEqual(env_dict["APP_CONTAINER_NAME"], "my-app-web")
        self.assertEqual(env_dict["RESOURCE_PLANE_CA_CERT"], "/app/.certs/ca.crt")
        self.assertIn("sslrootcert=%2Fapp%2F.certs%2Fca.crt", env_dict["DATABASE_URL"])
        self.assertIn('APP_CONTAINER_NAME=my-app-web', serialize_dotenv(env_dict))

    @patch("sandbox.app_deploy._caddy._ssh_run")
    def test_check_app_route_collision_detects_other_app_and_allows_redeploy(self, mock_ssh):
        mock_ssh.return_value = subprocess.CompletedProcess(
            [],
            0,
            "FILE:other-app.caddy\n" + render_app_route("other-app", "api.sf.mahesh0.dev", "other-app-web:3000") + "\n---END---\n",
            "",
        )
        ok_self, _ = check_app_route_collision(self.vps_config, "other-app", "api.sf.mahesh0.dev")
        self.assertTrue(ok_self)

        ok_other, msg = check_app_route_collision(self.vps_config, "new-app", "api.sf.mahesh0.dev")
        self.assertFalse(ok_other)
        self.assertIn("already assigned", msg)


class TestAppDeployCli(unittest.TestCase):
    """Tests CLI validation and modal-sandbox dispatch."""


    def test_cli_purge_requires_down_and_modal_sandbox_dispatch(self):
        with self.assertRaises(SystemExit) as ctx:
            deploy_app_main(["--purge"])
        self.assertNotEqual(ctx.exception.code, 0)

        with patch("scripts.deploy_app.main", return_value=0) as mock_main:
            with patch("sys.argv", ["modal-sandbox", "deploy-app", "--help"]):
                with self.assertRaises(SystemExit) as exc:
                    sandbox_main()
                self.assertEqual(exc.exception.code, 0)
                mock_main.assert_called_once_with(["--help"])


if __name__ == "__main__":
    unittest.main()
