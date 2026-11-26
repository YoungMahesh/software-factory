"""Unit tests for per-sandbox Modal cost estimation, caching, and fallback logic."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from sandbox.costs import (
    SandboxCostEntry,
    clear_sandbox_cost_cache,
    fetch_sandbox_cost,
    get_sandbox_costs,
)
from sandbox.lifecycle import clear_sandbox_metadata_cache


class TestSandboxCosts(unittest.TestCase):
    def setUp(self):
        clear_sandbox_cost_cache()
        clear_sandbox_metadata_cache()

    def tearDown(self):
        clear_sandbox_cost_cache()
        clear_sandbox_metadata_cache()

    def test_fetch_sandbox_cost_experimental_stats_success(self):
        sb = MagicMock()
        sb.object_id = "sb-123"
        stats = MagicMock()
        stats.cost = Decimal("0.92942300")
        stats.cost_by_resource = {
            "CPU": Decimal("0.30914163"),
            "Memory": Decimal("0.62028137"),
        }
        stats.duration = timedelta(hours=2, minutes=15)
        stats.billed_cpu_core_seconds = 1234.5
        stats.billed_memory_gib_seconds = 9876.5
        stats.since = datetime(2026, 11, 26, 3, 11, 39, tzinfo=timezone.utc)
        stats.until = datetime(2026, 11, 26, 5, 26, 39, tzinfo=timezone.utc)
        sb._experimental_stats.return_value = stats

        entry = fetch_sandbox_cost(sb, MagicMock(), "maheshghamand")
        self.assertEqual(entry.sandbox_id, "sb-123")
        self.assertEqual(entry.profile, "maheshghamand")
        self.assertAlmostEqual(entry.cost_usd, 0.929423)
        self.assertEqual(
            entry.cost_by_resource_usd,
            {"CPU": 0.30914163, "Memory": 0.62028137},
        )
        self.assertEqual(entry.duration_seconds, 8100.0)
        self.assertEqual(entry.billed_cpu_core_seconds, 1234.5)
        self.assertEqual(entry.billed_memory_gib_seconds, 9876.5)
        self.assertEqual(entry.source, "sandbox_stats")
        self.assertFalse(entry.cached)
        self.assertIsNone(entry.error)

    def test_fetch_sandbox_cost_pending_usage_returns_none(self):
        sb = MagicMock()
        sb.object_id = "sb-new"
        stats = MagicMock()
        stats.cost = None
        stats.cost_by_resource = {}
        stats.duration = timedelta(seconds=5)
        stats.billed_cpu_core_seconds = 0.0
        stats.billed_memory_gib_seconds = 0.0
        stats.since = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
        stats.until = datetime(2026, 11, 26, 10, 0, 5, tzinfo=timezone.utc)
        sb._experimental_stats.return_value = stats

        entry = fetch_sandbox_cost(sb, MagicMock(), "default")
        self.assertIsNone(entry.cost_usd)
        self.assertEqual(entry.cost_by_resource_usd, {})
        self.assertEqual(entry.source, "sandbox_stats")
        self.assertIsNone(entry.error)

    @patch("sandbox.costs.modal.App.lookup")
    def test_fetch_sandbox_cost_fallback_to_app_stats(self, mock_app_lookup):
        sb = MagicMock()
        sb.object_id = "sb-persistent"
        sb._experimental_stats.side_effect = NotImplementedError("not supported")
        created = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        sb.get_tags.return_value = {
            "app_name": "software-factory",
            "created_at": created,
            "instance_name": "software-factory-abc",
        }

        group = MagicMock()
        group.cost = Decimal("0.45")
        group.cost_by_resource = {"CPU": Decimal("0.15"), "Memory": Decimal("0.30")}
        mock_app = MagicMock()
        mock_app.sandboxes.stats.return_value = [group]
        mock_app_lookup.return_value = mock_app

        client = MagicMock()
        entry = fetch_sandbox_cost(sb, client, "team-a")
        self.assertEqual(entry.source, "app_stats")
        self.assertAlmostEqual(entry.cost_usd, 0.45)
        self.assertEqual(entry.cost_by_resource_usd, {"CPU": 0.15, "Memory": 0.30})
        self.assertIsNone(entry.error)
        mock_app_lookup.assert_called_once_with("software-factory", client=client)

    def test_fetch_sandbox_cost_fallback_missing_tags(self):
        sb = MagicMock()
        sb.object_id = "sb-untagged"
        sb._experimental_stats.side_effect = AttributeError("missing method")
        sb.get_tags.return_value = {}

        entry = fetch_sandbox_cost(sb, MagicMock(), "default")
        self.assertEqual(entry.source, "unavailable")
        self.assertIsNone(entry.cost_usd)
        self.assertIn("tags", entry.error or "")

    def test_fetch_sandbox_cost_handles_rpc_exception(self):
        sb = MagicMock()
        sb.object_id = "sb-err"
        sb._experimental_stats.side_effect = RuntimeError("Modal timeout")

        entry = fetch_sandbox_cost(sb, MagicMock(), "default")
        self.assertEqual(entry.source, "unavailable")
        self.assertIsNone(entry.cost_usd)
        self.assertEqual(entry.error, "Modal timeout")

    @patch("sandbox.costs.modal.Sandbox.list")
    @patch("sandbox.costs.get_all_clients")
    def test_get_sandbox_costs_caching_refresh_and_clear(self, mock_all_clients, mock_list):
        client = MagicMock()
        mock_all_clients.return_value = {"prof-a": client}

        sb = MagicMock()
        sb.object_id = "sb-cached"
        stats = MagicMock()
        stats.cost = Decimal("1.25")
        stats.cost_by_resource = {"CPU": Decimal("0.50"), "Memory": Decimal("0.75")}
        stats.duration = timedelta(hours=1)
        stats.billed_cpu_core_seconds = 100.0
        stats.billed_memory_gib_seconds = 200.0
        stats.since = datetime(2026, 11, 26, 9, 0, 0, tzinfo=timezone.utc)
        stats.until = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
        sb._experimental_stats.return_value = stats
        mock_list.return_value = [sb]

        res1 = get_sandbox_costs(profile="all", ttl_seconds=60.0)
        self.assertIn("sb-cached", res1.costs)
        self.assertFalse(res1.costs["sb-cached"].cached)
        self.assertEqual(sb._experimental_stats.call_count, 1)

        # Second call within TTL hits cache
        res2 = get_sandbox_costs(profile="all", ttl_seconds=60.0)
        self.assertTrue(res2.costs["sb-cached"].cached)
        self.assertEqual(sb._experimental_stats.call_count, 1)

        # refresh=True bypasses cache
        res3 = get_sandbox_costs(profile="all", refresh=True, ttl_seconds=60.0)
        self.assertFalse(res3.costs["sb-cached"].cached)
        self.assertEqual(sb._experimental_stats.call_count, 2)

        # Clearing metadata cache also clears cost cache
        clear_sandbox_metadata_cache("sb-cached")
        res4 = get_sandbox_costs(profile="all", ttl_seconds=60.0)
        self.assertFalse(res4.costs["sb-cached"].cached)
        self.assertEqual(sb._experimental_stats.call_count, 3)

    @patch("sandbox.costs.modal.Sandbox.list")
    @patch("sandbox.costs.get_all_clients")
    def test_errors_are_not_cached_and_sandbox_ids_filter_applies(self, mock_all_clients, mock_list):
        client = MagicMock()
        mock_all_clients.return_value = {"prof-a": client}

        sb_bad = MagicMock()
        sb_bad.object_id = "sb-bad"
        sb_bad._experimental_stats.side_effect = RuntimeError("transient error")

        sb_other = MagicMock()
        sb_other.object_id = "sb-other"
        mock_list.return_value = [sb_bad, sb_other]

        res = get_sandbox_costs(profile="all", sandbox_ids=["sb-bad"])
        self.assertEqual(set(res.costs.keys()), {"sb-bad"})
        self.assertEqual(res.costs["sb-bad"].error, "transient error")
        sb_other._experimental_stats.assert_not_called()

        # Error was not cached, so next call retries
        res2 = get_sandbox_costs(profile="all", sandbox_ids=["sb-bad"])
        self.assertEqual(sb_bad._experimental_stats.call_count, 2)
        self.assertIsInstance(res2.costs["sb-bad"], SandboxCostEntry)


if __name__ == "__main__":
    unittest.main()
