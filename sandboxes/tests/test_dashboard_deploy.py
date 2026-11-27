"""Unit tests for modal-sandbox infra dashboard deployment and Caddy cutover."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from sandbox.dashboard_deploy import (
    DEFAULT_DASHBOARD_APP_SLUG,
    build_dashboard_deploy_parser,
    build_dashboard_remote_env,
    deploy_dashboard,
    find_dashboard_source_dir,
    resolve_dashboard_target,
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

    def test_find_dashboard_source_dir_and_env_builder(self):
        dash_dir = find_dashboard_source_dir()
        self.assertTrue((dash_dir / "deploy.sh").is_file())
        self.assertTrue((dash_dir / "docker-compose.prod.yml").is_file())

        env_vars = build_dashboard_remote_env(
            control_plane_url="https://ws.modal.run",
            username="admin",
            password="secret",
            base_domain="apps.example.com",
            container_name="sandbox-dashboard-staging-web",
            compose_project="sandbox-dashboard-staging",
            dashboard_commit="abc1234",
        )
        self.assertEqual(env_vars["SANDBOX_CONTROL_PLANE_URL"], "https://ws.modal.run")
        self.assertEqual(env_vars["APPS_BASE_DOMAIN"], "apps.example.com")
        self.assertEqual(env_vars["WEB_UI_USERNAME"], "admin")
        self.assertEqual(env_vars["WEB_UI_PASSWORD"], "secret")
        self.assertEqual(env_vars["DASHBOARD_CONTAINER_NAME"], "sandbox-dashboard-staging-web")
        self.assertEqual(env_vars["DASHBOARD_COMPOSE_PROJECT"], "sandbox-dashboard-staging")
        self.assertEqual(env_vars["NEXT_PUBLIC_DASHBOARD_COMMIT"], "abc1234")

    def test_resolve_dashboard_target_isolation(self):
        apex = resolve_dashboard_target(subdomain=False)
        staging = resolve_dashboard_target(subdomain=True)
        self.assertEqual(apex.remote_dir, "/opt/sandbox-dashboard")
        self.assertEqual(apex.container_name, "sandbox-dashboard-web")
        self.assertEqual(apex.compose_project, "sandbox-dashboard")
        self.assertEqual(apex.upstream, "sandbox-dashboard-web:3000")
        self.assertEqual(staging.remote_dir, "/opt/sandbox-dashboard-staging")
        self.assertEqual(staging.container_name, "sandbox-dashboard-staging-web")
        self.assertEqual(staging.compose_project, "sandbox-dashboard-staging")
        self.assertEqual(staging.upstream, "sandbox-dashboard-staging-web:3000")

    @patch("sandbox.dashboard_deploy.ensure_app_caddy_route", return_value=(True, "Routed"))
    @patch("sandbox.dashboard_deploy.execute_remote_dashboard_deploy", return_value=(0, ""))
    @patch("sandbox.dashboard_deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.dashboard_deploy.sync_dashboard_to_vps", return_value=True)
    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_deploy_dashboard_staging_subdomain(
        self,
        _mock_ssh,
        _mock_docker,
        mock_sync,
        mock_write,
        mock_exec,
        mock_route,
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
                subdomain=True,
                dashboard_commit="deadbee",
                stream=False,
            )
        self.assertEqual(code, 0)
        mock_sync.assert_called_once()
        sync_cfg = mock_sync.call_args.args[0]
        self.assertEqual(sync_cfg.remote_dir, "/opt/sandbox-dashboard-staging")
        mock_write.assert_called_once()
        self.assertEqual(mock_write.call_args.args[1], "/opt/sandbox-dashboard-staging/.env")
        self.assertEqual(mock_write.call_args.kwargs["mode"], "0600")
        written_env = mock_write.call_args.args[2]
        self.assertIn("SANDBOX_CONTROL_PLANE_URL=https://ws.modal.run", written_env)
        self.assertIn("DASHBOARD_CONTAINER_NAME=sandbox-dashboard-staging-web", written_env)
        self.assertIn("DASHBOARD_COMPOSE_PROJECT=sandbox-dashboard-staging", written_env)
        self.assertIn("NEXT_PUBLIC_DASHBOARD_COMMIT=deadbee", written_env)
        mock_exec.assert_called_once()
        mock_route.assert_called_once_with(
            VpsSshConfig(
                host="1.2.3.4",
                key_path=self.key_file,
                user="root",
                port=22,
                remote_dir="/opt/sandbox-dashboard-staging",
            ),
            DEFAULT_DASHBOARD_APP_SLUG,
            "dashboard.apps.example.com",
            "sandbox-dashboard-staging-web:3000",
            base_domain="apps.example.com",
            cf_dns_token="cf-tok",
            dashboard_upstream="https://ws.modal.run",
            apex_cli_only=True,
        )

    @patch("sandbox.dashboard_deploy.setup_reverse_proxy", return_value=(True, "Apex ok"))
    @patch("sandbox.dashboard_deploy.execute_remote_dashboard_deploy", return_value=(0, ""))
    @patch("sandbox.dashboard_deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.dashboard_deploy.sync_dashboard_to_vps", return_value=True)
    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_deploy_dashboard_apex_isolation(
        self,
        _mock_ssh,
        _mock_docker,
        mock_sync,
        mock_write,
        _mock_exec,
        mock_proxy,
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
                subdomain=False,
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

    @patch("sandbox.dashboard_deploy.deploy_dashboard", return_value=0)
    @patch("sandbox.dashboard_deploy.resolve_vps_ssh_config")
    def test_modal_sandbox_infra_dashboard_cli_routing(self, mock_cfg, mock_deploy):
        mock_cfg.return_value = self.vps_config
        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra", "dashboard"]),
            self.assertRaises(SystemExit) as ctx,
        ):
            sandbox_main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertFalse(mock_deploy.call_args.kwargs["subdomain"])
        self.assertEqual(mock_cfg.call_args.kwargs["remote_dir"], "/opt/sandbox-dashboard")

        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra", "dashboard", "--subdomain"]),
            self.assertRaises(SystemExit) as ctx_sub,
        ):
            sandbox_main()
        self.assertEqual(ctx_sub.exception.code, 0)
        self.assertTrue(mock_deploy.call_args.kwargs["subdomain"])
        self.assertEqual(mock_cfg.call_args.kwargs["remote_dir"], "/opt/sandbox-dashboard-staging")

        with (
            patch.object(sys, "argv", ["modal-sandbox", "infra"]),
            self.assertRaises(SystemExit) as ctx_bare,
        ):
            sandbox_main()
        self.assertEqual(ctx_bare.exception.code, 2)

    def test_dashboard_parser_rejects_removed_flags(self):
        parser = build_dashboard_deploy_parser()
        for bad in (["--cutover"], ["--check-only"], ["--host", "1.2.3.4"], ["--remote-dir", "/tmp"]):
            with self.assertRaises(SystemExit) as ctx:
                parser.parse_args(bad)
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
