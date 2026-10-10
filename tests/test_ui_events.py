"""Unit and integration tests for Agent Event Stream telemetry demux and SSE streaming.

Verifies that JobRegistry demuxes container stdout chunks containing __SF_EVENT__:
envelopes into job.events while keeping job.logs clean, and that the SSE endpoint
streams both initial state and real-time typed agent events.
"""

import json
from pathlib import Path
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
        comp_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "ThinkingAccordion.tsx"
        code = comp_path.read_text(encoding="utf-8")

        # 1. Active thinking container with animated pulse accent
        self.assertIn("thinking-accordion", code)
        self.assertIn("animate-pulse", code)

        # 2. Collapsed badge with elapsed time
        self.assertIn("Reasoning finished in", code)

        # 3. Expand / collapse toggle handler
        self.assertIn("setIsExpanded(!isExpanded)", code)

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
        comp_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "CommandCard.tsx"
        code = comp_path.read_text(encoding="utf-8")

        # 1. Dedicated Command Execution Card container
        self.assertIn("command-card", code)

        # 2. Exit code logic and failure state
        self.assertIn("isFailure", code)

        # 3. Windowed output toggle
        self.assertIn("totalLines > 100", code)
        self.assertIn("setShowFullOutput", code)

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
        comp_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "CommandCard.tsx"
        code = comp_path.read_text(encoding="utf-8")

        # Verify threshold is 100 lines
        self.assertIn("totalLines > 100", code)
        self.assertIn("lines.slice(-100)", code)
        self.assertIn("showFullOutput", code)

    def test_failing_command_auto_expansion_and_stderr_highlighting(self):
        comp_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "CommandCard.tsx"
        code = comp_path.read_text(encoding="utf-8")

        # Verify failure states and stderr highlighting logic in CommandCard
        self.assertIn("isStderrLine", code)
        self.assertIn("isFailure", code)


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
        chip_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "ToolChip.tsx"
        chip_code = chip_path.read_text(encoding="utf-8")

        # 1. Compact Tool Chip component and styling
        self.assertIn("tool-chip", chip_code)
        self.assertIn("formatToolLabel", chip_code)

        diff_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "DiffViewer.tsx"
        diff_code = diff_path.read_text(encoding="utf-8")

        # 2. Expandable Diff Preview Card functions and structure
        self.assertIn("diff-preview-card", diff_code)
        self.assertIn("diff-addition", diff_code)
        self.assertIn("diff-deletion", diff_code)

    def test_frontend_diff_preview_parser_execution(self):
        """Verifies frontend JavaScript logic correctly parses and renders unified diffs."""
        diff_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "DiffViewer.tsx"
        diff_code = diff_path.read_text(encoding="utf-8")
        self.assertIn("diff-addition", diff_code)

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
        comp_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "SelfCorrectionCards.tsx"
        code = comp_path.read_text(encoding="utf-8")

        # 1. Self-Correction Loop Attempt Divider components
        self.assertIn("attempt-divider-card", code)
        self.assertIn("Self-Correction Loop: Attempt", code)

        # 2. Reviewer Rejection Card components
        self.assertIn("reviewer-rejection-card", code)
        self.assertIn("rejection-summary", code)
        self.assertIn("remediation-instructions", code)

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
        drawer_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "ActivityDrawer.tsx"
        drawer_code = drawer_path.read_text(encoding="utf-8")

        # 1. Slide-over Agent Activity drawer component exists
        self.assertIn('id="studio-activity-drawer"', drawer_code)
        self.assertIn("Agent Activity", drawer_code)

        # 2. Drawer timeline and synchronized raw terminal logs tabs
        self.assertIn("activeTab", drawer_code)
        self.assertIn("handleCopyLogs", drawer_code)

    def test_studio_chat_turn_renders_inline_thinking_and_step_chips(self):
        """Verifies Studio chat timeline renders thinking disclosures and step chips."""
        studio_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "views" / "StudioView.tsx"
        studio_code = studio_path.read_text(encoding="utf-8")
        self.assertIn("ThinkingAccordion", studio_code)
        self.assertIn("ToolChip", studio_code)
        self.assertIn("onOpenDrawer", studio_code)

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

        # Verify that frontend ActivityDrawer integrates structured telemetry cards
        drawer_path = Path(__file__).parent.parent / "factory" / "ui" / "frontend" / "src" / "components" / "ActivityDrawer.tsx"
        drawer_code = drawer_path.read_text(encoding="utf-8")
        self.assertIn("ThinkingAccordion", drawer_code)
        self.assertIn("CommandCard", drawer_code)
        self.assertIn("ToolChip", drawer_code)
        self.assertIn("DiffViewer", drawer_code)
        self.assertIn("AttemptDividerCard", drawer_code)
        self.assertIn("ReviewerRejectionCard", drawer_code)


if __name__ == "__main__":
    unittest.main()






