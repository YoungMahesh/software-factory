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
    ensure_wildcard_caddy,
    extract_dashboard_upstream,
    is_subdomain_of,
    lookup_control_plane_web_url,
    normalize_base_domain,
    normalize_dashboard_upstream,
    render_wildcard_site,
    resolve_apps_base_domain,
    resolve_cloudflare_dns_token,
    resolve_dashboard_upstream,
    resolve_wildcard_dashboard_upstream,
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
        self.assertEqual(normalize_base_domain("https://Apps.Example.com/"), "apps.example.com")
        self.assertEqual(normalize_base_domain("*.apps.example.com"), "apps.example.com")
        with self.assertRaises(ValueError):
            normalize_base_domain("localhost")

        self.assertEqual(sanitize_app_slug("My_Cool.App!"), "my-cool-app")
        self.assertEqual(validate_subdomain_label("Demo-1"), "demo-1")
        with self.assertRaises(ValueError):
            validate_subdomain_label("-bad")

        self.assertTrue(is_subdomain_of("app.apps.example.com", "apps.example.com"))
        self.assertTrue(is_subdomain_of("apps.example.com", "apps.example.com"))
        self.assertFalse(is_subdomain_of("db-host.example.com", "apps.example.com"))

    def test_resolve_env_and_token_precedence(self):
        with patch.dict(os.environ, {"APPS_BASE_DOMAIN": "env.example.com"}, clear=True):
            self.assertEqual(resolve_apps_base_domain(None, dotenv={"APPS_BASE_DOMAIN": "dot.dev"}), "env.example.com")
            self.assertEqual(resolve_apps_base_domain("arg.example.com"), "arg.example.com")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_apps_base_domain(None, dotenv={"APPS_BASE_DOMAIN": "dot.example.com"}), "dot.example.com")
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
        rendered = render_wildcard_site("apps.example.com")
        self.assertIn("apps.example.com, *.apps.example.com {", rendered)
        self.assertIn("dns cloudflare {env.CLOUDFLARE_DNS_API_TOKEN}", rendered)
        self.assertIn("import /etc/caddy/apps/*.caddy", rendered)
        self.assertNotIn("@sandbox_dashboard", rendered)
        self.assertNotIn("cf_secret", rendered)

    def test_render_wildcard_site_with_dashboard_upstream_and_loop_guard(self):
        upstream = "https://ws--sandbox-control-plane-fastapi-app.modal.run"
        rendered = render_wildcard_site("apps.example.com", dashboard_upstream=upstream)
        self.assertIn("apps.example.com, *.apps.example.com {", rendered)
        self.assertIn("@sandbox_dashboard host apps.example.com", rendered)
        self.assertIn(f"reverse_proxy {upstream} {{", rendered)
        self.assertIn("header_up Host {upstream_hostport}", rendered)
        self.assertIn("flush_interval -1", rendered)
        self.assertEqual(extract_dashboard_upstream(rendered), upstream)

        with self.assertRaises(ValueError):
            normalize_dashboard_upstream("https://apps.example.com", base_domain="apps.example.com")
        with self.assertRaises(ValueError):
            normalize_dashboard_upstream("https://sub.apps.example.com", base_domain="apps.example.com")
        with self.assertRaises(ValueError):
            normalize_dashboard_upstream("https://ws.modal.run/path", base_domain="apps.example.com")

    def test_resolve_dashboard_upstream_precedence_and_sdk_lookup(self):
        modal_url = "https://ws--sandbox-control-plane-fastapi-app.modal.run"
        with patch.dict(os.environ, {"SANDBOX_DASHBOARD_UPSTREAM": "env.modal.run"}, clear=True):
            up, err = resolve_dashboard_upstream(
                "https://arg.modal.run/", base_domain="apps.example.com", lookup_fn=lambda: modal_url
            )
            self.assertEqual(up, "https://arg.modal.run")
            self.assertIsNone(err)

            up_env, _ = resolve_dashboard_upstream(None, base_domain="apps.example.com", lookup_fn=lambda: modal_url)
            self.assertEqual(up_env, "https://env.modal.run")

        with patch.dict(os.environ, {"MODAL_SANDBOX_ENDPOINT_URL": "https://apps.example.com"}, clear=True):
            up_sdk, err_sdk = resolve_dashboard_upstream(
                None, base_domain="apps.example.com", lookup_fn=lambda: modal_url
            )
            self.assertEqual(up_sdk, modal_url)
            self.assertIsNone(err_sdk)

            # Never loop back to MODAL_SANDBOX_ENDPOINT_URL when it equals base_domain
            up_none, err_none = resolve_dashboard_upstream(
                None, base_domain="apps.example.com", lookup_fn=lambda: (_ for _ in ()).throw(RuntimeError("not deployed"))
            )
            self.assertIsNone(up_none)
            self.assertIn("not deployed", err_none)

    @patch("modal.Function.from_name")
    @patch("sandbox.caddy_wildcard.get_client_for_profile")
    @patch("sandbox.profiles.load_profiles_config", return_value={"work": {"environment": "prod", "active": True}})
    @patch("sandbox.profiles.get_active_profile_name", return_value="work")
    def test_lookup_control_plane_web_url_uses_active_profile(self, _act, _profs, mock_client, mock_from_name):
        mock_from_name.return_value.get_web_url.return_value = "https://work--sandbox-control-plane-fastapi-app.modal.run"
        url = lookup_control_plane_web_url(dotenv={"MODAL_TOKENS": "[]"})
        self.assertEqual(url, "https://work--sandbox-control-plane-fastapi-app.modal.run")
        mock_from_name.assert_called_once_with(
            "sandbox-control-plane", "fastapi_app", environment_name="prod", client=mock_client.return_value,
        )

    @patch("sandbox.caddy_wildcard._ssh_run")
    def test_check_caddy_has_cloudflare_module(self, mock_ssh):
        mock_ssh.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.assertTrue(check_caddy_has_cloudflare_module(self.vps_config))
        mock_ssh.return_value = subprocess.CompletedProcess([], 1, "", "")
        self.assertFalse(check_caddy_has_cloudflare_module(self.vps_config))

    @patch("sandbox.caddy_deploy.resolve_wildcard_dashboard_upstream", return_value=(True, "https://ws.modal.run", "Routed"))
    @patch("sandbox.caddy_deploy.ensure_wildcard_caddy")
    @patch("sandbox.caddy_deploy.ensure_caddy_network")
    def test_setup_reverse_proxy_routes_subdomain_through_wildcard_and_syncs_env(self, mock_net, mock_wc, _mock_dash):
        mock_wc.return_value = (True, "Wildcard ready.")
        mock_net.return_value = (True, "connected")
        env_file = self.tmp_path / ".env"
        env_file.write_text("APPS_BASE_DOMAIN=apps.example.com\nMODAL_SANDBOX_ENDPOINT_URL=\n", encoding="utf-8")
        with patch("sandbox.app_deploy._caddy.ensure_app_caddy_route", return_value=(True, "Routed")) as mock_app:
            ok, msg = setup_reverse_proxy(
                self.vps_config,
                domain="db.apps.example.com",
                base_domain="apps.example.com",
                cf_dns_token="cf-tok",
                wildcard=True,
                env_file_path=env_file,
            )
        self.assertTrue(ok)
        self.assertIn("Routed", msg)
        mock_wc.assert_called_once()
        self.assertEqual(mock_wc.call_args.kwargs["dashboard_upstream"], "https://ws.modal.run")
        self.assertIn('MODAL_SANDBOX_ENDPOINT_URL="https://apps.example.com"', env_file.read_text(encoding="utf-8"))
        mock_app.assert_called_once()

    @patch("sandbox.caddy_wildcard.prepare_runtime")
    @patch("sandbox.caddy_wildcard._read_remote")
    def test_ensure_wildcard_caddy_preserves_existing_dashboard_when_requested(self, mock_read, mock_prep):
        mock_read.return_value = (True, render_wildcard_site("apps.example.com", dashboard_upstream="https://kept.modal.run"))
        mock_prep.return_value = type("Res", (), {"success": True, "message": "ok"})()
        ok, _ = ensure_wildcard_caddy(
            self.vps_config, "apps.example.com", "cf-tok", dashboard_upstream=None, preserve_dashboard=True
        )
        self.assertTrue(ok)
        written = mock_prep.call_args.kwargs["files"]["conf/sites/apps-wildcard.caddy"]
        self.assertIn("https://kept.modal.run", written)

    def test_resolve_wildcard_dashboard_upstream_modes(self):
        ok_off, up_off, msg_off = resolve_wildcard_dashboard_upstream("apps.example.com", no_dashboard=True)
        self.assertTrue(ok_off)
        self.assertIsNone(up_off)
        self.assertIn("--no-dashboard", msg_off)

        ok_req, up_req, msg_req = resolve_wildcard_dashboard_upstream(
            "apps.example.com", require_dashboard=True, lookup_fn=lambda: None
        )
        self.assertFalse(ok_req)
        self.assertIsNone(up_req)
        self.assertIn("no web URL", msg_req)

    @patch("sandbox.caddy_deploy.resolve_vps_ssh_config")
    @patch("sandbox.caddy_deploy.setup_reverse_proxy")
    def test_cli_wildcard_flag_passes_base_domain_and_token(self, mock_setup, mock_cfg):
        mock_cfg.return_value = self.vps_config
        mock_setup.return_value = (True, "Wildcard configured")
        with patch.dict(
            os.environ,
            {"APPS_BASE_DOMAIN": "apps.example.com", "CLOUDFLARE_DNS_API_TOKEN": "cf-tok"},
            clear=True,
        ):
            code = caddy_main(["--wildcard", "--dashboard", "--dashboard-upstream", "https://cp.modal.run", "--no-sync-env", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(code, 0)
        self.assertTrue(mock_setup.call_args.kwargs["wildcard"])
        self.assertTrue(mock_setup.call_args.kwargs["dashboard"])
        self.assertEqual(mock_setup.call_args.kwargs["dashboard_upstream"], "https://cp.modal.run")
        self.assertIsNone(mock_setup.call_args.kwargs["env_file_path"])
        self.assertEqual(mock_setup.call_args.kwargs["base_domain"], "apps.example.com")
        self.assertEqual(mock_setup.call_args.kwargs["cf_dns_token"], "cf-tok")

        code_bad = caddy_main(["--dashboard", "--no-dashboard", "--host", "1.2.3.4", "--key", str(self.dummy_key)])
        self.assertEqual(code_bad, 1)


if __name__ == "__main__":
    unittest.main()
