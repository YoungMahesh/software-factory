"""Subsystem tests for GET /api/jobs/{job_id}/failed-commands endpoint."""

import unittest
from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.db import StudioDatabase
from factory.ui.registry import JobRegistry, JobStatus, JobStage, FactoryJob


class TestFailedCommandsEndpoint(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")
        self.registry = JobRegistry(db=self.db)
        self.app = create_app(registry=self.registry, db=self.db)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def tearDown(self):
        self.db.close()

    def test_failed_commands_in_memory_job_isolates_coder_and_verifier_failures(self):
        job = self.registry.create_job(
            repo="test-repo",
            feature="failed-cmd-test",
            issue="1",
        )
        job.status = JobStatus.RUNNING

        # Add various telemetry events to in-memory job
        job.events = [
            # 1. Successful bash command in CODER (must be excluded)
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm install",
                    "cwd": "/workspace",
                    "exitCode": 0,
                    "isError": False,
                    "durationMs": 1500,
                    "output": "dependencies installed",
                    "stdout": "dependencies installed",
                    "stderr": "",
                    "toolCallId": "call-1",
                },
            },
            # 2. Failed bash command in CODER (must be included)
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm build",
                    "cwd": "/workspace",
                    "exitCode": 1,
                    "isError": True,
                    "durationMs": 850,
                    "output": "tsc: not found",
                    "stdout": "",
                    "stderr": "tsc: not found",
                    "toolCallId": "call-2",
                },
            },
            # 3. Failed bash command in VERIFIER (must be included)
            {
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm test",
                    "cwd": "/workspace",
                    "exitCode": 2,
                    "isError": True,
                    "durationMs": 1200,
                    "output": "FAIL src/app.test.ts",
                    "stdout": "",
                    "stderr": "FAIL src/app.test.ts",
                    "toolCallId": "call-3",
                },
            },
            # 4. Failed non-bash tool in CODER (e.g. read error) (must be excluded)
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "read",
                    "path": "/workspace/missing.ts",
                    "exitCode": 1,
                    "isError": True,
                    "output": "File not found",
                    "toolCallId": "call-4",
                },
            },
            # 5. Failed bash command in PLANNER (must be excluded: only CODER & VERIFIER)
            {
                "type": "tool_result",
                "stage": "PLANNER",
                "data": {
                    "toolName": "bash",
                    "command": "cat unknown.txt",
                    "cwd": "/workspace",
                    "exitCode": 1,
                    "isError": True,
                    "output": "No such file",
                    "toolCallId": "call-5",
                },
            },
        ]

        resp = self.client.get(f"/api/jobs/{job.id}/failed-commands")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["job_id"], job.id)
        self.assertEqual(data["total_failed"], 2)
        failed_cmds = data["failed_commands"]
        self.assertEqual(len(failed_cmds), 2)

        # Inspect first failed command (CODER)
        c1 = failed_cmds[0]
        self.assertEqual(c1["command"], "pnpm build")
        self.assertEqual(c1["stage"], "CODER")
        self.assertEqual(c1["cwd"], "/workspace")
        self.assertEqual(c1["exit_code"], 1)
        self.assertEqual(c1["exitCode"], 1)
        self.assertEqual(c1["duration_ms"], 850)
        self.assertEqual(c1["stderr"], "tsc: not found")
        self.assertEqual(c1["is_error"], True)

        # Inspect second failed command (VERIFIER)
        c2 = failed_cmds[1]
        self.assertEqual(c2["command"], "pnpm test")
        self.assertEqual(c2["stage"], "VERIFIER")
        self.assertEqual(c2["exit_code"], 2)
        self.assertEqual(c2["exitCode"], 2)
        self.assertEqual(c2["duration_ms"], 1200)
        self.assertEqual(c2["stderr"], "FAIL src/app.test.ts")

    def test_failed_commands_queried_from_studio_database_for_historical_job(self):
        # Create a historical job directly in the database
        job_id = "hist-job-999"
        self.db.save_job({
            "id": job_id,
            "repo": "historical-repo",
            "feature": "slug-gen",
            "status": "FAILED",
            "stage": "VERIFIER",
        })

        # Save telemetry events to DB
        self.db.append_telemetry_events(job_id, [
            {
                "id": "evt-1",
                "type": "tool_result",
                "stage": "VERIFIER",
                "data": {
                    "toolName": "bash",
                    "command": "pytest tests/",
                    "cwd": "/workspace",
                    "exitCode": 1,
                    "durationMs": 4200,
                    "stdout": "",
                    "stderr": "FAILED tests/test_app.py::test_fail",
                    "output": "FAILED tests/test_app.py::test_fail",
                    "isError": True,
                },
            },
        ])

        # Ensure registry does NOT have this job in memory
        self.assertIsNone(self.registry._jobs.get(job_id))

        resp = self.client.get(f"/api/jobs/{job_id}/failed-commands")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["total_failed"], 1)
        self.assertEqual(len(data["failed_commands"]), 1)
        self.assertEqual(data["failed_commands"][0]["command"], "pytest tests/")
        self.assertEqual(data["failed_commands"][0]["stage"], "VERIFIER")
        self.assertEqual(data["failed_commands"][0]["exit_code"], 1)

    def test_failed_commands_empty_state_when_zero_failures(self):
        job = self.registry.create_job(repo="clean-repo", feature="clean-run")
        job.events = [
            {
                "type": "tool_result",
                "stage": "CODER",
                "data": {
                    "toolName": "bash",
                    "command": "pnpm build",
                    "exitCode": 0,
                    "isError": False,
                },
            }
        ]

        resp = self.client.get(f"/api/jobs/{job.id}/failed-commands")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["job_id"], job.id)
        self.assertEqual(data["total_failed"], 0)
        self.assertEqual(data["failed_commands"], [])

    def test_failed_commands_returns_404_when_job_not_found(self):
        resp = self.client.get("/api/jobs/nonexistent-job-id/failed-commands")
        self.assertEqual(resp.status_code, 404)
