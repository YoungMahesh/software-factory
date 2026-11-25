"""Unit tests for Caddy wildcard DNS-01 ingress and /opt/caddy upgrade helpers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sandbox.caddy_deploy import main as caddy_main, setup_reverse_proxy
from sandbox.caddy_wildcard import (
    check_caddy_has_cloudflare_module,
    is_subdomain_of,
    normalize_base_domain,
    render_wildcard_site,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    sanitize_app_slug,
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


if __name__ == "__main__":
    unittest.main()
