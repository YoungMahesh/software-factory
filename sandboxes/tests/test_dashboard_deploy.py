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
    build_dashboard_remote_env,
    deploy_dashboard,
    find_dashboard_source_dir,
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
        )
        self.assertEqual(env_vars["SANDBOX_CONTROL_PLANE_URL"], "https://ws.modal.run")
        self.assertEqual(env_vars["APPS_BASE_DOMAIN"], "apps.example.com")
        self.assertEqual(env_vars["WEB_UI_USERNAME"], "admin")
        self.assertEqual(env_vars["WEB_UI_PASSWORD"], "secret")

    def test_deploy_dashboard_rejects_subdomain_with_cutover(self):
        code = deploy_dashboard(
            self.vps_config,
            factory_root=self.tmp_path,
            dotenv={},
            subdomain="dashboard",
            cutover=True,
        )
        self.assertEqual(code, 1)

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
                subdomain="dashboard",
                stream=False,
            )
        self.assertEqual(code, 0)
        mock_sync.assert_called_once()
        mock_write.assert_called_once()
        self.assertEqual(mock_write.call_args.kwargs["mode"], "0600")
        self.assertIn("SANDBOX_CONTROL_PLANE_URL=https://ws.modal.run", mock_write.call_args.args[2])
        mock_exec.assert_called_once()
        mock_route.assert_called_once_with(
            self.vps_config,
            DEFAULT_DASHBOARD_APP_SLUG,
            "dashboard.apps.example.com",
            "sandbox-dashboard-web:3000",
            base_domain="apps.example.com",
            cf_dns_token="cf-tok",
        )

    @patch("sandbox.dashboard_deploy.remove_app_caddy_route", return_value=(True, "Removed"))
    @patch("sandbox.dashboard_deploy.setup_reverse_proxy", return_value=(True, "Apex cutover ok"))
    @patch("sandbox.dashboard_deploy.execute_remote_dashboard_deploy", return_value=(0, ""))
    @patch("sandbox.dashboard_deploy._write_remote_b64", return_value=(True, "ok"))
    @patch("sandbox.dashboard_deploy.sync_dashboard_to_vps", return_value=True)
    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_deploy_dashboard_apex_cutover(
        self,
        _mock_ssh,
        _mock_docker,
        _mock_sync,
        _mock_write,
        _mock_exec,
        mock_proxy,
        mock_remove,
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
                cutover=True,
                stream=False,
            )
        self.assertEqual(code, 0)
        mock_proxy.assert_called_once()
        self.assertEqual(mock_proxy.call_args.kwargs["dashboard_upstream"], "https://ws.modal.run")
        self.assertEqual(
            mock_proxy.call_args.kwargs["dashboard_web_upstream"],
            "sandbox-dashboard-web:3000",
        )
        mock_remove.assert_called_once_with(self.vps_config, DEFAULT_DASHBOARD_APP_SLUG)

    @patch("sandbox.dashboard_deploy.check_remote_docker", return_value=(True, "Docker ok"))
    @patch("sandbox.dashboard_deploy.check_ssh_connection", return_value=True)
    def test_modal_sandbox_infra_dashboard_cli_routing(self, _mock_ssh, _mock_docker):
        with (
            patch.object(
                sys,
                "argv",
                [
                    "modal-sandbox",
                    "infra",
                    "dashboard",
                    "--check-only",
                    "--host",
                    "1.2.3.4",
                    "--key",
                    str(self.key_file),
                ],
            ),
            self.assertRaises(SystemExit) as ctx,
        ):
            sandbox_main()
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
