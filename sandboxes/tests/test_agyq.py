"""Unit tests for Antigravity Gemini Quota checker (scripts/agyq)."""

import datetime
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

AGYQ_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agyq"
loader = importlib.machinery.SourceFileLoader("agyq", str(AGYQ_PATH))
spec = importlib.util.spec_from_loader("agyq", loader)
agyq = importlib.util.module_from_spec(spec)
loader.exec_module(agyq)


class TestAgyqFormatters(unittest.TestCase):
    def test_format_time_remaining_ready(self):
        # A time in the past should report "ready to reset"
        past_time = "2020-01-01T00:00:00Z"
        self.assertEqual(agyq.format_time_remaining(past_time), "ready to reset")

    def test_format_time_remaining_empty_or_invalid(self):
        self.assertEqual(agyq.format_time_remaining(""), "N/A")
        self.assertEqual(agyq.format_time_remaining(None), "N/A")
        self.assertEqual(agyq.format_time_remaining("invalid-date"), "N/A")

    def test_format_time_remaining_future(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        # 45 minutes in future (with buffer for microsecond elapsed time)
        in_45m = (now + datetime.timedelta(minutes=45, seconds=5)).isoformat()
        self.assertEqual(agyq.format_time_remaining(in_45m), "45m")

        # 2 hours 15 minutes in future
        in_2h15m = (now + datetime.timedelta(hours=2, minutes=15, seconds=5)).isoformat()
        self.assertEqual(agyq.format_time_remaining(in_2h15m), "2h 15m")

        # 3 days 5 hours in future
        in_3d5h = (now + datetime.timedelta(days=3, hours=5, seconds=5)).isoformat()
        self.assertEqual(agyq.format_time_remaining(in_3d5h), "3d 5h")

    def test_format_reset_time(self):
        iso_str = "2026-11-08T12:13:08Z"
        formatted = agyq.format_reset_time(iso_str)
        self.assertEqual(formatted, "2026-11-08 12:13:08 UTC")


class TestAgyqQuotaExtraction(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_get_gemini_quota_with_summary(self, mock_urlopen):
        mock_token_resp = MagicMock()
        mock_token_resp.read.return_value = b'{"access_token": "dummy_tok"}'
        mock_token_resp.__enter__.return_value = mock_token_resp

        mock_summary_resp = MagicMock()
        mock_summary_data = {
            "groups": [
                {
                    "displayName": "Gemini Models",
                    "buckets": [
                        {
                            "bucketId": "gemini-weekly",
                            "displayName": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remainingFraction": 0.84,
                            "resetTime": "2026-11-14T03:00:00Z",
                            "description": "Weekly reset in 5 days",
                        },
                        {
                            "bucketId": "gemini-5h",
                            "displayName": "Five Hour Limit Remaining",
                            "window": "5h",
                            "remainingFraction": 0.88,
                            "resetTime": "2026-11-08T12:13:08Z",
                            "description": "5-hour reset in 1 hour 30m",
                        },
                    ],
                }
            ]
        }
        mock_summary_resp.read.return_value = json.dumps(mock_summary_data).encode("utf-8")
        mock_summary_resp.__enter__.return_value = mock_summary_resp

        mock_urlopen.side_effect = [mock_token_resp, mock_summary_resp]

        token_dict = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
        }
        res = agyq.get_gemini_quota(token_dict)
        self.assertEqual(res["modelName"], "Gemini Pool")
        self.assertAlmostEqual(res["remainingPercent"], 88.0)
        self.assertAlmostEqual(res["usedPercent"], 12.0)
        self.assertEqual(res["resetTime"], "2026-11-08T12:13:08Z")
        self.assertAlmostEqual(res["weeklyRemainingPercent"], 84.0)
        self.assertAlmostEqual(res["weeklyUsedPercent"], 16.0)

    @patch("urllib.request.urlopen")
    def test_get_gemini_quota_fallback_to_models(self, mock_urlopen):
        mock_token_resp = MagicMock()
        mock_token_resp.read.return_value = b'{"access_token": "dummy_tok"}'
        mock_token_resp.__enter__.return_value = mock_token_resp

        # 2 summary calls fail (daily and prod)
        import urllib.error
        mock_err = urllib.error.URLError("Failed")

        mock_models_resp = MagicMock()
        mock_models_data = {
            "models": {
                "gemini-3.8-flash-tiered": {
                    "displayName": "Gemini 3.8 Flash Tiered",
                    "modelProvider": "MODEL_PROVIDER_GOOGLE",
                    "quotaInfo": {
                        "remainingFraction": 1.0,
                        "resetTime": "2026-11-08T15:00:00Z",
                    },
                }
            }
        }
        mock_models_resp.read.return_value = json.dumps(mock_models_data).encode("utf-8")
        mock_models_resp.__enter__.return_value = mock_models_resp

        mock_urlopen.side_effect = [mock_token_resp, mock_err, mock_err, mock_models_resp]

        token_dict = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
        }
        res = agyq.get_gemini_quota(token_dict)
        self.assertEqual(res["modelName"], "Gemini 3.8 Flash Tiered")
        self.assertEqual(res["remainingPercent"], 100.0)
        self.assertEqual(res["usedPercent"], 0.0)


class TestAgyqTokenResolution(unittest.TestCase):
    def test_resolve_t3_instance_id_dynamic_settings(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            settings_data = {
                "providerInstances": {
                    "antigravity": {
                        "driver": "antigravity",
                        "displayName": "ANV",
                        "enabled": True,
                    },
                    "antigravity-mgh": {
                        "driver": "antigravity",
                        "displayName": "MGH",
                        "enabled": True,
                    },
                    "antigravity-m47": {
                        "driver": "antigravity",
                        "displayName": "M47",
                        "enabled": True,
                    },
                }
            }
            json.dump(settings_data, tf)
            tf.flush()
            tmp_path = tf.name

        try:
            self.assertEqual(agyq.resolve_t3_instance_id("m47", settings_path=tmp_path), "antigravity-m47")
            self.assertEqual(agyq.resolve_t3_instance_id("anv", settings_path=tmp_path), "antigravity")
            self.assertEqual(agyq.resolve_t3_instance_id("mgh", settings_path=tmp_path), "antigravity-mgh")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_resolve_t3_instance_id_classic_settings(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            settings_data = {
                "providerInstances": {
                    "antigravity": {
                        "driver": "antigravity",
                        "displayName": "Antigravity",
                        "enabled": True,
                    },
                    "antigravity-anv": {
                        "driver": "antigravity",
                        "displayName": "Antigravity (ANV)",
                        "enabled": True,
                    },
                    "antigravity-mgh": {
                        "driver": "antigravity",
                        "displayName": "Antigravity (MGH)",
                        "enabled": True,
                    },
                }
            }
            json.dump(settings_data, tf)
            tf.flush()
            tmp_path = tf.name

        try:
            self.assertEqual(agyq.resolve_t3_instance_id("m47", settings_path=tmp_path), "antigravity")
            self.assertEqual(agyq.resolve_t3_instance_id("anv", settings_path=tmp_path), "antigravity-anv")
            self.assertEqual(agyq.resolve_t3_instance_id("mgh", settings_path=tmp_path), "antigravity-mgh")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_resolve_account_token_distinct_profiles(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock T3 structure
            settings_path = os.path.join(tmp_dir, "settings.json")
            settings_data = {
                "providerInstances": {
                    "antigravity": {
                        "driver": "antigravity",
                        "displayName": "ANV",
                        "enabled": True,
                    },
                    "antigravity-m47": {
                        "driver": "antigravity",
                        "displayName": "M47",
                        "enabled": True,
                    },
                }
            }
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f)

            # Instance hashes
            anv_hash = hashlib.sha256(b"antigravity").hexdigest()
            m47_hash = hashlib.sha256(b"antigravity-m47").hexdigest()

            anv_dir = os.path.join(tmp_dir, anv_hash, "antigravity-acp")
            m47_dir = os.path.join(tmp_dir, m47_hash, "antigravity-acp")
            os.makedirs(anv_dir, exist_ok=True)
            os.makedirs(m47_dir, exist_ok=True)

            with open(os.path.join(anv_dir, "acp_token.json"), "w", encoding="utf-8") as f:
                json.dump({"client_id": "cid-anv", "refresh_token": "rt-anv"}, f)

            with open(os.path.join(m47_dir, "acp_token.json"), "w", encoding="utf-8") as f:
                json.dump({"client_id": "cid-m47", "refresh_token": "rt-m47"}, f)

            # Patch ~/.t3/userdata/providers/antigravity to point to tmp_dir
            def mock_expanduser(path):
                if "~/.t3/userdata/providers/antigravity" in path:
                    sub = path.split("~/.t3/userdata/providers/antigravity/")[1]
                    return os.path.join(tmp_dir, sub)
                return os.path.expanduser(path)

            with patch("os.path.expanduser", side_effect=mock_expanduser):
                token_m47, err_m47 = agyq.resolve_account_token("m47", settings_path=settings_path)
                token_anv, err_anv = agyq.resolve_account_token("anv", settings_path=settings_path)

                self.assertIsNone(err_m47)
                self.assertIsNone(err_anv)
                self.assertEqual(token_m47["refresh_token"], "rt-m47")
                self.assertEqual(token_anv["refresh_token"], "rt-anv")
                self.assertNotEqual(token_m47["refresh_token"], token_anv["refresh_token"])


if __name__ == "__main__":
    unittest.main()
