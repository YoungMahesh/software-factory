"""Unit and integration tests for Agent Event Stream telemetry demux and SSE streaming.

Verifies that JobRegistry demuxes container stdout chunks containing __SF_EVENT__:
envelopes into job.events while keeping job.logs clean, and that the SSE endpoint
streams both initial state and real-time typed agent events.
"""

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


class TestAgentEventStreamDemux(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)

    def test_job_has_events_storage_channel(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        self.assertTrue(hasattr(job, "events"))
        self.assertEqual(job.events, [])
        self.assertEqual(job.to_dict()["event_count"], 0)

    def test_append_log_single_event_envelope(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        raw_envelope = '__SF_EVENT__:{"type":"thinking","stage":"PLANNER","data":{"delta":"Analyzing code..."},"timestamp":1728547200.0}\n'
        self.registry.append_log(job.id, raw_envelope)

        # 1. job.events has the parsed structured event
        self.assertEqual(len(job.events), 1)
        self.assertEqual(job.events[0]["type"], "thinking")
        self.assertEqual(job.events[0]["stage"], "PLANNER")
        self.assertEqual(job.events[0]["data"]["delta"], "Analyzing code...")
        self.assertEqual(job.events[0]["timestamp"], 1728547200.0)

        # 2. Raw envelope line is stripped from job.logs
        self.assertEqual(job.logs, [])
        self.assertEqual(job.to_dict()["event_count"], 1)
        self.assertEqual(job.to_dict()["log_count"], 0)

        # 3. Broadcast to listener as discrete agent_event payload
        self.assertIsNotNone(q)
        event = q.get_nowait()
        self.assertEqual(event["event"], "agent_event")
        self.assertEqual(event["data"]["type"], "thinking")
        self.assertEqual(event["data"]["data"]["delta"], "Analyzing code...")

        self.registry.remove_listener(job.id, q)

    def test_mixed_chunk_stdout_demux(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        # Simulated stdout chunk containing mixed plain text and __SF_EVENT__: envelopes
        mixed_chunk = (
            "Starting step 1: analysis\n"
            '__SF_EVENT__:{"type":"thinking","stage":"PLANNER","data":{"delta":"Inspecting files"}}\n'
            '__SF_EVENT__:{"type":"tool_start","stage":"PLANNER","data":{"toolName":"read","args":{"path":"CONTEXT.md"}}}\n'
            "Reading CONTEXT.md complete.\n"
            '__SF_EVENT__:{"type":"tool_result","stage":"PLANNER","data":{"toolName":"read","result":"Domain context","isError":false}}\n'
            "Step 1 completed successfully.\n"
        )

        self.registry.append_log(job.id, mixed_chunk)

        # Verify job.logs contains only clean plain-text terminal output
        expected_logs = [
            "Starting step 1: analysis\n",
            "Reading CONTEXT.md complete.\n",
            "Step 1 completed successfully.\n",
        ]
        self.assertEqual(job.logs, expected_logs)

        # Verify job.events contains all 3 structured telemetry events
        self.assertEqual(len(job.events), 3)
        self.assertEqual(job.events[0]["type"], "thinking")
        self.assertEqual(job.events[1]["type"], "tool_start")
        self.assertEqual(job.events[1]["data"]["toolName"], "read")
        self.assertEqual(job.events[2]["type"], "tool_result")
        self.assertEqual(job.events[2]["data"]["result"], "Domain context")

        # Verify listener received interleaved events in correct order
        received = []
        while not q.empty():
            received.append(q.get_nowait())

        # Expected:
        # 1. log: Starting step 1: analysis\n
        # 2. agent_event: thinking
        # 3. agent_event: tool_start
        # 4. log: Reading CONTEXT.md complete.\n
        # 5. agent_event: tool_result
        # 6. log: Step 1 completed successfully.\n
        self.assertEqual(len(received), 6)
        self.assertEqual(received[0]["event"], "log")
        self.assertEqual(received[0]["data"], "Starting step 1: analysis\n")
        self.assertEqual(received[1]["event"], "agent_event")
        self.assertEqual(received[1]["data"]["type"], "thinking")
        self.assertEqual(received[2]["event"], "agent_event")
        self.assertEqual(received[2]["data"]["type"], "tool_start")
        self.assertEqual(received[3]["event"], "log")
        self.assertEqual(received[3]["data"], "Reading CONTEXT.md complete.\n")
        self.assertEqual(received[4]["event"], "agent_event")
        self.assertEqual(received[4]["data"]["type"], "tool_result")
        self.assertEqual(received[5]["event"], "log")
        self.assertEqual(received[5]["data"], "Step 1 completed successfully.\n")

        self.registry.remove_listener(job.id, q)

    def test_chunk_fragmentation_reassembly(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")

        # Chunk 1 splits midway through an __SF_EVENT__ envelope
        chunk1 = (
            "Building components...\n"
            '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"ba'
        )
        # Chunk 2 supplies the remainder of the envelope and the next terminal log
        chunk2 = 'sh","args":{"cmd":"ls"}}}\nBuild successful.\n'

        self.registry.append_log(job.id, chunk1)
        # First log line processed, partial envelope buffered
        self.assertEqual(job.logs, ["Building components...\n"])
        self.assertEqual(len(job.events), 0)

        self.registry.append_log(job.id, chunk2)
        # Reassembled: parsed into job.events, clean plain logs
        self.assertEqual(len(job.events), 1)
        self.assertEqual(job.events[0]["type"], "tool_start")
        self.assertEqual(job.events[0]["data"]["toolName"], "bash")
        self.assertEqual(job.events[0]["data"]["args"]["cmd"], "ls")
        self.assertEqual(
            job.logs,
            ["Building components...\n", "Build successful.\n"],
        )

    def test_stage_event_envelope_updates_stage(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        envelope = '__SF_EVENT__:{"type":"stage","stage":"PLANNER","data":{"ticket":"#1"},"timestamp":100.0}\n'
        self.registry.append_log(job.id, envelope)

        self.assertEqual(job.stage, JobStage.PLANNER)
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        # Should broadcast stage transition and agent_event
        event_types = [e["event"] for e in events]
        self.assertIn("stage", event_types)
        self.assertIn("agent_event", event_types)

        self.registry.remove_listener(job.id, q)

    def test_malformed_sf_event_gracefully_handled(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        # Should not crash on invalid JSON
        self.registry.append_log(job.id, "__SF_EVENT__:not-a-json-object\n")
        # Invalid JSON should not be added to events
        self.assertEqual(job.events, [])

    def test_sse_init_payload_contains_backlog_and_events(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        job.status = JobStatus.SUCCESS

        # Seed job with both plain logs and structured events
        self.registry.append_log(job.id, "Initial log line 1\n")
        self.registry.append_log(
            job.id,
            '__SF_EVENT__:{"type":"thinking","stage":"CODER","data":{"delta":"Writing tests..."}}\n',
        )
        self.registry.append_log(job.id, "Initial log line 2\n")

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
            self.assertIn("backlog", init_event)
            self.assertIn("events", init_event)
            self.assertEqual(
                init_event["backlog"],
                ["Initial log line 1\n", "Initial log line 2\n"],
            )
            self.assertEqual(len(init_event["events"]), 1)
            self.assertEqual(init_event["events"][0]["type"], "thinking")
            self.assertEqual(
                init_event["events"][0]["data"]["delta"],
                "Writing tests...",
            )

    def test_sse_realtime_stream_receives_agent_events(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        self.registry.append_log(job.id, "Ready.\n")
        job.status = JobStatus.SUCCESS

        orig_add_listener = self.registry.add_listener

        def add_listener_and_emit(jid):
            q = orig_add_listener(jid)
            self.registry.append_log(
                jid,
                '__SF_EVENT__:{"type":"tool_start","stage":"CODER","data":{"toolName":"bash","args":{"command":"pytest"}}}\n',
            )
            return q

        with patch.object(self.registry, "add_listener", side_effect=add_listener_and_emit):
            with self.client.stream(
                "GET",
                f"/api/jobs/{job.id}/stream",
                auth=("admin", "admin"),
            ) as response:
                self.assertEqual(response.status_code, 200)
                received_events = []
                for chunk in response.iter_lines():
                    if chunk.startswith("data: "):
                        payload = json.loads(chunk[len("data: "):])
                        received_events.append(payload)

                event_types = [e.get("event") for e in received_events]
                self.assertIn("init", event_types)
                self.assertIn("agent_event", event_types)

                agent_event = next(e for e in received_events if e.get("event") == "agent_event")
                self.assertEqual(agent_event["data"]["type"], "tool_start")
                self.assertEqual(agent_event["data"]["data"]["toolName"], "bash")


class TestThinkingAccordionConsole(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def test_console_template_contains_thinking_accordion_components(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Active thinking container with animated pulse accent
        self.assertIn("thinking-accordion", html)
        self.assertIn("animate-pulse", html)

        # 2. Collapsed badge with elapsed time
        self.assertIn("Reasoning finished in", html)

        # 3. Expand / collapse toggle handler
        self.assertIn("toggleThinkingAccordion", html)

        # 4. Agent Event Stream telemetry handler for thinking events
        self.assertIn("handleAgentTelemetryEvent", html)

        # 5. Auto-collapses on completion / tool_start
        self.assertIn("collapseThinkingBlock", html)

        # 6. Markdown rendering and history rehydration
        self.assertIn("marked.min.js", html)
        self.assertIn("renderThinkingContent", html)
        self.assertIn("rehydrateEventsHistory", html)

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

    def test_console_template_contains_command_execution_card_components(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Dedicated Command Execution Card container
        self.assertIn("command-card", html)

        # 2. Active running spinner and timer counter
        self.assertIn("animate-spin", html)
        self.assertIn("command-timer", html)

        # 3. Exit code badge ("Exit code 0" in green, non-zero in red)
        self.assertIn("Exit code 0", html)
        self.assertIn("Exit code", html)

        # 4. Windowed output toggle ("Showing last 100 of N lines — [View full output]")
        self.assertIn("Showing last 100 of", html)
        self.assertIn("[View full output]", html)

        # 5. Full output expansion toggle function
        self.assertIn("toggleCommandOutput", html)

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

    def test_windowed_output_rendering_and_expand_toggle_logic(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # Verify threshold is 100 lines
        self.assertIn("totalLines <= 100", html)
        self.assertIn("card.lines.slice(-100)", html)
        self.assertIn("Showing last 100 of ${totalLines} lines —", html)
        self.assertIn("[View full output]", html)
        self.assertIn("[Show last 100 lines]", html)

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


if __name__ == "__main__":
    unittest.main()




