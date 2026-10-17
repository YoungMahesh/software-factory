"""Unit and integration tests for canonical GET /api/repos/{repo}/bottlenecks endpoint."""

import unittest
from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.db import StudioDatabase
from factory.ui.registry import JobRegistry, PreviewRegistry


class TestBottlenecksApiEndpoint(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")
        self.registry = JobRegistry()
        self.preview_reg = PreviewRegistry()
        self.app = create_app(
            registry=self.registry,
            preview_reg=self.preview_reg,
            db=self.db,
        )
        self.client = TestClient(self.app)
        self.auth = ("admin", "admin")

    def tearDown(self):
        self.db.close()

    def test_get_repo_bottlenecks_blank_repo_returns_400(self):
        res = self.client.get("/api/repos/%20/bottlenecks", auth=self.auth)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Repository name is required", res.json()["detail"])

    def test_get_repo_bottlenecks_empty_repo_returns_empty_list(self):
        res = self.client.get("/api/repos/brand-new-repo/bottlenecks", auth=self.auth)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["repo"], "brand-new-repo")
        self.assertEqual(data["bottlenecks"], [])

    def test_get_repo_bottlenecks_aggregation_and_limit(self):
        # 1. Setup jobs and events
        self.db.save_job({
            "id": "job-api-1",
            "repo": "chat-app",
            "feature": "init",
            "model": "deepseek-v4.1-flash",
            "status": "COMPLETED",
        })
        self.db.save_job({
            "id": "job-api-2",
            "repo": "chat-app",
            "feature": "styling",
            "model": "deepseek-v4.1-flash",
            "status": "COMPLETED",
        })

        self.db.append_telemetry_events("job-api-1", [
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm test",
                    "durationMs": 400,
                    "exitCode": 0,
                },
            },
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm install",
                    "durationMs": 2500,
                    "exitCode": 0,
                },
            },
            {
                "type": "thinking",
                "stage": "PLANNER",
                "data": {
                    "delta": "Thinking through state model...",
                    "durationMs": 1800,
                    "done": True,
                },
            },
        ])

        self.db.append_telemetry_events("job-api-2", [
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm test",
                    "durationMs": 600,
                    "exitCode": 0,
                },
            },
        ])
        self.db.flush_batches()

        # 2. Query endpoint
        res = self.client.get("/api/repos/chat-app/bottlenecks", auth=self.auth)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["repo"], "chat-app")
        items = data["bottlenecks"]
        self.assertEqual(len(items), 3)

        # Sorted by total duration: pnpm install (2500), thinking (1800), pnpm test (1000)
        self.assertEqual(items[0]["command"], "pnpm install")
        self.assertEqual(items[0]["category"], "Package Install")
        self.assertEqual(items[0]["stage"], "CODER")
        self.assertEqual(items[0]["count"], 1)
        self.assertEqual(items[0]["total_duration_ms"], 2500)
        self.assertEqual(items[0]["avg_duration_ms"], 2500.0)
        self.assertEqual(items[0]["max_duration_ms"], 2500)

        self.assertEqual(items[1]["command"], "LLM Thinking (PLANNER)")
        self.assertEqual(items[1]["category"], "LLM Thinking")
        self.assertEqual(items[1]["stage"], "PLANNER")
        self.assertEqual(items[1]["count"], 1)
        self.assertEqual(items[1]["total_duration_ms"], 1800)

        self.assertEqual(items[2]["command"], "pnpm test")
        self.assertEqual(items[2]["category"], "Test Suite")
        self.assertEqual(items[2]["stage"], "VERIFIER")
        self.assertEqual(items[2]["count"], 2)
        self.assertEqual(items[2]["total_duration_ms"], 1000)
        self.assertEqual(items[2]["avg_duration_ms"], 500.0)
        self.assertEqual(items[2]["max_duration_ms"], 600)

        # 3. Test limit query param
        limited_res = self.client.get("/api/repos/chat-app/bottlenecks?limit=1", auth=self.auth)
        self.assertEqual(limited_res.status_code, 200)
        limited_items = limited_res.json()["bottlenecks"]
        self.assertEqual(len(limited_items), 1)
        self.assertEqual(limited_items[0]["command"], "pnpm install")
