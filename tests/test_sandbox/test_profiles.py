"""Unit tests for Modal multi-profile discovery and client resolution."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.profiles import (
    clear_client_cache,
    get_active_profile_name,
    get_all_clients,
    get_available_profiles,
    get_client_for_profile,
    get_profile_credentials,
    load_profiles_config,
    parse_modal_tokens_data,
    parse_modal_tokens_env,
)


class TestProfiles(unittest.TestCase):
    def setUp(self):
        clear_client_cache()

    def tearDown(self):
        clear_client_cache()

    def test_load_profiles_config(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[prof1]
token_id = "ak-111"
token_secret = "as-111"
environment = "main"

[prof2]
token_id = "ak-222"
token_secret = "as-222"
active = true
environment = "dev"

[empty_prof]
foo = "bar"
""",
                encoding="utf-8",
            )

            profiles = load_profiles_config(toml_path)
            self.assertIn("prof1", profiles)
            self.assertIn("prof2", profiles)
            self.assertNotIn("empty_prof", profiles)
            self.assertEqual(profiles["prof1"]["token_id"], "ak-111")
            self.assertEqual(profiles["prof2"]["active"], True)

    def test_get_active_profile_name(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[alpha]
token_id = "ak-1"
token_secret = "as-1"

[beta]
token_id = "ak-2"
token_secret = "as-2"
active = true
""",
                encoding="utf-8",
            )
            # Should detect active = true
            self.assertEqual(get_active_profile_name(toml_path), "beta")

            # Environment override should take precedence
            with patch.dict(os.environ, {"MODAL_PROFILE": "alpha"}):
                self.assertEqual(get_active_profile_name(toml_path), "alpha")

    def test_get_available_profiles_does_not_leak_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[prof_secret]
token_id = "ak-secret"
token_secret = "as-super-secret"
environment = "prod"
active = true
""",
                encoding="utf-8",
            )
            profiles = get_available_profiles(toml_path)
            self.assertEqual(len(profiles), 1)
            prof = profiles[0]
            self.assertEqual(prof["name"], "prof_secret")
            self.assertTrue(prof["active"])
            self.assertEqual(prof["environment"], "prod")
            self.assertNotIn("token_id", prof)
            self.assertNotIn("token_secret", prof)

    def test_get_profile_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[user1]
token_id = "ak-123"
token_secret = "as-456"
active = true
""",
                encoding="utf-8",
            )
            creds = get_profile_credentials("user1", toml_path)
            self.assertEqual(creds, {"token_id": "ak-123", "token_secret": "as-456"})

            missing = get_profile_credentials("nonexistent", toml_path)
            self.assertIsNone(missing)

    @patch("modal.Client.from_credentials")
    def test_get_client_for_profile_with_credentials(self, mock_from_credentials):
        mock_client = MagicMock()
        mock_from_credentials.return_value = mock_client

        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[team_a]
token_id = "ak-team"
token_secret = "as-team"
active = true
""",
                encoding="utf-8",
            )
            client = get_client_for_profile("team_a", toml_path)
            self.assertEqual(client, mock_client)
            mock_from_credentials.assert_called_once_with("ak-team", "as-team")

            # Cache check - should not call from_credentials a second time
            client2 = get_client_for_profile("team_a", toml_path)
            self.assertEqual(client2, mock_client)
            self.assertEqual(mock_from_credentials.call_count, 1)

    @patch("modal.Client.from_credentials")
    def test_get_all_clients(self, mock_from_credentials):
        mock_from_credentials.side_effect = lambda tid, tsec: MagicMock(id=tid)

        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / ".modal.toml"
            toml_path.write_text(
                """
[p1]
token_id = "ak-1"
token_secret = "as-1"

[p2]
token_id = "ak-2"
token_secret = "as-2"
""",
                encoding="utf-8",
            )
            all_clients = get_all_clients(toml_path, use_cache=False)
            self.assertIn("p1", all_clients)
            self.assertIn("p2", all_clients)
            self.assertEqual(mock_from_credentials.call_count, 2)

    def test_parse_modal_tokens_data(self):
        raw = json.dumps([
            {"name": "Work Account", "token_id": "ak-work", "token_secret": "as-work", "environment": "main"},
            {"name": "Personal", "token_id": "ak-pers", "token_secret": "as-pers", "active": True},
            {"name": "Invalid", "token_id": "ak-inv"},  # missing token_secret
            "not a dict",
        ])
        profiles = parse_modal_tokens_data(raw)
        self.assertIn("work-account", profiles)
        self.assertEqual(profiles["work-account"]["token_id"], "ak-work")
        self.assertEqual(profiles["work-account"]["token_secret"], "as-work")
        self.assertEqual(profiles["work-account"]["environment"], "main")

        self.assertIn("personal", profiles)
        self.assertEqual(profiles["personal"]["token_id"], "ak-pers")
        self.assertEqual(profiles["personal"]["active"], True)

        self.assertNotIn("invalid", profiles)
        self.assertEqual(parse_modal_tokens_data(""), {})
        self.assertEqual(parse_modal_tokens_data("invalid json {"), {})
        self.assertEqual(parse_modal_tokens_data({"not": "a list"}), {})

    def test_load_profiles_config_with_modal_tokens(self):
        tokens_json = json.dumps([
            {"name": "prod", "token_id": "ak-prod", "token_secret": "as-prod"},
            {"name": "dev", "token_id": "ak-dev", "token_secret": "as-dev", "active": True},
        ])
        with patch.dict(os.environ, {"MODAL_TOKENS": tokens_json}):
            profiles = load_profiles_config()
            self.assertIn("prod", profiles)
            self.assertIn("dev", profiles)
            self.assertEqual(profiles["dev"]["active"], True)
            self.assertEqual(get_active_profile_name(), "dev")

            available = get_available_profiles()
            self.assertEqual(len(available), 2)
            names = [p["name"] for p in available]
            self.assertIn("prod", names)
            self.assertIn("dev", names)
            dev_prof = next(p for p in available if p["name"] == "dev")
            self.assertTrue(dev_prof["active"])
            self.assertNotIn("token_id", dev_prof)

            creds = get_profile_credentials("prod")
            self.assertEqual(creds, {"token_id": "ak-prod", "token_secret": "as-prod"})
