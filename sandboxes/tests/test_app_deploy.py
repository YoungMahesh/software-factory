"""Unit tests for host-only Hosted App deployment (deploy-app) and Caddy app routing."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.app_deploy import (
    AppDeployRequest,
    build_remote_app_env,
    check_app_route_collision,
    deploy_app,
    ensure_app_caddy_route,
    remove_app_caddy_route,
    render_app_route,
    resolve_app_domain,
    resolve_deploy_target,
    serialize_dotenv,
    teardown_app,
)
from sandbox.app_deploy._cli import main as deploy_app_main
from sandbox.env_store import VaultBundle
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

    @patch("sandbox.caddy_deploy.reload_caddy")
    @patch("sandbox.app_deploy._caddy.write_and_validate_caddy_file")
    @patch("sandbox.app_deploy._caddy.check_app_route_collision")
    @patch("sandbox.app_deploy._caddy._read_remote")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    def test_ensure_and_remove_app_caddy_route(
        self, mock_running, mock_net, mock_read, mock_col, mock_write, mock_reload
    ):
        mock_running.return_value = (True, "running")
        mock_net.return_value = (True, "connected")
        mock_read.return_value = (True, "sf.mahesh0.dev, *.sf.mahesh0.dev {\n}\n")
        mock_col.return_value = (True, "")
        mock_write.return_value = (True, True, "Updated")
        mock_reload.return_value = (True, "Reloaded")

        ok, msg = ensure_app_caddy_route(self.vps_config, "my-app", "my-app.sf.mahesh0.dev", "my-app-web:3000")
        self.assertTrue(ok)
        self.assertIn("https://my-app.sf.mahesh0.dev", msg)

        with patch("sandbox.app_deploy._caddy._ssh_run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            rm_ok, rm_msg = remove_app_caddy_route(self.vps_config, "my-app")
        self.assertTrue(rm_ok)
        self.assertIn("Removed", rm_msg)


class TestAppDeployOrchestrationAndCli(unittest.TestCase):
    """Tests deploy_app pipeline, teardown_app, and CLI dispatch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.factory_root = self.tmp_path / "factory"
        self.factory_root.mkdir()
        key_file = self.factory_root / ".secrets" / "resource_plane_ssh"
        key_file.parent.mkdir(parents=True)
        key_file.write_text("ssh-key", encoding="utf-8")
        key_file.chmod(0o600)
        (self.factory_root / ".env").write_text(
            "RESOURCE_PLANE_SSH_HOST=vps.example.com\n"
            "RESOURCE_PLANE_SSH_KEY=.secrets/resource_plane_ssh\n"
            "APPS_BASE_DOMAIN=sf.mahesh0.dev\n"
            "GH_ORG_NAME=sFactory0\n"
            "GH_TOKEN=ghp_test\n",
            encoding="utf-8",
        )
        self.app_dir = self.tmp_path / "demo-app"
        self.app_dir.mkdir()
        (self.app_dir / "package.json").write_text('{"name":"demo-app"}', encoding="utf-8")
        (self.app_dir / "docker-compose.yml").write_text("services:\n  web:\n    image: x\n", encoding="utf-8")
        (self.app_dir / ".env").write_text("NODE_ENV=development\nBETTER_AUTH_SECRET=abc\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("sandbox.app_deploy._deploy.ensure_app_caddy_route", return_value=(True, "Route active"))
    @patch("sandbox.app_deploy._deploy.ensure_docker_network", return_value=(True, "net ok"))
    @patch("sandbox.app_deploy._deploy.stage_remote_ca_cert", return_value=True)
    @patch("sandbox.app_deploy._deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.app_deploy._deploy.sync_local_app_to_vps")
    @patch("sandbox.app_deploy._deploy.check_app_route_collision", return_value=(True, ""))
    @patch("sandbox.app_deploy._deploy._maybe_ensure_wildcard_ready", return_value=None)
    @patch("sandbox.app_deploy._deploy._read_remote", return_value=(True, ""))
    @patch("sandbox.app_deploy._deploy.check_remote_docker", return_value=(True, "docker ok"))
    @patch("sandbox.app_deploy._deploy.check_ssh_connection", return_value=True)
    @patch("sandbox.app_deploy._deploy._ssh_run")
    @patch("subprocess.run")
    def test_deploy_app_local_mode_with_migrations(
        self, mock_subproc, mock_ssh, mock_conn, mock_docker, mock_read,
        mock_wc, mock_col, mock_sync, mock_write, mock_ca, mock_net, mock_route
    ):
        mock_ssh.side_effect = [
            subprocess.CompletedProcess([], 0, "ok\n", ""),    # docker-compose.yml check
            subprocess.CompletedProcess([], 0, "yes\n", ""),   # drizzle/*.sql check
            subprocess.CompletedProcess([], 0, "ok\n", ""),    # health check
        ]
        mock_subproc.return_value = subprocess.CompletedProcess([], 0, "", "")

        res = deploy_app(
            AppDeployRequest(target=str(self.app_dir)),
            repo_root=self.factory_root,
        )
        self.assertEqual(res.repo_name, "demo-app")
        self.assertEqual(res.remote_dir, "/root/demo-app")
        self.assertEqual(res.url, "https://demo-app.sf.mahesh0.dev")
        self.assertEqual(res.source_mode, "local")
        self.assertTrue(res.migrated)
        mock_sync.assert_called_once()
        mock_route.assert_called_once()
        env_write = mock_write.call_args
        self.assertIn("NEXT_PUBLIC_APP_URL=https://demo-app.sf.mahesh0.dev", env_write.args[2])

    @patch("sandbox.app_deploy._deploy.ensure_app_caddy_route", return_value=(True, "Route active"))
    @patch("sandbox.app_deploy._deploy.ensure_docker_network", return_value=(True, "net ok"))
    @patch("sandbox.app_deploy._deploy.stage_remote_ca_cert", return_value=False)
    @patch("sandbox.app_deploy._deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.app_deploy._deploy.sync_github_app_on_vps")
    @patch("sandbox.app_deploy._deploy.resolve_sandbox_bundle")
    @patch("sandbox.app_deploy._deploy.check_app_route_collision", return_value=(True, ""))
    @patch("sandbox.app_deploy._deploy._maybe_ensure_wildcard_ready", return_value=None)
    @patch("sandbox.app_deploy._deploy._read_remote", return_value=(True, ""))
    @patch("sandbox.app_deploy._deploy.check_remote_docker", return_value=(True, "docker ok"))
    @patch("sandbox.app_deploy._deploy.check_ssh_connection", return_value=True)
    @patch("sandbox.app_deploy._deploy._ssh_run")
    @patch("subprocess.run")
    def test_deploy_app_github_mode_pulls_vault_and_skips_missing_migrations(
        self, mock_subproc, mock_ssh, mock_conn, mock_docker, mock_read,
        mock_wc, mock_col, mock_bundle, mock_gh_sync, mock_write, mock_ca, mock_net, mock_route
    ):
        mock_bundle.return_value = VaultBundle(env_dict={"BETTER_AUTH_SECRET": "vault_secret"})
        mock_ssh.side_effect = [
            subprocess.CompletedProcess([], 0, "ok\n", ""),
            subprocess.CompletedProcess([], 0, "no\n", ""),
            subprocess.CompletedProcess([], 0, "ok\n", ""),
        ]
        mock_subproc.return_value = subprocess.CompletedProcess([], 0, "", "")

        res = deploy_app(
            AppDeployRequest(repo="sandbox-app", subdomain="preview"),
            repo_root=self.factory_root,
            cwd=self.tmp_path,
        )
        self.assertEqual(res.source_mode, "github")
        self.assertEqual(res.remote_dir, "/root/sandbox-app")
        self.assertEqual(res.url, "https://preview.sf.mahesh0.dev")
        self.assertFalse(res.migrated)
        mock_gh_sync.assert_called_once()
        self.assertIn("BETTER_AUTH_SECRET=vault_secret", mock_write.call_args.args[2])

    @patch("sandbox.app_deploy._deploy.remove_app_caddy_route", return_value=(True, "Removed"))
    @patch("sandbox.app_deploy._deploy.check_ssh_connection", return_value=True)
    @patch("sandbox.app_deploy._deploy._ssh_run", return_value=subprocess.CompletedProcess([], 0, "", ""))
    def test_teardown_app_stops_compose_and_removes_route(self, mock_ssh, mock_conn, mock_rm):
        res = teardown_app(
            AppDeployRequest(repo="demo-app"),
            purge=True,
            repo_root=self.factory_root,
            cwd=self.tmp_path,
        )
        self.assertTrue(res.purged)
        self.assertIn("rm -rf '/root/demo-app'", mock_ssh.call_args.args[1])
        mock_rm.assert_called_once()

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
