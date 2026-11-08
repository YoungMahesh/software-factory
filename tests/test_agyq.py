"""Unit tests for Antigravity Gemini Quota checker (scripts/agyq)."""

import datetime
import importlib.machinery
import importlib.util
from pathlib import Path
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
        import json
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
        import json
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


if __name__ == "__main__":
    unittest.main()
