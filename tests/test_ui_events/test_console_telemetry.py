"""Subsystem tests for Agent Event Stream telemetry demux and SSE streaming."""

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.registry import (
    JobRegistry,
    JobStage,
    JobStatus,
)


class TestThinkingAccordionConsole(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_thinking_events_pipeline_and_duration_tracking(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        # 1. Stream PLANNER thinking deltas
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"thinking","stage":"PLANNER","data":{"delta":"Investigating CONTEXT.md...","durationMs":120},"timestamp":100.0}\n'
        )
        # 2. Thinking done with total duration
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"thinking","stage":"PLANNER","data":{"delta":"","done":true,"durationMs":4200},"timestamp":104.2}\n'
        )
        # 3. Tool execution start
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"read","args":{"path":"CONTEXT.md"}},"timestamp":104.5}\n'
        )

        self.assertEqual(len(job.events), 3)
        self.assertEqual(job.events[0]["stage"], "PLANNER")
        self.assertEqual(job.events[0]["data"]["durationMs"], 120)
        self.assertEqual(job.events[1]["data"]["done"], True)
        self.assertEqual(job.events[1]["data"]["durationMs"], 4200)

        # Ensure raw __SF_EVENT__ lines were not added to job.logs
        self.assertEqual(job.logs, [])

        received = []
        while not q.empty():
            received.append(q.get_nowait())

        self.assertEqual(len(received), 3)
        self.assertEqual(received[0]["event"], "agent_event")
        self.assertEqual(received[0]["data"]["type"], "thinking")
        self.assertEqual(received[0]["data"]["data"]["durationMs"], 120)

        self.assertEqual(received[1]["data"]["data"]["done"], True)
        self.assertEqual(received[1]["data"]["data"]["durationMs"], 4200)

        self.assertEqual(received[2]["data"]["type"], "tool_start")
        self.assertEqual(received[2]["data"]["data"]["toolName"], "read")

        self.registry.remove_listener(job.id, q)


class TestCommandExecutionTimelineConsole(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_coder_and_verifier_command_telemetry_pipeline(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        # 1. Coder bash command start
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"bash","command":"pnpm test","cwd":"/workspace","args":{"command":"pnpm test","cwd":"/workspace"},"toolCallId":"c-1"}}\n'
        )
        # 2. Coder bash command result (success)
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"CODER","data":{"toolName":"bash","command":"pnpm test","cwd":"/workspace","exitCode":0,"durationMs":350,"stdout":"PASS src/app.test.ts","stderr":"","output":"PASS src/app.test.ts","isError":false,"toolCallId":"c-1"}}\n'
        )
        # 3. Verifier test suite execution start
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"VERIFIER","data":{"toolName":"bash","command":"pytest","cwd":"/workspace","args":{"command":"pytest","cwd":"/workspace"},"toolCallId":"v-1"}}\n'
        )
        # 4. Verifier test suite execution result (failure)
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"VERIFIER","data":{"toolName":"bash","command":"pytest","cwd":"/workspace","exitCode":1,"durationMs":720,"stdout":"","stderr":"FAILED tests/test_api.py","output":"FAILED tests/test_api.py","isError":true,"toolCallId":"v-1"}}\n'
        )

        self.assertEqual(len(job.events), 4)

        # Verify Coder bash event details
        self.assertEqual(job.events[0]["stage"], "CODER")
        self.assertEqual(job.events[0]["data"]["command"], "pnpm test")
        self.assertEqual(job.events[0]["data"]["cwd"], "/workspace")
        self.assertEqual(job.events[1]["stage"], "CODER")
        self.assertEqual(job.events[1]["data"]["exitCode"], 0)
        self.assertEqual(job.events[1]["data"]["isError"], False)
        self.assertEqual(job.events[1]["data"]["durationMs"], 350)

        # Verify Verifier event details
        self.assertEqual(job.events[2]["stage"], "VERIFIER")
        self.assertEqual(job.events[2]["data"]["command"], "pytest")
        self.assertEqual(job.events[2]["data"]["cwd"], "/workspace")
        self.assertEqual(job.events[3]["stage"], "VERIFIER")
        self.assertEqual(job.events[3]["data"]["exitCode"], 1)
        self.assertEqual(job.events[3]["data"]["isError"], True)
        self.assertEqual(job.events[3]["data"]["durationMs"], 720)

        # Logs must remain clean without __SF_EVENT__: envelopes
        self.assertEqual(job.logs, [])

        received = []
        while not q.empty():
            received.append(q.get_nowait())

        self.assertEqual(len(received), 4)
        for r in received:
            self.assertEqual(r["event"], "agent_event")

        self.registry.remove_listener(job.id, q)

    def test_rehydration_of_command_events_history(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        job.status = JobStatus.SUCCESS
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"bash","command":"npm test","cwd":"/repo","toolCallId":"c-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"CODER","data":{"toolName":"bash","command":"npm test","cwd":"/repo","exitCode":0,"durationMs":100,"output":"ok","toolCallId":"c-1"}}\n'
        )

        with self.client.stream(
            "GET",
            f"/api/jobs/{job.id}/stream",
            auth=("admin", "admin"),
        ) as response:
            self.assertEqual(response.status_code, 200)
            init_event = None
            for chunk in response.iter_lines():
                if chunk.startswith("data: "):
                    payload = json.loads(chunk[len("data: "):])
                    if payload.get("event") == "init":
                        init_event = payload
                        break

        self.assertIsNotNone(init_event)
        self.assertEqual(len(init_event["events"]), 2)
        self.assertEqual(init_event["events"][0]["data"]["command"], "npm test")
        self.assertEqual(init_event["events"][1]["data"]["exitCode"], 0)


class TestSemanticToolTelemetryConsole(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_semantic_tool_telemetry_pipeline(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        # 1. Read start & result (large line count, suppressed verbatim text)
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"read","path":"src/routes/index.tsx","args":{"path":"src/routes/index.tsx"},"toolCallId":"r-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"PLANNER","data":{"toolName":"read","path":"src/routes/index.tsx","lineCount":42,"durationMs":10,"isError":false,"toolCallId":"r-1"}}\n'
        )

        # 2. Write start & result (bytes reported)
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"write","path":"src/config.json","bytes":256,"args":{"path":"src/config.json","bytes":256},"toolCallId":"w-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"CODER","data":{"toolName":"write","path":"src/config.json","bytes":256,"durationMs":18,"isError":false,"toolCallId":"w-1"}}\n'
        )

        # 3. Edit start & result (unified diff patch)
        patch = "--- src/routes/index.tsx\\n+++ src/routes/index.tsx\\n@@ -1,3 +1,3 @@\\n-const a = 1;\\n+const a = 2;\\n"
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"edit","path":"src/routes/index.tsx","args":{"path":"src/routes/index.tsx","editCount":1},"toolCallId":"e-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            f'__SF_EVENT__:{{"type":"tool_result","stage":"CODER","data":{{"toolName":"edit","path":"src/routes/index.tsx","diff":"{patch}","patch":"{patch}","durationMs":35,"isError":false,"toolCallId":"e-1"}}}}\n'
        )

        # 4. Grep start & result
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"grep","pattern":"useState","path":"src/","args":{"pattern":"useState","path":"src/"},"toolCallId":"g-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"PLANNER","data":{"toolName":"grep","pattern":"useState","path":"src/","matchCount":5,"durationMs":14,"isError":false,"toolCallId":"g-1"}}\n'
        )

        # 5. Diff start & result
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"REVIEWER","data":{"toolName":"diff","path":"src/routes/index.tsx","args":{"path":"src/routes/index.tsx"},"toolCallId":"d-1"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"REVIEWER","data":{"toolName":"diff","path":"src/routes/index.tsx","lineCount":12,"durationMs":22,"isError":false,"toolCallId":"d-1"}}\n'
        )

        self.assertEqual(len(job.events), 10)
        self.assertEqual(job.logs, [])  # Logs ring buffer kept completely clean

        # Verify parsed structured events
        self.assertEqual(job.events[0]["data"]["toolName"], "read")
        self.assertEqual(job.events[1]["data"]["lineCount"], 42)
        self.assertEqual(job.events[2]["data"]["toolName"], "write")
        self.assertEqual(job.events[3]["data"]["bytes"], 256)
        self.assertEqual(job.events[4]["data"]["toolName"], "edit")
        self.assertIn("+const a = 2;", job.events[5]["data"]["diff"])
        self.assertEqual(job.events[6]["data"]["pattern"], "useState")
        self.assertEqual(job.events[7]["data"]["matchCount"], 5)
        self.assertEqual(job.events[8]["data"]["toolName"], "diff")
        self.assertEqual(job.events[9]["data"]["lineCount"], 12)

        # Verify SSE streaming
        received = []
        while not q.empty():
            received.append(q.get_nowait())
        self.assertEqual(len(received), 10)
        for r in received:
            self.assertEqual(r["event"], "agent_event")

        self.registry.remove_listener(job.id, q)

    def test_rehydration_of_semantic_tool_and_diff_events(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        job.status = JobStatus.SUCCESS
        patch = "--- src/app.tsx\\n+++ src/app.tsx\\n@@ -1 +1 @@\\n-old\\n+new\\n"
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"read","path":"src/app.tsx","toolCallId":"r-99"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"PLANNER","data":{"toolName":"read","path":"src/app.tsx","lineCount":15,"toolCallId":"r-99"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"edit","path":"src/app.tsx","toolCallId":"e-99"}}\n'
        )
        self.registry.append_log(
            job.id,
            f'__SF_EVENT__:{{"type":"tool_result","stage":"CODER","data":{{"toolName":"edit","path":"src/app.tsx","diff":"{patch}","toolCallId":"e-99"}}}}\n'
        )

        with self.client.stream(
            "GET",
            f"/api/jobs/{job.id}/stream",
            auth=("admin", "admin"),
        ) as response:
            self.assertEqual(response.status_code, 200)
            init_event = None
            for chunk in response.iter_lines():
                if chunk.startswith("data: "):
                    payload = json.loads(chunk[len("data: "):])
                    if payload.get("event") == "init":
                        init_event = payload
                        break

        self.assertIsNotNone(init_event)
        self.assertEqual(len(init_event["events"]), 4)
        self.assertEqual(init_event["events"][0]["data"]["toolName"], "read")
        self.assertEqual(init_event["events"][1]["data"]["lineCount"], 15)
        self.assertEqual(init_event["events"][2]["data"]["toolName"], "edit")
        self.assertIn("+new", init_event["events"][3]["data"]["diff"])


class TestSelfCorrectionVisualStatesConsole(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_rehydration_of_attempt_dividers_and_rejection_cards(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        job.status = JobStatus.SUCCESS

        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"reviewer_rejection","stage":"REVIEWER","data":{"verdict":"rejected","summary":"Missing security checks","remediation":"Add auth middleware"}}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"attempt_start","stage":"CODER","data":{"attempt":2,"maxRetries":2,"maxAttempts":3,"reason":"reviewer rejection","summary":"Addressing reviewer feedback"}}\n'
        )

        with self.client.stream(
            "GET",
            f"/api/jobs/{job.id}/stream",
            auth=("admin", "admin"),
        ) as response:
            self.assertEqual(response.status_code, 200)
            init_event = None
            for chunk in response.iter_lines():
                if chunk.startswith("data: "):
                    payload = json.loads(chunk[len("data: "):])
                    if payload.get("event") == "init":
                        init_event = payload
                        break

        self.assertIsNotNone(init_event)
        self.assertEqual(len(init_event["events"]), 2)
        self.assertEqual(init_event["events"][0]["type"], "reviewer_rejection")
        self.assertEqual(init_event["events"][0]["data"]["summary"], "Missing security checks")
        self.assertEqual(init_event["events"][1]["type"], "attempt_start")
        self.assertEqual(init_event["events"][1]["data"]["attempt"], 2)


class TestStudioActivityDrawerAndInlineDisclosures(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_slide_over_drawer_syncs_with_sse_stream(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        job.status = JobStatus.SUCCESS

        # 1. Thinking delta event
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"thinking","stage":"PLANNER","data":{"delta":"Synthesizing plan...","durationMs":250},"timestamp":100.0}\n'
        )
        # 2. Bash command start and result
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"bash","args":{"command":"pnpm test"},"toolCallId":"tool-1"},"timestamp":101.0}\n'
        )
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"tool_result","stage":"PLANNER","data":{"toolName":"bash","command":"pnpm test","exitCode":0,"output":"1 passed\\n","isError":false,"toolCallId":"tool-1"},"timestamp":102.0}\n'
        )
        # 3. Synchronized plain log line
        self.registry.append_log(job.id, "Deterministic verifier completed.\n")

        with self.client.stream(
            "GET",
            f"/api/jobs/{job.id}/stream",
            auth=("admin", "admin"),
        ) as response:
            self.assertEqual(response.status_code, 200)
            events = []
            for chunk in response.iter_lines():
                if chunk.startswith("data: "):
                    payload = json.loads(chunk[len("data: "):])
                    events.append(payload)
                    if payload.get("event") == "status":
                        break
                    # We expect init event
                    if payload.get("event") == "init":
                        break

        self.assertTrue(len(events) >= 1)
        init_event = events[0]
        self.assertEqual(init_event["event"], "init")
        # backlog contains synchronized plain text log
        self.assertEqual(init_event["backlog"], ["Deterministic verifier completed.\n"])
        # events array contains structured telemetry stream
        self.assertEqual(len(init_event["events"]), 3)
        self.assertEqual(init_event["events"][0]["type"], "thinking")
        self.assertEqual(init_event["events"][0]["data"]["delta"], "Synthesizing plan...")
        self.assertEqual(init_event["events"][1]["type"], "tool_start")
        self.assertEqual(init_event["events"][2]["type"], "tool_result")
        self.assertEqual(init_event["events"][2]["data"]["command"], "pnpm test")


if __name__ == "__main__":
    unittest.main()
