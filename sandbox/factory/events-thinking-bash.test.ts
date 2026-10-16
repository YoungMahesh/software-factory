import { describe, it } from "node:test";
import * as assert from "node:assert/strict";
import {
  EVENT_PREFIX,
  formatTelemetryEnvelope,
  parseTelemetryEnvelope,
  emitTelemetryEvent,
  emitThinkingEvent,
  emitToolStartEvent,
  emitToolResultEvent,
  emitStageEvent,
  emitAttemptEvent,
  emitAttemptStartEvent,
  emitReviewerRejectionEvent,
  emitDeliveryGateEvent,
  type DeliveryGateEventData,
  AgentEventStream,
  ThinkingBatchBuffer,
  ThinkingExtractor,
  type TelemetryEnvelope,
} from "./events.ts";


describe("Agent Event Stream Telemetry Emitter - Thinking & Bash", () => {
  describe("ThinkingExtractor (Dual-Extraction & Throttled Reasoning Stream)", () => {
    it("captures native thinking_delta events and tracks duration and stage", async () => {
      const chunks: string[] = [];
      // @ts-ignore - will be implemented in events.ts
      const extractor = new ThinkingExtractor({
        stage: "PLANNER",
        stream: { write: (c: string) => chunks.push(c) },
        intervalMs: 50,
      });

      extractor.handleThinkingDelta("Step 1: Inspecting ");
      extractor.handleThinkingDelta("CONTEXT.md ");
      assert.equal(chunks.length, 0, "Deltas should be buffered in micro-batch buffer");

      await new Promise((r) => setTimeout(r, 70));
      assert.equal(chunks.length, 1, "Micro-batch buffer should flush after interval");

      const env1 = parseTelemetryEnvelope(chunks[0]);
      assert.equal(env1?.type, "thinking");
      assert.equal(env1?.stage, "PLANNER");
      assert.equal(env1?.data.delta, "Step 1: Inspecting CONTEXT.md ");
      assert.ok(typeof env1?.data.durationMs === "number");

      // Signal completion of thinking
      extractor.handleThinkingEnd();
      assert.equal(chunks.length, 2, "Thinking end should immediately flush final event");
      const endEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(endEnv?.type, "thinking");
      assert.equal(endEnv?.data.done, true);
      assert.ok(endEnv?.data.durationMs >= 0);
    });

    it("extracts and strips text-streamed <think>...</think> blocks across chunk boundaries", () => {
      const chunks: string[] = [];
      // @ts-ignore
      const extractor = new ThinkingExtractor({
        stage: "CODER",
        stream: { write: (c: string) => chunks.push(c) },
        intervalMs: 100,
      });

      // Split <think> tags across multiple delta chunks
      const deltas = [
        "Let me analyze: <th",
        "ink>First, I will modify ",
        "src/auth.ts to check credentials.",
        "</th",
        "ink>Here is the implementation code.",
      ];

      const strippedParts: string[] = [];
      for (const d of deltas) {
        const res = extractor.handleTextDelta(d);
        if (res.strippedText) {
          strippedParts.push(res.strippedText);
        }
      }

      // Check stripped text: <think> and </think> tags and contents must be stripped
      const fullStripped = strippedParts.join("");
      assert.equal(fullStripped, "Let me analyze: Here is the implementation code.");

      // Verify that reasoning content was captured and flushed on </think>
      assert.ok(chunks.length >= 1, "Thinking should be flushed on closing tag");
      const allThinking = chunks
        .map((c) => parseTelemetryEnvelope(c)?.data.delta || "")
        .join("");
      assert.ok(allThinking.includes("First, I will modify src/auth.ts"));
      assert.equal(extractor.getAccumulatedThinking(), "First, I will modify src/auth.ts to check credentials.");
    });

    it("throttles rapid burst of 20 reasoning deltas into 100ms envelopes", async () => {
      const chunks: string[] = [];
      // @ts-ignore
      const extractor = new ThinkingExtractor({
        stage: "REVIEWER",
        stream: { write: (c: string) => chunks.push(c) },
        intervalMs: 80,
      });

      // Rapid burst of 20 deltas emitted in tight sync loop
      for (let i = 0; i < 20; i++) {
        extractor.handleThinkingDelta(`token_${i} `);
      }

      assert.equal(chunks.length, 0, "No chunks should be emitted immediately during burst");

      // Wait for one interval
      await new Promise((r) => setTimeout(r, 100));
      assert.equal(chunks.length, 1, "20 burst tokens should be aggregated into single envelope");

      const env = parseTelemetryEnvelope(chunks[0]);
      assert.equal(env?.stage, "REVIEWER");
      assert.ok(env?.data.delta.startsWith("token_0 "));
      assert.ok(env?.data.delta.includes("token_19 "));
    });

    it("immediately flushes pending thinking when tool starts", () => {
      const chunks: string[] = [];
      // @ts-ignore
      const extractor = new ThinkingExtractor({
        stage: "CODER",
        stream: { write: (c: string) => chunks.push(c) },
        intervalMs: 100,
      });

      extractor.handleThinkingDelta("Decided to run tests.");
      assert.equal(chunks.length, 0);

      // Tool starts before interval expires
      extractor.handleToolStart("bash", { command: "pytest" }, "call-1");

      assert.equal(chunks.length, 2, "Both flushed thinking and tool_start should be emitted");
      const thinkEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(thinkEnv?.type, "thinking");
      assert.equal(thinkEnv?.data.delta, "Decided to run tests.");
      assert.equal(thinkEnv?.data.done, true);

      const toolEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(toolEnv?.type, "tool_start");
      assert.equal(toolEnv?.data.toolName, "bash");
    });
  });

  describe("Bash Command Execution Telemetry", () => {
    it("captures tool_execution_start and tool_execution_end for bash invocations with exact command strings and working directories", () => {
      const chunks: string[] = [];
      let listener: any = null;
      const fakeAgent = {
        subscribe: (fn: any) => {
          listener = fn;
          return () => {
            listener = null;
          };
        },
      };

      const eventStream = new AgentEventStream({
        stage: "CODER",
        stream: { write: (c: string) => chunks.push(c) },
        workspaceDir: "/root/target-repo",
      });
      eventStream.subscribe(fakeAgent);

      assert.ok(listener, "Listener should be registered");

      // 1. Tool execution start
      listener({
        type: "tool_execution_start",
        toolCallId: "call-bash-123",
        toolName: "bash",
        args: { command: "npm test -- --coverage" },
      });

      assert.equal(chunks.length, 1);
      const startEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(startEnv?.type, "tool_start");
      assert.equal(startEnv?.stage, "CODER");
      assert.equal(startEnv?.data.toolName, "bash");
      assert.equal(startEnv?.data.command, "npm test -- --coverage");
      assert.equal(startEnv?.data.cwd, "/root/target-repo");
      assert.equal(startEnv?.data.toolCallId, "call-bash-123");

      // 2. Tool execution end (success)
      listener({
        type: "tool_execution_end",
        toolCallId: "call-bash-123",
        toolName: "bash",
        result: {
          content: [{ type: "text", text: "PASS src/index.test.ts" }],
          structuredContent: {
            output: "PASS src/index.test.ts\nAll tests passed\n",
            exit_code: 0,
            wall_time_seconds: 1,
            truncated: false,
          },
        },
        isError: false,
        durationMs: 450,
      });

      assert.equal(chunks.length, 2);
      const resultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(resultEnv?.type, "tool_result");
      assert.equal(resultEnv?.stage, "CODER");
      assert.equal(resultEnv?.data.toolName, "bash");
      assert.equal(resultEnv?.data.command, "npm test -- --coverage");
      assert.equal(resultEnv?.data.cwd, "/root/target-repo");
      assert.equal(resultEnv?.data.exitCode, 0);
      assert.equal(resultEnv?.data.durationMs, 450);
      assert.equal(resultEnv?.data.isError, false);
      assert.ok(resultEnv?.data.stdout.includes("PASS src/index.test.ts"));
      assert.equal(resultEnv?.data.toolCallId, "call-bash-123");
    });

    it("captures failing bash tool executions with non-zero exit codes, stderr text, and isError flag", () => {
      const chunks: string[] = [];
      let listener: any = null;
      const fakeAgent = {
        subscribe: (fn: any) => {
          listener = fn;
          return () => {
            listener = null;
          };
        },
      };

      const eventStream = new AgentEventStream({
        stage: "CODER",
        stream: { write: (c: string) => chunks.push(c) },
        workspaceDir: "/root/target-repo",
      });
      eventStream.subscribe(fakeAgent);

      // Start
      listener({
        type: "tool_execution_start",
        toolCallId: "call-bash-fail",
        toolName: "bash",
        args: { command: "pytest -v" },
      });

      // End with non-zero exit code
      listener({
        type: "tool_execution_end",
        toolCallId: "call-bash-fail",
        toolName: "bash",
        result: {
          content: [
            { type: "text", text: "FAILED tests/test_login.py - AssertionError\nCommand exited with code 1" },
          ],
          structuredContent: {
            output: "FAILED tests/test_login.py - AssertionError\n",
            exit_code: 1,
            wall_time_seconds: 2,
            truncated: false,
          },
          isError: true,
        },
        isError: true,
        durationMs: 780,
      });

      assert.equal(chunks.length, 2);
      const resultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(resultEnv?.type, "tool_result");
      assert.equal(resultEnv?.stage, "CODER");
      assert.equal(resultEnv?.data.toolName, "bash");
      assert.equal(resultEnv?.data.command, "pytest -v");
      assert.equal(resultEnv?.data.cwd, "/root/target-repo");
      assert.equal(resultEnv?.data.exitCode, 1);
      assert.equal(resultEnv?.data.durationMs, 780);
      assert.equal(resultEnv?.data.isError, true);
      assert.ok(resultEnv?.data.stderr.includes("FAILED tests/test_login.py"));
      assert.equal(resultEnv?.data.toolCallId, "call-bash-fail");
    });
  });

});
