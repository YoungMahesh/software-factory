"""Unit tests for Resource Plane Caddy reverse-proxy automation module."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sandbox.caddy_deploy import (
    CaddyConfig,
    build_caddy_parser,
    check_caddy_running,
    ensure_caddy_network,
    ensure_caddy_route,
    format_caddy_route,
    main as caddy_main,
    parse_caddyfile_domains,
    reload_caddy,
    setup_reverse_proxy,
)
from sandbox.infra_deploy import VpsSshConfig


class TestCaddyDeploy(unittest.TestCase):
    """Test suite for Caddy reverse-proxy configuration, routing, and CLI."""

    def setUp(self):
        self.dummy_key = Path("/tmp/dummy_caddy_key")
        self.dummy_key.write_text("dummy", encoding="utf-8")
        self.vps_config = VpsSshConfig(
            host="1.2.3.4",
            key_path=self.dummy_key,
            user="root",
            port=22,
        )

    def tearDown(self):
        if self.dummy_key.exists():
            self.dummy_key.unlink()

    def test_parse_caddyfile_domains(self):
        content = """
{
    email admin@example.com
}

# Comment line
s3-split.mahesh0.dev {
    reverse_proxy cS3Split:3000
}

db-host.mahesh0.dev {
    reverse_proxy db-host-web:3000
}
"""
        domains = parse_caddyfile_domains(content)
        self.assertIn("s3-split.mahesh0.dev", domains)
        self.assertIn("db-host.mahesh0.dev", domains)
        self.assertEqual(len(domains), 2)

    def test_format_caddy_route(self):
        block = format_caddy_route("db-host.example.com", "db-host-web:3000")
        self.assertIn("db-host.example.com {", block)
        self.assertIn("reverse_proxy db-host-web:3000", block)

    @patch("subprocess.run")
    def test_check_caddy_running_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="running\n", stderr="")
        ok, msg = check_caddy_running(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("is running", msg)

    @patch("subprocess.run")
    def test_check_caddy_running_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not_running\n", stderr="")
        ok, msg = check_caddy_running(self.vps_config)
        self.assertFalse(ok)
        self.assertIn("not running", msg)

    @patch("subprocess.run")
    def test_ensure_caddy_network_connected(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="connected\n", stderr="")
        ok, msg = ensure_caddy_network(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("is connected to network", msg)

    @patch("subprocess.run")
    def test_ensure_caddy_route_already_present(self, mock_run):
        caddyfile = "db-host.mahesh0.dev {\n\treverse_proxy db-host-web:3000\n}\n"
        mock_run.return_value = MagicMock(returncode=0, stdout=caddyfile, stderr="")
        ok, msg = ensure_caddy_route(self.vps_config, "db-host.mahesh0.dev")
        self.assertTrue(ok)
        self.assertIn("already configured", msg)
        self.assertEqual(mock_run.call_count, 1)

    @patch("subprocess.run")
    def test_ensure_caddy_route_appended(self, mock_run):
        read_res = MagicMock(returncode=0, stdout="other.dev {\n}\n", stderr="")
        write_res = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = [read_res, write_res]
        ok, msg = ensure_caddy_route(self.vps_config, "new-domain.dev")
        self.assertTrue(ok)
        self.assertIn("Added reverse-proxy route", msg)
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_reload_caddy_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, msg = reload_caddy(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("Successfully reloaded Caddy", msg)

    @patch("sandbox.caddy_deploy.check_caddy_running")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    @patch("sandbox.caddy_deploy.ensure_caddy_route")
    @patch("sandbox.caddy_deploy.reload_caddy")
    def test_setup_reverse_proxy_end_to_end(self, mock_reload, mock_route, mock_net, mock_check):
        mock_check.return_value = (True, "Caddy running")
        mock_net.return_value = (True, "Connected")
        mock_route.return_value = (True, "Route added")
        mock_reload.return_value = (True, "Reloaded")

        ok, msg = setup_reverse_proxy(
            self.vps_config,
            domain="db-host.example.com",
            s3_domain="s3.example.com",
        )
        self.assertTrue(ok)
        self.assertIn("Reverse-proxy successfully configured", msg)
        self.assertEqual(mock_route.call_count, 2)

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    def test_caddy_cli_check_only(self, mock_net, mock_check, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_check.return_value = (True, "Caddy running")
        mock_net.return_value = (True, "Connected")

        ret = caddy_main(["--check-only", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(ret, 0)

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    def test_caddy_cli_setup(self, mock_setup, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_setup.return_value = (True, "Configured")

        ret = caddy_main([
            "--domain", "my-domain.dev",
            "--host", "1.2.3.4",
            "--key", str(self.dummy_key),
        ])
        self.assertEqual(ret, 0)
        mock_setup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
