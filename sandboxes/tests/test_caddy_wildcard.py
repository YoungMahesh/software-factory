"""Unit tests for Caddy wildcard DNS-01 ingress and /opt/caddy upgrade helpers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.caddy_deploy import main as caddy_main, setup_reverse_proxy
from sandbox.caddy_store import restore_caddy_from_store
from sandbox.caddy_wildcard import (
    check_caddy_has_cloudflare_module,
    ensure_wildcard_caddy,
    is_subdomain_of,
    normalize_base_domain,
    render_wildcard_site,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    sanitize_app_slug,
    sync_caddy_wildcard_runtime,
    validate_subdomain_label,
)
from sandbox.infra_deploy import VpsSshConfig


class TestCaddyWildcard(unittest.TestCase):
    """Tests for APPS_BASE_DOMAIN, Cloudflare DNS-01 token resolution, and wildcard Caddy setup."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.dummy_key = self.tmp_path / "vps_key"
        self.dummy_key.write_text("dummy", encoding="utf-8")
        self.dummy_key.chmod(0o600)
        self.vps_config = VpsSshConfig(host="1.2.3.4", key_path=self.dummy_key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_domain_and_slug_helpers(self):
        self.assertEqual(normalize_base_domain("https://SF.Mahesh0.dev/"), "sf.mahesh0.dev")
        self.assertEqual(normalize_base_domain("*.sf.mahesh0.dev"), "sf.mahesh0.dev")
        with self.assertRaises(ValueError):
            normalize_base_domain("localhost")

        self.assertEqual(sanitize_app_slug("My_Cool.App!"), "my-cool-app")
        self.assertEqual(validate_subdomain_label("Demo-1"), "demo-1")
        with self.assertRaises(ValueError):
            validate_subdomain_label("-bad")

        self.assertTrue(is_subdomain_of("app.sf.mahesh0.dev", "sf.mahesh0.dev"))
        self.assertTrue(is_subdomain_of("sf.mahesh0.dev", "sf.mahesh0.dev"))
        self.assertFalse(is_subdomain_of("db-host.mahesh0.dev", "sf.mahesh0.dev"))

    def test_resolve_env_and_token_precedence(self):
        with patch.dict(os.environ, {"APPS_BASE_DOMAIN": "env.mahesh0.dev"}, clear=True):
            self.assertEqual(resolve_apps_base_domain(None, dotenv={"APPS_BASE_DOMAIN": "dot.dev"}), "env.mahesh0.dev")
            self.assertEqual(resolve_apps_base_domain("arg.mahesh0.dev"), "arg.mahesh0.dev")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_apps_base_domain(None, dotenv={"APPS_BASE_DOMAIN": "dot.mahesh0.dev"}), "dot.mahesh0.dev")
            with self.assertRaises(ValueError):
                resolve_apps_base_domain()

        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "pages_or_dns"}, clear=True):
            self.assertEqual(resolve_cloudflare_dns_token(), "pages_or_dns")
            self.assertEqual(
                resolve_cloudflare_dns_token(dotenv={"CLOUDFLARE_DNS_API_TOKEN": "dns_specific"}),
                "dns_specific",
            )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                resolve_cloudflare_dns_token()

    def test_render_wildcard_site_uses_env_placeholder_and_apps_import(self):
        rendered = render_wildcard_site("sf.mahesh0.dev")
        self.assertIn("sf.mahesh0.dev, *.sf.mahesh0.dev {", rendered)
        self.assertIn("dns cloudflare {env.CLOUDFLARE_DNS_API_TOKEN}", rendered)
        self.assertIn("import /etc/caddy/apps/*.caddy", rendered)
        self.assertNotIn("cf_secret", rendered)

    @patch("sandbox.caddy_wildcard._ssh_run")
    def test_check_caddy_has_cloudflare_module(self, mock_ssh):
        mock_ssh.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.assertTrue(check_caddy_has_cloudflare_module(self.vps_config))
        mock_ssh.return_value = subprocess.CompletedProcess([], 1, "", "")
        self.assertFalse(check_caddy_has_cloudflare_module(self.vps_config))

    @patch("sandbox.caddy_wildcard.check_caddy_has_cloudflare_module")
    @patch("sandbox.caddy_wildcard._write_remote_b64")
    @patch("sandbox.caddy_wildcard._read_remote")
    @patch("sandbox.caddy_wildcard._ssh_run")
    def test_sync_caddy_wildcard_runtime_upgrades_when_module_missing(
        self, mock_ssh, mock_read, mock_write, mock_has_cf
    ):
        src_dir = self.tmp_path / "caddy"
        (src_dir / "conf").mkdir(parents=True)
        (src_dir / "Dockerfile").write_text("FROM caddy:2-alpine\n", encoding="utf-8")
        (src_dir / "docker-compose.yml").write_text("services:\n  caddy:\n    build: .\n", encoding="utf-8")

        mock_read.side_effect = [(True, ""), (True, ""), (True, "")]
        mock_write.return_value = (True, "ok")
        mock_has_cf.return_value = False
        mock_ssh.return_value = subprocess.CompletedProcess([], 0, "", "")

        ok, changed, msg = sync_caddy_wildcard_runtime(
            self.vps_config, "cf-token-123", source_dir=src_dir
        )
        self.assertTrue(ok)
        self.assertTrue(changed)
        self.assertIn("Upgraded", msg)
        env_writes = [c for c in mock_write.call_args_list if c.args[1] == "/opt/caddy/.env"]
        self.assertEqual(len(env_writes), 1)
        self.assertEqual(env_writes[0].kwargs["mode"], "0600")
        self.assertIn("docker compose up -d --build", mock_ssh.call_args_list[-1].args[1])

    @patch("sandbox.caddy_deploy.reload_caddy")
    @patch("sandbox.caddy_wildcard.write_and_validate_caddy_file")
    @patch("sandbox.caddy_wildcard.sync_caddy_wildcard_runtime")
    @patch("sandbox.caddy_wildcard._read_remote")
    @patch("sandbox.caddy_wildcard._ssh_run")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    def test_ensure_wildcard_caddy_upgrades_running_instance(
        self, mock_running, mock_net, mock_ssh, mock_read, mock_sync, mock_write_site, mock_reload
    ):
        mock_running.return_value = (True, "running")
        mock_net.return_value = (True, "connected")
        mock_read.return_value = (True, "{\n}\n\nimport /etc/caddy/sites/*.caddy\n")
        mock_sync.return_value = (True, True, "Upgraded")
        mock_write_site.return_value = (True, True, "Updated")
        mock_reload.return_value = (True, "Reloaded")

        ok, msg = ensure_wildcard_caddy(self.vps_config, "sf.mahesh0.dev", "tok")
        self.assertTrue(ok)
        self.assertIn("sf.mahesh0.dev, *.sf.mahesh0.dev", msg)
        mock_reload.assert_called_once()

    @patch("sandbox.caddy_deploy.ensure_wildcard_caddy")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    def test_setup_reverse_proxy_routes_subdomain_through_wildcard(self, mock_net, mock_wc):
        mock_wc.return_value = (True, "Wildcard ready.")
        mock_net.return_value = (True, "connected")
        with patch("sandbox.app_deploy._caddy.ensure_app_caddy_route", return_value=(True, "Routed")) as mock_app:
            ok, msg = setup_reverse_proxy(
                self.vps_config,
                domain="db.sf.mahesh0.dev",
                base_domain="sf.mahesh0.dev",
                cf_dns_token="cf-tok",
                wildcard=True,
            )
        self.assertTrue(ok)
        self.assertIn("Routed", msg)
        mock_app.assert_called_once()

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    def test_cli_wildcard_flag_passes_base_domain_and_token(self, mock_setup, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_setup.return_value = (True, "Wildcard configured")
        with patch.dict(
            os.environ,
            {"APPS_BASE_DOMAIN": "sf.mahesh0.dev", "CLOUDFLARE_DNS_API_TOKEN": "cf-tok"},
            clear=True,
        ):
            code = caddy_main(["--wildcard", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(code, 0)
        self.assertTrue(mock_setup.call_args.kwargs["wildcard"])
        self.assertEqual(mock_setup.call_args.kwargs["base_domain"], "sf.mahesh0.dev")
        self.assertEqual(mock_setup.call_args.kwargs["cf_dns_token"], "cf-tok")

    @patch("sandbox.caddy_store._sync.resolve_factory_root")
    @patch("sandbox.caddy_store._sync.ensure_caddy_store_repo")
    @patch("sandbox.caddy_store._sync.fetch_caddy_store_bundle")
    @patch("sandbox.caddy_store._sync.list_remote_docker_networks")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    @patch("sandbox.caddy_deploy.check_ports_available")
    @patch("sandbox.caddy_deploy.ensure_docker_network")
    @patch("sandbox.caddy_deploy.validate_caddy")
    @patch("subprocess.run")
    def test_caddy_store_bootstrap_includes_build_and_env_for_wildcard(
        self, mock_subproc, mock_val, mock_net, mock_ports, mock_running, mock_nets, mock_bundle, mock_ensure, mock_root
    ):
        mock_root.return_value = self.tmp_path
        mock_bundle.return_value = {
            "conf/Caddyfile": "{\n}\n\nimport /etc/caddy/sites/*.caddy\n",
            "conf/sites/apps-wildcard.caddy": render_wildcard_site("sf.mahesh0.dev"),
        }
        mock_running.return_value = (False, "not running")
        mock_nets.return_value = {"dbhost-network"}
        mock_ports.return_value = (True, "free")
        mock_net.return_value = (True, "ok")
        mock_val.return_value = (True, "valid")
        mock_subproc.return_value = subprocess.CompletedProcess([], 0, b"", b"")

        with patch.dict(os.environ, {"CLOUDFLARE_DNS_API_TOKEN": "cf-secret-token"}, clear=True):
            res = restore_caddy_from_store(self.vps_config, org_name="sFactory0", gh_token="tok", bootstrap=True)

        self.assertTrue(res.success)
        up_cmd = mock_subproc.call_args_list[-1].args[0][-1]
        self.assertIn("docker compose up -d --build", up_cmd)


if __name__ == "__main__":
    unittest.main()
