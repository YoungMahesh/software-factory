"""Unit tests for modal-sandbox infra dashboard and deployer orchestration."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from sandbox.dashboard_deploy import (
    DASHBOARD_TARGET,
    DEFAULT_DEPLOYER_APP_SLUG,
    DEPLOYER_TARGET,
    build_dashboard_deploy_parser,
    build_dashboard_remote_env,
    build_deployer_deploy_parser,
    cleanup_legacy_staging_dashboard,
    deploy_dashboard,
    deploy_deployer,
    find_dashboard_source_dir,
    find_deployer_source_dir,
)
from sandbox.infra_deploy import VpsSshConfig
from sandbox.main import main as sandbox_main


class TestDashboardDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.key_file = self.tmp_path / "vps_key"
        self.key_file.write_text("dummy", encoding="utf-8")
        self.key_file.chmod(0o600)
        self.vps_config = VpsSshConfig(
            host="1.2.3.4",
            key_path=self.key_file,
            remote_dir="/opt/sandbox-dashboard",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_source_dirs_and_env_builder(self):
        dash_dir = find_dashboard_source_dir()
        self.assertTrue((dash_dir / "deploy.sh").is_file())
        self.assertTrue((dash_dir / "docker-compose.prod.yml").is_file())

        deployer_dir = find_deployer_source_dir()
        self.assertTrue((deployer_dir / "deploy.sh").is_file())
        self.assertTrue((deployer_dir / "docker-compose.prod.yml").is_file())

        env_vars = build_dashboard_remote_env(
            control_plane_url="https://ws.modal.run",
            username="admin",
            password="secret",
            base_domain="apps.example.com",
            container_name="dashboard-deployer-web",
            compose_project="dashboard-deployer",
            dashboard_commit="abc1234",
        )
        self.assertEqual(env_vars["SANDBOX_CONTROL_PLANE_URL"], "https://ws.modal.run")
        self.assertEqual(env_vars["APPS_BASE_DOMAIN"], "apps.example.com")
        self.assertEqual(env_vars["WEB_UI_USERNAME"], "admin")
        self.assertEqual(env_vars["WEB_UI_PASSWORD"], "secret")
        self.assertEqual(env_vars["DASHBOARD_CONTAINER_NAME"], "dashboard-deployer-web")
        self.assertEqual(env_vars["DASHBOARD_COMPOSE_PROJECT"], "dashboard-deployer")
        self.assertEqual(env_vars["NEXT_PUBLIC_DASHBOARD_COMMIT"], "abc1234")

    def test_target_constants(self):
        self.assertEqual(DASHBOARD_TARGET.remote_dir, "/opt/sandbox-dashboard")
        self.assertEqual(DASHBOARD_TARGET.container_name, "sandbox-dashboard-web")
        self.assertEqual(DASHBOARD_TARGET.compose_project, "sandbox-dashboard")
        self.assertEqual(DASHBOARD_TARGET.upstream, "sandbox-dashboard-web:3000")
        self.assertEqual(DEPLOYER_TARGET.remote_dir, "/opt/dashboard-deployer")
        self.assertEqual(DEPLOYER_TARGET.container_name, "dashboard-deployer-web")
        self.assertEqual(DEPLOYER_TARGET.compose_project, "dashboard-deployer")
        self.assertEqual(DEPLOYER_TARGET.upstream, "dashboard-deployer-web:3000")

    @patch("sandbox.dashboard_deploy.subprocess.run")
    @patch("sandbox.dashboard_deploy.remove_app_caddy_route", return_value=(True, "Removed"))
    def test_cleanup_legacy_staging_dashboard(self, mock_remove_route, mock_run):
        mock_run.return_value = type("CP", (), {"returncode": 0, "stdout": "REMOVED_STAGING\n", "stderr": ""})()
        logs: list[str] = []
        cleanup_legacy_staging_dashboard(self.vps_config, log_cb=logs.append)
        mock_remove_route.assert_called_once_with(self.vps_config, "sandbox-dashboard")
        mock_run.assert_called_once()
        ssh_args = mock_run.call_args.args[0]
        self.assertIn("/opt/sandbox-dashboard-staging", " ".join(ssh_args))
        self.assertEqual(len(logs), 2)

    @patch("sandbox.dashboard_deploy.cleanup_legacy_staging_dashboard")
    @patch("sandbox.dashboard_deploy.setup_reverse_proxy", return_value=(True, "Apex ok"))
    @patch("sandbox.dashboard_deploy.execute_remote_dashboard_deploy", return_value=(0, ""))
    @patch("sandbox.dashboard_deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.dashboard_deploy.sync_dashboard_to_vps", return_value=True)
    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_deploy_dashboard_apex(
        self,
        _mock_ssh,
        _mock_docker,
        mock_sync,
        mock_write,
        _mock_exec,
        mock_proxy,
        mock_cleanup,
    ):
        dotenv = {
            "APPS_BASE_DOMAIN": "apps.example.com",
            "SANDBOX_DASHBOARD_UPSTREAM": "https://ws.modal.run",
            "CLOUDFLARE_DNS_API_TOKEN": "cf-tok",
            "WEB_UI_USERNAME": "admin",
            "WEB_UI_PASSWORD": "secret",
        }
        with patch.dict(os.environ, dotenv, clear=True):
            code = deploy_dashboard(
                self.vps_config,
                factory_root=self.tmp_path,
                dotenv=dotenv,
                dashboard_commit="cafebabe",
                stream=False,
            )
        self.assertEqual(code, 0)
        self.assertEqual(mock_sync.call_args.args[0].remote_dir, "/opt/sandbox-dashboard")
        self.assertEqual(mock_write.call_args.args[1], "/opt/sandbox-dashboard/.env")
        self.assertIn("NEXT_PUBLIC_DASHBOARD_COMMIT=cafebabe", mock_write.call_args.args[2])
        mock_proxy.assert_called_once()
        self.assertTrue(mock_proxy.call_args.kwargs["wildcard"])
        self.assertTrue(mock_proxy.call_args.kwargs["dashboard"])
        self.assertEqual(mock_proxy.call_args.kwargs["dashboard_upstream"], "https://ws.modal.run")
        self.assertEqual(
            mock_proxy.call_args.kwargs["dashboard_web_upstream"],
            "sandbox-dashboard-web:3000",
        )
        mock_cleanup.assert_called_once()

    @patch("sandbox.dashboard_deploy.cleanup_legacy_staging_dashboard")
    @patch("sandbox.dashboard_deploy.ensure_app_caddy_route", return_value=(True, "Routed"))
    @patch("sandbox.dashboard_deploy.execute_remote_dashboard_deploy", return_value=(0, ""))
    @patch("sandbox.dashboard_deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.dashboard_deploy.sync_deployer_to_vps", return_value=True)
    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_deploy_deployer_subdomain(
        self,
        _mock_ssh,
        _mock_docker,
        mock_sync,
        mock_write,
        mock_exec,
        mock_route,
        mock_cleanup,
    ):
        dotenv = {
            "APPS_BASE_DOMAIN": "apps.example.com",
            "SANDBOX_DASHBOARD_UPSTREAM": "https://ws.modal.run",
            "CLOUDFLARE_DNS_API_TOKEN": "cf-tok",
            "WEB_UI_USERNAME": "admin",
            "WEB_UI_PASSWORD": "secret",
        }
        with patch.dict(os.environ, dotenv, clear=True):
            code = deploy_deployer(
                self.vps_config,
                factory_root=self.tmp_path,
                dotenv=dotenv,
                dashboard_commit="deadbee",
                stream=False,
            )
        self.assertEqual(code, 0)
        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.args[0].remote_dir, "/opt/dashboard-deployer")
        mock_write.assert_called_once()
        self.assertEqual(mock_write.call_args.args[1], "/opt/dashboard-deployer/.env")
        self.assertEqual(mock_write.call_args.kwargs["mode"], "0600")
        written_env = mock_write.call_args.args[2]
        self.assertIn("SANDBOX_CONTROL_PLANE_URL=https://ws.modal.run", written_env)
        self.assertIn("DASHBOARD_CONTAINER_NAME=dashboard-deployer-web", written_env)
        self.assertIn("DASHBOARD_COMPOSE_PROJECT=dashboard-deployer", written_env)
        self.assertIn("NEXT_PUBLIC_DASHBOARD_COMMIT=deadbee", written_env)
        mock_exec.assert_called_once()
        mock_route.assert_called_once_with(
            VpsSshConfig(
                host="1.2.3.4",
                key_path=self.key_file,
                user="root",
                port=22,
                remote_dir="/opt/dashboard-deployer",
            ),
            DEFAULT_DEPLOYER_APP_SLUG,
            "deploy.apps.example.com",
            "dashboard-deployer-web:3000",
            base_domain="apps.example.com",
            cf_dns_token="cf-tok",
            dashboard_upstream="https://ws.modal.run",
            apex_cli_only=True,
        )
        mock_cleanup.assert_called_once()

    @patch("sandbox.dashboard_deploy.deploy_deployer", return_value=0)
    @patch("sandbox.dashboard_deploy.deploy_dashboard", return_value=0)
    @patch("sandbox.dashboard_deploy.resolve_vps_ssh_config")
    def test_modal_sandbox_infra_cli_routing(self, mock_cfg, mock_deploy_dash, mock_deploy_deployer):
        mock_cfg.return_value = self.vps_config
        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra", "dashboard"]),
            self.assertRaises(SystemExit) as ctx,
        ):
            sandbox_main()
        self.assertEqual(ctx.exception.code, 0)
        mock_deploy_dash.assert_called_once()
        self.assertEqual(mock_cfg.call_args.kwargs["remote_dir"], "/opt/sandbox-dashboard")

        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra", "deployer"]),
            self.assertRaises(SystemExit) as ctx_dep,
        ):
            sandbox_main()
        self.assertEqual(ctx_dep.exception.code, 0)
        mock_deploy_deployer.assert_called_once()
        self.assertEqual(mock_cfg.call_args.kwargs["remote_dir"], "/opt/dashboard-deployer")

        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra"]),
            self.assertRaises(SystemExit) as ctx_bare,
        ):
            sandbox_main()
        self.assertEqual(ctx_bare.exception.code, 2)

    def test_parsers_reject_removed_flags(self):
        dash_parser = build_dashboard_deploy_parser()
        for bad in (["--subdomain"], ["--cutover"], ["--check-only"], ["--host", "1.2.3.4"], ["--remote-dir", "/tmp"]):
            with self.assertRaises(SystemExit) as ctx:
                dash_parser.parse_args(bad)
            self.assertEqual(ctx.exception.code, 2)

        deployer_parser = build_deployer_deploy_parser()
        for bad in (["--subdomain"], ["--host", "1.2.3.4"]):
            with self.assertRaises(SystemExit) as ctx:
                deployer_parser.parse_args(bad)
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
