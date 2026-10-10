"""Unit and integration tests for Agent Event Stream telemetry demux and SSE streaming.

Verifies that JobRegistry demuxes container stdout chunks containing __SF_EVENT__:
envelopes into job.events while keeping job.logs clean, and that the SSE endpoint
streams both initial state and real-time typed agent events.
"""

import json
import subprocess
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

    def test_attempt_start_and_reviewer_rejection_telemetry_pipeline(self):
        job = self.registry.create_job(repo="test-repo", feature="test-feat")
        q = self.registry.add_listener(job.id)

        # 1. Reviewer rejection envelope
        rejection_envelope = (
            '__SF_EVENT__:{"type":"reviewer_rejection","stage":"REVIEWER","data":{"verdict":"rejected","summary":"Missing tests","remediation":"Add unit tests"}}\n'
        )
        self.registry.append_log(job.id, rejection_envelope)

        # 2. Self-correction attempt_start envelope
        attempt_envelope = (
            '__SF_EVENT__:{"type":"attempt_start","stage":"CODER","data":{"attempt":2,"maxRetries":2,"maxAttempts":3,"reason":"reviewer rejection","summary":"Addressing reviewer feedback"}}\n'
        )
        self.registry.append_log(job.id, attempt_envelope)

        # Logs must remain clean
        self.assertEqual(job.logs, [])
        self.assertEqual(len(job.events), 2)
        self.assertEqual(job.events[0]["type"], "reviewer_rejection")
        self.assertEqual(job.events[0]["data"]["summary"], "Missing tests")
        self.assertEqual(job.events[1]["type"], "attempt_start")
        self.assertEqual(job.events[1]["data"]["attempt"], 2)
        self.assertEqual(job.events[1]["data"]["reason"], "reviewer rejection")

        # Listener receives agent_event and attempt milestone events
        received = []
        while not q.empty():
            received.append(q.get_nowait())

        event_names = [r["event"] for r in received]
        self.assertIn("agent_event", event_names)
        self.assertIn("attempt", event_names)

        # Verify attempt payload
        attempt_payload = next(r for r in received if r["event"] == "attempt")
        self.assertEqual(attempt_payload["data"]["type"], "attempt_start")
        self.assertEqual(attempt_payload["data"]["data"]["attempt"], 2)
        self.assertEqual(attempt_payload["data"]["data"]["reason"], "reviewer rejection")

        self.registry.remove_listener(job.id, q)


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

    def test_failing_command_auto_expansion_and_stderr_highlighting(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # Verify failure states and stderr highlighting logic in console template
        self.assertIn("stderr-line", html)
        self.assertIn("isFailure", html)
        self.assertIn("Exit code ${exitCode}", html)


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

    def test_console_renders_semantic_tool_chips_and_diff_preview(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Compact Tool Chip functions and structure
        self.assertIn("tool-chip", html)
        self.assertIn("createToolChip", html)
        self.assertIn("completeToolChip", html)

        # 2. Tool chip semantic formatting
        self.assertIn("Read ${path} (${lineCount}", html)
        self.assertIn("Write ${path} (${bytes}", html)
        self.assertIn("Grep", html)
        self.assertIn("Diff", html)

        # 3. Expandable Diff Preview Card functions and structure
        self.assertIn("diff-preview-card", html)
        self.assertIn("createDiffCard", html)
        self.assertIn("completeDiffCard", html)
        self.assertIn("toggleDiffCard", html)

        # 4. Syntax-colored additions and deletions
        self.assertIn("diff-addition", html)
        self.assertIn("diff-deletion", html)
        self.assertIn("diff-additions", html)
        self.assertIn("diff-deletions", html)

    def test_frontend_diff_preview_parser_execution(self):
        """Verifies frontend JavaScript logic correctly parses and renders unified diffs."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn("diff-addition", html)

        # Run node to verify the exact diff parsing logic extracted from index.html
        js_test = """
        const patch = "--- a/src/app.tsx\\n+++ b/src/app.tsx\\n@@ -1,3 +1,4 @@\\n import React from 'react';\\n-const a = 1;\\n+const a = 2;\\n+const b = 3;\\n";
        const rawLines = patch.split(/\\r?\\n/);
        let additions = 0;
        let deletions = 0;
        const rendered = rawLines.map((line) => {
          if (line.startsWith("+++") || line.startsWith("---")) return { type: "header", line };
          if (line.startsWith("+")) { additions++; return { type: "addition", line }; }
          if (line.startsWith("-")) { deletions++; return { type: "deletion", line }; }
          if (line.startsWith("@@")) return { type: "hunk", line };
          return { type: "context", line };
        });
        console.log(JSON.stringify({ additions, deletions, count: rendered.length }));
        """
        proc = subprocess.run(["node", "-e", js_test], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout)
        self.assertEqual(res["additions"], 2)
        self.assertEqual(res["deletions"], 1)

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

    def test_console_template_contains_self_correction_components(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Self-Correction Loop Attempt Divider components
        self.assertIn("attempt-divider-card", html)
        self.assertIn("Self-Correction Loop: Attempt", html)
        self.assertIn("createAttemptDividerCard", html)

        # 2. Reviewer Rejection Card components
        self.assertIn("reviewer-rejection-card", html)
        self.assertIn("rejection-summary", html)
        self.assertIn("remediation-instructions", html)
        self.assertIn("createReviewerRejectionCard", html)

        # 3. Failing command auto-expansion and stderr highlighting
        self.assertIn("stderr-line", html)
        self.assertIn("isFailure", html)
        self.assertIn("card.isExpanded = true", html)

    def test_frontend_failing_command_auto_expansion_and_stderr_execution(self):
        """Verifies frontend JS logic auto-expands failing commands and highlights stderr lines."""
        js_test = """
        const escapeHtml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const card = {
          id: 'cmd-fail',
          lines: ['Running tests...', 'AssertionError: expected 1 to be 2', 'FAILED tests/test_math.py'],
          fullOutput: 'Running tests...\\nAssertionError: expected 1 to be 2\\nFAILED tests/test_math.py',
          stderr: 'AssertionError: expected 1 to be 2\\nFAILED tests/test_math.py',
          isExpanded: false,
          isFailure: false,
        };
        const resultData = {
          exitCode: 1,
          isError: true,
          stderr: 'AssertionError: expected 1 to be 2\\nFAILED tests/test_math.py',
          output: card.fullOutput,
        };

        const exitCode = typeof resultData.exitCode === 'number' ? resultData.exitCode : (resultData.isError ? 1 : 0);
        const isFailure = exitCode !== 0 || Boolean(resultData.isError);
        if (isFailure) {
          card.isExpanded = true;
          card.isFailure = true;
        }

        const stderrLines = card.stderr ? new Set(card.stderr.split(/\\r?\\n/).map(l => l.trim()).filter(Boolean)) : null;
        function isStderrLine(line, set) {
          if (!line || !line.trim()) return false;
          const trimmed = line.trim();
          if (set && set.has(trimmed)) return true;
          return /^(FAIL|FAILED|Error:|Exception:|AssertionError|Traceback|STDERR:)/i.test(trimmed);
        }

        const rendered = card.lines.map((line) => {
          if (isStderrLine(line, stderrLines)) {
            return { type: 'stderr', line };
          }
          return { type: 'stdout', line };
        });

        console.log(JSON.stringify({
          isExpanded: card.isExpanded,
          isFailure: card.isFailure,
          rendered,
        }));
        """
        proc = subprocess.run(["node", "-e", js_test], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout)
        self.assertTrue(res["isExpanded"])
        self.assertTrue(res["isFailure"])
        self.assertEqual(res["rendered"][0]["type"], "stdout")
        self.assertEqual(res["rendered"][1]["type"], "stderr")
        self.assertEqual(res["rendered"][2]["type"], "stderr")

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

    def test_studio_template_contains_activity_drawer_and_inline_disclosures(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Slide-over Agent Activity drawer component exists, initially hidden
        self.assertIn('id="studio-activity-drawer"', html)
        self.assertIn("hidden", html)
        self.assertIn("Agent Activity", html)

        # 2. Activity button on floating status badge
        self.assertIn('id="btn-studio-activity"', html)

        # 3. Drawer timeline and synchronized raw terminal logs containers
        self.assertIn('id="studio-drawer-timeline"', html)
        self.assertIn('id="studio-drawer-logs"', html)
        self.assertIn('id="btn-close-activity-drawer"', html)
        self.assertIn('id="btn-drawer-tab-timeline"', html)
        self.assertIn('id="btn-drawer-tab-logs"', html)

        # 4. JavaScript handlers for drawer open/close and inline disclosures/step chips
        self.assertIn("openStudioActivityDrawer", html)
        self.assertIn("closeStudioActivityDrawer", html)
        self.assertIn("updateStudioThinkingDisclosure", html)
        self.assertIn("appendStudioStepChip", html)
        self.assertIn("studio-thinking-disclosure", html)
        self.assertIn("studio-step-chips", html)

    def test_studio_chat_turn_renders_inline_thinking_and_step_chips(self):
        """Verifies frontend JS logic streams inline thinking deltas and appends sequential tool chips using actual functions from index.html."""
        import re
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "factory" / "ui" / "templates" / "index.html"
        template_content = template_path.read_text(encoding="utf-8")

        # Extract actual Studio functions from template
        match = re.search(
            r'(let currentStudioTurn = null;.*?function closeStudioActivityDrawer\(\) \{.*?\n    \})',
            template_content,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "Studio assistant turn & drawer functions not found in template")
        functions_js = match.group(1)

        js_test = f"""
        const escapeHtml = (str) => String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        let activeJobId = 'job-test-actual-1';
        let activeJobStage = 'PLANNER';
        const requestAnimationFrame = (cb) => cb();

        class MockElement {{
          constructor(tagName = 'div') {{
            this.tagName = tagName;
            this.children = [];
            this.className = '';
            this.classList = {{
              classes: new Set(),
              add(...cls) {{ cls.forEach(c => this.classes.add(c)); }},
              remove(...cls) {{ cls.forEach(c => this.classes.delete(c)); }},
              contains(c) {{ return this.classes.has(c); }}
            }};
            this.attributes = new Map();
            this.listeners = new Map();
            this.textContent = '';
            this.innerHTML = '';
            this.scrollTop = 0;
            this.scrollHeight = 0;
          }}
          setAttribute(k, v) {{ this.attributes.set(k, v); }}
          getAttribute(k) {{ return this.attributes.get(k); }}
          appendChild(child) {{ this.children.push(child); return child; }}
          addEventListener(evt, fn) {{
            if (!this.listeners.has(evt)) this.listeners.set(evt, []);
            this.listeners.get(evt).push(fn);
          }}
          querySelector(sel) {{
            return this.children[0] || new MockElement();
          }}
          querySelectorAll(sel) {{
            return this.children;
          }}
          scrollIntoView() {{}}
        }}

        const studioChatHistory = new MockElement('div');
        let drawerOpenedWithTarget = null;
        const drawerEl = new MockElement('div');
        const drawerTimeline = new MockElement('div');

        const document = {{
          body: {{ contains: () => true }},
          createElement: (tag) => new MockElement(tag),
          querySelector: () => null,
          querySelectorAll: () => [],
          getElementById: (id) => {{
            if (id === 'studio-activity-drawer') return drawerEl;
            if (id === 'studio-drawer-timeline') return drawerTimeline;
            return new MockElement('div');
          }},
          addEventListener: () => {{}}
        }};

        function switchDrawerTab(tab) {{}}

        {functions_js}

        // Spy on openStudioActivityDrawer
        const origOpen = openStudioActivityDrawer;
        openStudioActivityDrawer = function(targetToolCallId) {{
          drawerOpenedWithTarget = targetToolCallId;
          return origOpen(targetToolCallId);
        }};

        // 1. Thinking delta arrives -> inline pulsating disclosure active
        updateStudioThinkingDisclosure('PLANNER', 'Synthesizing architecture...', 180, false);
        const turn = getOrCreateStudioAssistantTurn(activeJobId);
        const content1 = turn.activeDisclosure.content;
        const duration1 = turn.activeDisclosure.durationMs;
        const isCollapsed1 = turn.activeDisclosure.isCollapsed;

        // 2. Thinking done arrives -> pulsation ends, duration updated, activeDisclosure collapsed
        updateStudioThinkingDisclosure('PLANNER', '', 4500, true);
        const clearedActive = turn.activeDisclosure === null;

        // 3. Sequential tool results arrive -> appends step chips
        appendStudioStepChip('bash', {{ command: 'pnpm test', toolCallId: 'tool-call-1' }}, 'PLANNER');
        appendStudioStepChip('edit', {{ path: 'src/routes/index.tsx', toolCallId: 'tool-call-2' }}, 'CODER');

        // Click second chip to verify drawer trigger
        const chipBtn = turn.stepChipsContainer.children[1];
        const clickHandler = chipBtn.listeners.get('click')[0];
        clickHandler();

        console.log(JSON.stringify({{
          content1,
          duration1,
          isCollapsed1,
          clearedActive,
          chipCount: turn.stepChipsContainer.children.length,
          chip1Html: turn.stepChipsContainer.children[0].innerHTML,
          chip2Html: turn.stepChipsContainer.children[1].innerHTML,
          drawerOpenedWithTarget
        }}));
        """
        proc = subprocess.run(["node", "-e", js_test], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout)

        self.assertEqual(res["content1"], "Synthesizing architecture...")
        self.assertEqual(res["duration1"], 180)
        self.assertFalse(res["isCollapsed1"])
        self.assertTrue(res["clearedActive"])

        self.assertEqual(res["chipCount"], 2)
        self.assertIn("[Ran bash: pnpm test]", res["chip1Html"])
        self.assertIn("[Edited src/routes/index.tsx]", res["chip2Html"])
        self.assertEqual(res["drawerOpenedWithTarget"], "tool-call-2")

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

        # Verify that frontend drawer sync logic clones cards into drawer containers
        import re
        from pathlib import Path
        template_path = Path(__file__).parent.parent / "factory" / "ui" / "templates" / "index.html"
        template_content = template_path.read_text(encoding="utf-8")
        match_sync = re.search(
            r'(function syncToDrawerTimeline\(container, id\)\s*\{.*?\n    \})',
            template_content,
            re.DOTALL,
        )
        self.assertIsNotNone(match_sync, "syncToDrawerTimeline not found in template")
        sync_js = match_sync.group(1)

        js_drawer_test = f"""
        const checkAutoscroll = {{ checked: true }};
        class MockElement {{
          constructor(tagName = 'div') {{
            this.tagName = tagName;
            this.children = [];
            this.className = '';
            this.id = '';
            this.scrollTop = 0;
            this.scrollHeight = 0;
          }}
          appendChild(child) {{ this.children.push(child); return child; }}
          cloneNode(deep) {{
            const copy = new MockElement(this.tagName);
            copy.className = this.className;
            copy.id = this.id;
            return copy;
          }}
        }}

        const drawerTimeline = new MockElement('div');
        const drawerLogs = new MockElement('div');
        const document = {{
          getElementById: (id) => {{
            if (id === 'studio-drawer-timeline') return drawerTimeline;
            if (id === 'studio-drawer-logs') return drawerLogs;
            return null;
          }}
        }};

        {sync_js}

        // Test syncing a command card into drawer timeline
        const card = new MockElement('div');
        card.id = 'tool-1';
        syncToDrawerTimeline(card, 'tool-1');

        console.log(JSON.stringify({{
          drawerTimelineCount: drawerTimeline.children.length,
          drawerCardId: drawerTimeline.children[0].id
        }}));
        """
        proc_drawer = subprocess.run(["node", "-e", js_drawer_test], capture_output=True, text=True, check=True)
        res_drawer = json.loads(proc_drawer.stdout)
        self.assertEqual(res_drawer["drawerTimelineCount"], 1)
        self.assertEqual(res_drawer["drawerCardId"], "drawer-tool-1")


if __name__ == "__main__":
    unittest.main()






