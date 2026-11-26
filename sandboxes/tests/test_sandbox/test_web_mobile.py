"""Tests for mobile-friendly responsive layout markers in the Sandbox Web Dashboard."""

import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.web import app


class TestWebDashboardMobileResponsiveness(unittest.TestCase):
    def setUp(self):
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

    def test_dashboard_includes_mobile_responsive_layout_and_cards(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text

        # Viewport & horizontal overflow prevention
        self.assertIn("width=device-width, initial-scale=1.0", html)
        self.assertIn("overflow-x-hidden", html)

        # Responsive 2x2 tab layout on mobile
        self.assertIn("grid-cols-2 sm:inline-flex", html)

        # Mobile auto-refresh toggle pill
        self.assertIn("autoRefresh = !autoRefresh", html)

        # Mobile card views alongside desktop tables for Sandboxes & Snapshots
        self.assertGreaterEqual(html.count('class="md:hidden space-y-3"'), 2)
        self.assertGreaterEqual(html.count('class="hidden md:block bg-slate-900'), 2)

        # Modals constrain height with pinned headers/footers and scrollable body
        self.assertGreaterEqual(html.count("max-h-[92dvh] overflow-hidden"), 5)
        self.assertGreaterEqual(html.count("flex-1 min-h-0 overflow-y-auto"), 5)
        self.assertIn("fixed bottom-4 left-4 right-4 sm:left-auto", html)

        # Key dashboard IDs remain intact
        for element_id in (
            "nav-tab-scratchpad",
            "builder-prompt-input",
            "builder-submit-btn",
            "github-repos-panel",
            "scratchpad-suggestion-modal",
        ):
            self.assertIn(element_id, html)


if __name__ == "__main__":
    unittest.main()
