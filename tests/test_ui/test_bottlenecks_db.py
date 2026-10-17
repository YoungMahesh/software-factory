"""Unit and integration tests for database telemetry aggregation queries."""

import time
import unittest

from factory.ui.db import StudioDatabase


class TestDatabaseBottlenecksAggregation(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def tearDown(self):
        self.db.close()

    def test_repo_bottlenecks_aggregation_and_grouping(self):
        # 1. Setup jobs for target repo and other repo
        self.db.save_job({
            "id": "job-repo-1",
            "repo": "inventory-tracker",
            "feature": "feat-1",
            "model": "deepseek-v4.1-flash",
            "status": "COMPLETED",
        })
        self.db.save_job({
            "id": "job-repo-2",
            "repo": "inventory-tracker",
            "feature": "feat-2",
            "model": "deepseek-v4.1-flash",
            "status": "COMPLETED",
        })
        self.db.save_job({
            "id": "job-other",
            "repo": "unrelated-repo",
            "feature": "feat-other",
            "model": "deepseek-v4.1-flash",
            "status": "COMPLETED",
        })

        # 2. Append events to job-repo-1
        self.db.append_telemetry_events("job-repo-1", [
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm test",
                    "durationMs": 300,
                    "exitCode": 0,
                    "toolCallId": "tc-1",
                },
            },
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm install",
                    "durationMs": 1500,
                    "exitCode": 0,
                    "toolCallId": "tc-2",
                },
            },
            {
                "type": "thinking",
                "stage": "PLANNER",
                "data": {
                    "delta": "Analyzing requirements...",
                    "durationMs": 1200,
                    "done": True,
                },
            },
        ])

        # 3. Append events to job-repo-2 (including normalized sudo command)
        self.db.append_telemetry_events("job-repo-2", [
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "sudo pnpm test",
                    "durationMs": 500,
                    "exitCode": 0,
                    "toolCallId": "tc-3",
                },
            },
            {
                "type": "tool_result",
                "stage": "PLANNER",
                "data": {
                    "toolName": "bash",
                    "command": "git status",
                    "durationMs": 50,
                    "exitCode": 0,
                    "toolCallId": "tc-4",
                },
            },
        ])

        # 4. Append events to unrelated repo
        self.db.append_telemetry_events("job-other", [
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm test",
                    "durationMs": 9999,
                    "exitCode": 0,
                    "toolCallId": "tc-other",
                },
            },
        ])

        # Flush batches
        self.db.flush_batches()

        # 5. Query aggregated bottlenecks
        bottlenecks = self.db.get_repo_bottlenecks("inventory-tracker")

        # Must not include unrelated repo
        total_pnpm_test_duration = sum(b["total_duration_ms"] for b in bottlenecks if b["command"] == "pnpm test")
        self.assertEqual(total_pnpm_test_duration, 800)

        # Sorted strictly in descending order of total_duration_ms
        commands_in_order = [b["command"] for b in bottlenecks]
        self.assertEqual(commands_in_order, ["pnpm install", "LLM Thinking (PLANNER)", "pnpm test", "git status"])

        # Validate pnpm test metrics
        test_op = next(b for b in bottlenecks if b["command"] == "pnpm test")
        self.assertEqual(test_op["count"], 2)
        self.assertEqual(test_op["total_duration_ms"], 800)
        self.assertEqual(test_op["avg_duration_ms"], 400.0)
        self.assertEqual(test_op["max_duration_ms"], 500)
        self.assertEqual(test_op["category"], "Test Suite")
        self.assertEqual(test_op["stage"], "VERIFIER")

        # Validate pnpm install metrics
        install_op = next(b for b in bottlenecks if b["command"] == "pnpm install")
        self.assertEqual(install_op["count"], 1)
        self.assertEqual(install_op["total_duration_ms"], 1500)
        self.assertEqual(install_op["avg_duration_ms"], 1500.0)
        self.assertEqual(install_op["max_duration_ms"], 1500)
        self.assertEqual(install_op["category"], "Package Install")
        self.assertEqual(install_op["stage"], "CODER")

        # Validate thinking metrics
        think_op = next(b for b in bottlenecks if b["command"] == "LLM Thinking (PLANNER)")
        self.assertEqual(think_op["count"], 1)
        self.assertEqual(think_op["total_duration_ms"], 1200)
        self.assertEqual(think_op["avg_duration_ms"], 1200.0)
        self.assertEqual(think_op["max_duration_ms"], 1200)
        self.assertEqual(think_op["category"], "LLM Thinking")
        self.assertEqual(think_op["stage"], "PLANNER")

        # Test limit parameter
        limited = self.db.get_repo_bottlenecks("inventory-tracker", limit=2)
        self.assertEqual(len(limited), 2)
        self.assertEqual(limited[0]["command"], "pnpm install")
        self.assertEqual(limited[1]["command"], "LLM Thinking (PLANNER)")

    def test_repo_bottlenecks_empty_repo(self):
        bottlenecks = self.db.get_repo_bottlenecks("non-existent-repo")
        self.assertEqual(bottlenecks, [])
