"""Unit tests for Host Ingress Proxy (/opt/caddy) automation module."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sandbox.caddy_deploy import (
    DEFAULT_CADDY_CONTAINER,
    DEFAULT_CADDY_DIR,
    DEFAULT_CADDYFILE_PATH,
    DEFAULT_RESOURCE_PLANE_SITE_PATH,
    CaddyConfig,
    build_caddy_parser,
    caddyfile_imports_sites,
    check_caddy_running,
    check_ports_available,
    ensure_caddy_network,
    find_caddy_source_dir,
    format_caddy_route,
    main as caddy_main,
    parse_caddyfile_domains,
    reload_caddy,
    render_base_caddyfile,
    render_resource_plane_site,
    setup_reverse_proxy,
    validate_caddy,
)
from sandbox.infra_deploy import VpsSshConfig


class TestCaddyDeploy(unittest.TestCase):
    """Test suite for /opt/caddy configuration, bootstrapping, routing, and CLI."""

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

    def test_canonical_defaults(self):
        cfg = CaddyConfig()
        self.assertEqual(DEFAULT_CADDY_DIR, "/opt/caddy")
        self.assertEqual(DEFAULT_CADDYFILE_PATH, "/opt/caddy/conf/Caddyfile")
        self.assertEqual(DEFAULT_RESOURCE_PLANE_SITE_PATH, "/opt/caddy/conf/sites/resource-plane.caddy")
        self.assertEqual(DEFAULT_CADDY_CONTAINER, "caddy")
        self.assertEqual(cfg.caddy_dir, "/opt/caddy")
        self.assertEqual(cfg.container_name, "caddy")

    def test_find_caddy_source_dir(self):
        caddy_dir = find_caddy_source_dir()
        self.assertTrue((caddy_dir / "docker-compose.yml").is_file())
        self.assertTrue((caddy_dir / "conf" / "Caddyfile").is_file())

    def test_caddyfile_imports_sites(self):
        self.assertTrue(caddyfile_imports_sites("{\n}\n\nimport /etc/caddy/sites/*.caddy\n"))
        self.assertTrue(caddyfile_imports_sites("import sites/*.caddy\n"))
        self.assertFalse(caddyfile_imports_sites("# import /etc/caddy/sites/*.caddy\ndb.dev {\n}\n"))

    def test_render_base_caddyfile(self):
        no_email = render_base_caddyfile()
        self.assertNotIn("email", no_email)
        self.assertIn("import /etc/caddy/sites/*.caddy", no_email)

        with_email = render_base_caddyfile("ops@example.com")
        self.assertIn("email ops@example.com", with_email)
        self.assertIn("import /etc/caddy/sites/*.caddy", with_email)

    def test_parse_caddyfile_domains_and_render_site(self):
        site = render_resource_plane_site(
            domain="db-host.example.com",
            s3_domain="s3.example.com",
        )
        self.assertIn("db-host.example.com {", site)
        self.assertIn("reverse_proxy db-host-web:3000", site)
        self.assertIn("s3.example.com {", site)
        self.assertIn("reverse_proxy neon-seaweedfs:8333", site)

        domains = parse_caddyfile_domains(site)
        self.assertEqual(domains, ["db-host.example.com", "s3.example.com"])

    def test_format_caddy_route(self):
        block = format_caddy_route("DB-Host.Example.com", "db-host-web:3000")
        self.assertIn("db-host.example.com {", block)
        self.assertIn("reverse_proxy db-host-web:3000", block)

    @patch("subprocess.run")
    def test_check_caddy_running_success_and_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="running\n", stderr="")
        ok, msg = check_caddy_running(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("caddy", msg)

        mock_run.return_value = MagicMock(returncode=0, stdout="not_running\n", stderr="")
        ok, msg = check_caddy_running(self.vps_config)
        self.assertFalse(ok)
        self.assertIn("not running", msg)

    @patch("subprocess.run")
    def test_check_ports_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="FREE\n", stderr="")
        ok, _ = check_ports_available(self.vps_config)
        self.assertTrue(ok)

        mock_run.return_value = MagicMock(returncode=0, stdout="BUSY:cCaddy 0.0.0.0:80->80/tcp\n", stderr="")
        ok, msg = check_ports_available(self.vps_config)
        self.assertFalse(ok)
        self.assertIn("already in use", msg)

    @patch("subprocess.run")
    def test_ensure_caddy_network_connected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ok\n", stderr=""),
            MagicMock(returncode=0, stdout="connected\n", stderr=""),
        ]
        ok, msg = ensure_caddy_network(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("is connected to network", msg)


    @patch("subprocess.run")
    def test_reload_caddy_validates_then_reloads(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        ok, msg = reload_caddy(self.vps_config)
        self.assertTrue(ok)
        self.assertIn("Successfully reloaded Caddy", msg)
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_validate_caddy_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="syntax error")
        ok, msg = validate_caddy(self.vps_config)
        self.assertFalse(ok)
        self.assertIn("syntax error", msg)


    @patch("sandbox.caddy_deploy.check_caddy_running")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    @patch("sandbox.caddy_deploy.ensure_caddy_site_config")
    @patch("sandbox.caddy_deploy.reload_caddy")
    def test_setup_reverse_proxy_skips_reload_when_unchanged(
        self, mock_reload, mock_site, mock_net, mock_check
    ):
        mock_check.return_value = (True, "running")
        mock_net.return_value = (True, "connected")
        mock_site.return_value = (True, False, "already up to date")

        ok, msg = setup_reverse_proxy(self.vps_config, domain="db-host.example.com")
        self.assertTrue(ok)
        self.assertIn("reload skipped", msg)
        mock_reload.assert_not_called()

    @patch("sandbox.caddy_deploy.check_caddy_running")
    def test_setup_reverse_proxy_missing_caddy_hints_bootstrap(self, mock_check):
        mock_check.return_value = (False, "Caddy container 'caddy' is not running.")
        ok, msg = setup_reverse_proxy(self.vps_config, domain="db-host.example.com")
        self.assertFalse(ok)
        self.assertIn("--bootstrap", msg)

    def test_parser_rejects_removed_path_override_flags(self):
        parser = build_caddy_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--caddy-dir", "/custom"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--caddyfile", "/custom/Caddyfile"])

    def test_cli_rejects_email_without_bootstrap(self):
        ret = caddy_main(["--email", "ops@example.com", "--domain", "db.dev"])
        self.assertEqual(ret, 1)

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    def test_cli_bootstrap_only_without_domain(self, mock_setup, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_setup.return_value = (True, "Bootstrapped")
        ret = caddy_main(["--bootstrap", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(ret, 0)
        mock_setup.assert_called_once()

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    @patch("sandbox.caddy_deploy.validate_caddy")
    def test_cli_check_only(self, mock_val, mock_net, mock_check, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_check.return_value = (True, "running")
        mock_net.return_value = (True, "connected")
        mock_val.return_value = (True, "validated")

        ret = caddy_main(["--check-only", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(ret, 0)

    def test_cli_rejects_from_store_without_bootstrap(self):
        ret = caddy_main(["--from-store", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(ret, 1)

    @patch("sandbox.caddy_store.run_caddy_store_subcommand")
    def test_cli_dispatches_backup_and_restore_subcommands(self, mock_sub):
        mock_sub.return_value = 0
        self.assertEqual(caddy_main(["backup", "--profile", "prod"]), 0)
        mock_sub.assert_called_with("backup", ["--profile", "prod"])
        self.assertEqual(caddy_main(["restore", "--prune"]), 0)
        mock_sub.assert_called_with("restore", ["--prune"])

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_store._cli.restore_caddy_from_store")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    def test_cli_bootstrap_from_store_does_not_clobber_without_explicit_domain(
        self, mock_setup, mock_restore, mock_cfg
    ):
        mock_cfg.return_value = self.vps_config
        mock_restore.return_value = MagicMock(success=True, message="Restored")
        with patch.dict("os.environ", {"RESOURCE_PLANE_DOMAIN": "env.example.com"}):
            ret = caddy_main(["--bootstrap", "--from-store", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(ret, 0)
        mock_restore.assert_called_once()
        mock_setup.assert_not_called()

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    @patch("sandbox.caddy_store._cli.backup_caddy_to_store")
    def test_cli_domain_with_sync_triggers_backup(self, mock_backup, mock_setup, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_setup.return_value = (True, "Updated")
        mock_backup.return_value = MagicMock(success=True, message="Synced")
        ret = caddy_main([
            "--domain", "db.example.com", "--sync", "--profile", "prod",
            "--host", "1.2.3.4", "--key", str(self.dummy_key),
        ])
        self.assertEqual(ret, 0)
        mock_backup.assert_called_once_with(self.vps_config, profile="prod")


if __name__ == "__main__":
    unittest.main()
