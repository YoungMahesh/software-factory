"""API route tests for GET /api/sandboxes/costs and termination cache cleanup."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox.costs import SandboxCostEntry, SandboxCostsResponse, clear_sandbox_cost_cache
from sandbox.lifecycle import clear_sandbox_metadata_cache, terminate_sandbox
from sandbox.web import app


class TestWebSandboxCostsAPI(unittest.TestCase):
    def setUp(self):
        clear_sandbox_cost_cache()
        clear_sandbox_metadata_cache()
        self.env_patcher = patch.dict(
            os.environ,
            {
                "WEB_UI_USERNAME": "testadmin",
                "WEB_UI_PASSWORD": "testpassword",
            },
        )
        self.env_patcher.start()
        auth_bytes = base64.b64encode(b"testadmin:testpassword").decode("utf-8")
        self.client = TestClient(app, headers={"Authorization": f"Basic {auth_bytes}"})

    def tearDown(self):
        self.env_patcher.stop()
        clear_sandbox_cost_cache()
        clear_sandbox_metadata_cache()

    def test_costs_endpoint_requires_auth(self):
        unauth_client = TestClient(app)
        response = unauth_client.get("/api/sandboxes/costs")
        self.assertEqual(response.status_code, 401)

    @patch("sandbox.costs.get_sandbox_costs")
    def test_costs_endpoint_forwards_query_params_and_returns_payload(self, mock_get_costs):
        mock_get_costs.return_value = SandboxCostsResponse(
            fetched_at="2026-11-26T13:02:00+00:00",
            costs={
                "sb-1": SandboxCostEntry(
                    sandbox_id="sb-1",
                    profile="prof-1",
                    cost_usd=0.929423,
                    cost_by_resource_usd={"CPU": 0.30914163, "Memory": 0.62028137},
                    duration_seconds=35412.0,
                    source="sandbox_stats",
                    cached=False,
                ),
            },
        )

        response = self.client.get("/api/sandboxes/costs?profile=prof-1&refresh=true&sandbox_ids=sb-1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["fetched_at"], "2026-11-26T13:02:00+00:00")
        self.assertAlmostEqual(data["costs"]["sb-1"]["cost_usd"], 0.929423)
        self.assertEqual(data["costs"]["sb-1"]["source"], "sandbox_stats")
        mock_get_costs.assert_called_once_with(
            app_name=None,
            all_apps=True,
            profile="prof-1",
            refresh=True,
            sandbox_ids=["sb-1"],
        )

    @patch("sandbox.costs.get_sandbox_costs")
    def test_costs_endpoint_scopes_to_app_name(self, mock_get_costs):
        mock_get_costs.return_value = SandboxCostsResponse(
            fetched_at="2026-11-26T13:02:00+00:00",
            costs={},
        )

        response = self.client.get("/api/sandboxes/costs?app_name=my-app")
        self.assertEqual(response.status_code, 200)
        mock_get_costs.assert_called_once_with(
            app_name="my-app",
            all_apps=False,
            profile=None,
            refresh=False,
            sandbox_ids=None,
        )

    @patch("sandbox.lifecycle.get_client_for_profile")
    @patch("sandbox.lifecycle.modal.Sandbox.from_id")
    @patch("sandbox.costs.clear_sandbox_cost_cache")
    def test_terminate_sandbox_clears_cost_cache(self, mock_clear_cost, mock_from_id, mock_get_client):
        mock_get_client.return_value = MagicMock()
        mock_sb = MagicMock()
        mock_sb.poll.return_value = 0
        mock_from_id.return_value = mock_sb

        res = terminate_sandbox("sb-term-1", profile="prof-1")
        self.assertEqual(res["status"], "terminated")
        mock_clear_cost.assert_called_once_with("sb-term-1")


if __name__ == "__main__":
    unittest.main()
