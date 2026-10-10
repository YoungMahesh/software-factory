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
  AgentEventStream,
  ThinkingBatchBuffer,
  ThinkingExtractor,
  type TelemetryEnvelope,
} from "./events.ts";

describe("Agent Event Stream Telemetry Emitter", () => {
  it("defines standard event prefix __SF_EVENT__:", () => {
    assert.equal(EVENT_PREFIX, "__SF_EVENT__:");
  });

  describe("formatTelemetryEnvelope", () => {
    it("formats thinking event into single-line JSON envelope", () => {
      const line = formatTelemetryEnvelope({
        type: "thinking",
        stage: "PLANNER",
        data: { delta: "Examining project architecture...\nLine 2" },
        timestamp: 1728547200.0,
      });

      assert.ok(line.startsWith(EVENT_PREFIX));
      assert.ok(line.endsWith("\n"));
      // Exactly one newline at the very end (single-line JSON)
      assert.equal(line.indexOf("\n"), line.length - 1);

      const jsonStr = line.slice(EVENT_PREFIX.length).trim();
      const parsed = JSON.parse(jsonStr);
      assert.equal(parsed.type, "thinking");
      assert.equal(parsed.stage, "PLANNER");
      assert.equal(parsed.data.delta, "Examining project architecture...\nLine 2");
      assert.equal(parsed.timestamp, 1728547200.0);
    });

    it("formats tool_start event with toolName and arguments", () => {
      const line = formatTelemetryEnvelope({
        type: "tool_start",
        stage: "CODER",
        data: {
          toolName: "bash",
          args: { command: "npm test" },
          toolCallId: "call-123",
        },
      });

      assert.ok(line.startsWith(EVENT_PREFIX));
      const parsed = JSON.parse(line.slice(EVENT_PREFIX.length).trim());
      assert.equal(parsed.type, "tool_start");
      assert.equal(parsed.stage, "CODER");
      assert.equal(parsed.data.toolName, "bash");
      assert.equal(parsed.data.args.command, "npm test");
      assert.equal(parsed.data.toolCallId, "call-123");
      assert.ok(typeof parsed.timestamp === "number");
    });

    it("formats tool_result event with result and isError flag", () => {
      const line = formatTelemetryEnvelope({
        type: "tool_result",
        stage: "VERIFIER",
        data: {
          toolName: "bash",
          result: "All 5 tests passed",
          isError: false,
          durationMs: 142,
        },
      });

      const parsed = JSON.parse(line.slice(EVENT_PREFIX.length).trim());
      assert.equal(parsed.type, "tool_result");
      assert.equal(parsed.stage, "VERIFIER");
      assert.equal(parsed.data.isError, false);
      assert.equal(parsed.data.durationMs, 142);
    });

    it("formats stage transition event", () => {
      const line = formatTelemetryEnvelope({
        type: "stage",
        stage: "REVIEWER",
        data: { ticket: "#42" },
      });

      const parsed = JSON.parse(line.slice(EVENT_PREFIX.length).trim());
      assert.equal(parsed.type, "stage");
      assert.equal(parsed.stage, "REVIEWER");
      assert.equal(parsed.data.ticket, "#42");
    });
  });

  describe("parseTelemetryEnvelope", () => {
    it("successfully parses valid envelope line", () => {
      const line =
        '__SF_EVENT__:{"type":"thinking","stage":"CODER","data":{"delta":"writing code"},"timestamp":123.4}\n';
      const parsed = parseTelemetryEnvelope(line);
      assert.ok(parsed !== null);
      assert.equal(parsed?.type, "thinking");
      assert.equal(parsed?.stage, "CODER");
      assert.equal(parsed?.data.delta, "writing code");
      assert.equal(parsed?.timestamp, 123.4);
    });

    it("returns null for non-envelope text", () => {
      assert.equal(parseTelemetryEnvelope("Standard build output line"), null);
      assert.equal(parseTelemetryEnvelope(""), null);
    });

    it("returns null for malformed JSON envelope", () => {
      assert.equal(parseTelemetryEnvelope("__SF_EVENT__:not-json\n"), null);
    });
  });

  describe("emitTelemetryEvent and typed helpers", () => {
    it("writes formatted envelope to custom stream", () => {
      const chunks: string[] = [];
      const mockStream = {
        write: (chunk: string) => {
          chunks.push(chunk);
          return true;
        },
      };

      emitTelemetryEvent(
        {
          type: "stage",
          stage: "PLANNER",
          data: { status: "started" },
        },
        { stream: mockStream }
      );

      assert.equal(chunks.length, 1);
      assert.ok(chunks[0].startsWith(EVENT_PREFIX));
      const parsed = parseTelemetryEnvelope(chunks[0]);
      assert.equal(parsed?.type, "stage");
      assert.equal(parsed?.stage, "PLANNER");
    });

    it("helper emitThinkingEvent emits formatted thinking envelope", () => {
      const chunks: string[] = [];
      emitThinkingEvent("Step 1 reasoning", "PLANNER", { turn: 1 }, {
        stream: { write: (c) => chunks.push(c) },
      });

      assert.equal(chunks.length, 1);
      const parsed = parseTelemetryEnvelope(chunks[0]);
      assert.equal(parsed?.type, "thinking");
      assert.equal(parsed?.stage, "PLANNER");
      assert.equal(parsed?.data.delta, "Step 1 reasoning");
      assert.equal(parsed?.data.turn, 1);
    });

    it("helper emitToolStartEvent and emitToolResultEvent emit tool lifecycle", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      emitToolStartEvent("edit", { path: "src/app.ts" }, "call-1", "CODER", { stream });
      emitToolResultEvent("edit", "file updated", false, "call-1", "CODER", 50, { stream });

      assert.equal(chunks.length, 2);
      const start = parseTelemetryEnvelope(chunks[0]);
      assert.equal(start?.type, "tool_start");
      assert.equal(start?.data.toolName, "edit");

      const result = parseTelemetryEnvelope(chunks[1]);
      assert.equal(result?.type, "tool_result");
      assert.equal(result?.data.result, "file updated");
      assert.equal(result?.data.durationMs, 50);
    });

    it("helper emitAttemptEvent formats self-correction attempt", () => {
      const chunks: string[] = [];
      emitAttemptEvent(2, 3, "CODER", { reason: "test failure" }, {
        stream: { write: (c) => chunks.push(c) },
      });

      assert.equal(chunks.length, 1);
      const parsed = parseTelemetryEnvelope(chunks[0]);
      assert.equal(parsed?.type, "attempt");
      assert.equal(parsed?.data.attempt, 2);
      assert.equal(parsed?.data.maxAttempts, 3);
      assert.equal(parsed?.data.reason, "test failure");
    });

    it("helper emitAttemptStartEvent formats attempt_start with attempt number and diagnostics reason", () => {
      const chunks: string[] = [];
      emitAttemptStartEvent(2, 2, "test failure", {
        summary: "Fixing failing test suites",
        diagnostics: "AssertionError: 404 != 200",
      }, "CODER", {
        stream: { write: (c) => chunks.push(c) },
      });

      assert.equal(chunks.length, 1);
      const parsed = parseTelemetryEnvelope(chunks[0]);
      assert.equal(parsed?.type, "attempt_start");
      assert.equal(parsed?.stage, "CODER");
      assert.equal(parsed?.data.attempt, 2);
      assert.equal(parsed?.data.maxRetries, 2);
      assert.equal(parsed?.data.maxAttempts, 3);
      assert.equal(parsed?.data.reason, "test failure");
      assert.equal(parsed?.data.summary, "Fixing failing test suites");
      assert.equal(parsed?.data.diagnostics, "AssertionError: 404 != 200");
    });

    it("helper emitReviewerRejectionEvent formats reviewer rejection diagnostics", () => {
      const chunks: string[] = [];
      emitReviewerRejectionEvent({
        verdict: "rejected",
        summary: "Missing input validation in auth route",
        remediation: "Add zod schema validation before processing credentials",
        issues: [{ severity: "error", description: "No validation", file: "src/auth.ts" }],
      }, "REVIEWER", {
        stream: { write: (c) => chunks.push(c) },
      });

      assert.equal(chunks.length, 1);
      const parsed = parseTelemetryEnvelope(chunks[0]);
      assert.equal(parsed?.type, "reviewer_rejection");
      assert.equal(parsed?.stage, "REVIEWER");
      assert.equal(parsed?.data.verdict, "rejected");
      assert.equal(parsed?.data.summary, "Missing input validation in auth route");
      assert.equal(parsed?.data.remediation, "Add zod schema validation before processing credentials");
      assert.equal(parsed?.data.issues.length, 1);
    });
  });

  describe("AgentEventStream class", () => {
    it("manages stage context and emits attributed events", () => {
      const chunks: string[] = [];
      const stream = new AgentEventStream({
        stage: "PLANNER",
        stream: { write: (c: string) => chunks.push(c) },
      });

      assert.equal(stream.getStage(), "PLANNER");

      stream.emitThinking("Deliberating...");
      stream.emitToolStart("read", { path: "package.json" }, "call-99");
      stream.emitToolResult("read", "{ ... }", false, "call-99", 25);

      assert.equal(chunks.length, 3);
      for (const chunk of chunks) {
        const env = parseTelemetryEnvelope(chunk);
        assert.equal(env?.stage, "PLANNER");
      }

      // Transition to CODER stage
      stream.emitStage("CODER", { step: "implementation" });
      assert.equal(stream.getStage(), "CODER");

      stream.emitThinking("Writing implementation...");
      assert.equal(chunks.length, 5);

      const stageEnv = parseTelemetryEnvelope(chunks[3]);
      assert.equal(stageEnv?.type, "stage");
      assert.equal(stageEnv?.stage, "CODER");

      const coderThinkEnv = parseTelemetryEnvelope(chunks[4]);
      assert.equal(coderThinkEnv?.type, "thinking");
      assert.equal(coderThinkEnv?.stage, "CODER");
    });

    it("buffers rapid thinking deltas and flushes on tool start", () => {
      const chunks: string[] = [];
      const stream = new AgentEventStream({
        stage: "CODER",
        stream: { write: (c: string) => chunks.push(c) },
        batchThinkingMs: 100,
      });

      // Stream multiple rapid tokens
      stream.bufferThinking("Thinking ");
      stream.bufferThinking("step ");
      stream.bufferThinking("1...");

      // Nothing emitted immediately
      assert.equal(chunks.length, 0);

      // Invoking a tool forces an immediate flush of pending thinking
      stream.emitToolStart("bash", { command: "ls" });

      assert.equal(chunks.length, 2);
      const thinkEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(thinkEnv?.type, "thinking");
      assert.equal(thinkEnv?.data.delta, "Thinking step 1...");

      const toolEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(toolEnv?.type, "tool_start");
      assert.equal(toolEnv?.data.toolName, "bash");
    });
  });

  describe("ThinkingBatchBuffer", () => {
    it("aggregates multiple tokens and flushes explicitly", () => {
      const flushed: string[] = [];
      const buffer = new ThinkingBatchBuffer({
        intervalMs: 100,
        onFlush: (chunk) => flushed.push(chunk),
      });

      buffer.append("Hello ");
      buffer.append("world!");
      assert.equal(flushed.length, 0);
      assert.equal(buffer.hasPending(), true);

      buffer.flush();
      assert.equal(flushed.length, 1);
      assert.equal(flushed[0], "Hello world!");
      assert.equal(buffer.hasPending(), false);
    });

    it("flushes automatically after interval timeout", async () => {
      const flushed: string[] = [];
      const buffer = new ThinkingBatchBuffer({
        intervalMs: 25,
        onFlush: (chunk) => flushed.push(chunk),
      });

      buffer.append("Token 1 ");
      buffer.append("Token 2");
      assert.equal(flushed.length, 0);

      await new Promise((r) => setTimeout(r, 40));
      assert.equal(flushed.length, 1);
      assert.equal(flushed[0], "Token 1 Token 2");
    });
  });

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

  describe("Semantic tool chips and diff previews telemetry", () => {
    it("read tool: suppresses large file bodies over stdout and records path and line count", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      // 1. Tool start
      emitToolStartEvent(
        "read",
        { path: "src/routes/index.tsx", offset: 1, limit: 100 },
        "call-read-1",
        "PLANNER",
        { stream }
      );

      const startEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(startEnv?.type, "tool_start");
      assert.equal(startEnv?.stage, "PLANNER");
      assert.equal(startEnv?.data.toolName, "read");
      assert.equal(startEnv?.data.path, "src/routes/index.tsx");
      assert.equal(startEnv?.data.toolCallId, "call-read-1");

      // 2. Large file content result (2,000 lines, ~100KB)
      const largeContent = Array.from({ length: 2000 }, (_, i) => `// Line ${i + 1}: export const item${i} = "data";\n`).join("");
      assert.ok(largeContent.length > 50000, "Content must be multikilobyte");

      emitToolResultEvent(
        "read",
        {
          content: [{ type: "text", text: largeContent }],
          structuredContent: largeContent,
        },
        false,
        "call-read-1",
        "PLANNER",
        15,
        { stream, path: "src/routes/index.tsx" }
      );

      const resultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(resultEnv?.type, "tool_result");
      assert.equal(resultEnv?.stage, "PLANNER");
      assert.equal(resultEnv?.data.toolName, "read");
      assert.equal(resultEnv?.data.path, "src/routes/index.tsx");
      assert.equal(resultEnv?.data.lineCount, 2000);
      assert.equal(resultEnv?.data.isError, false);

      // Verifies verbatim file text is NOT emitted over stdout
      const emittedChunk = chunks[1];
      assert.ok(!emittedChunk.includes("export const item0"), "Must NOT dump verbatim file body to stdout");
      assert.ok(!emittedChunk.includes("export const item1999"), "Must NOT dump verbatim file body to stdout");
      assert.ok(emittedChunk.length < 500, `Emitted chunk must be small summary envelope, got ${emittedChunk.length} bytes`);
    });

    it("write tool: reports target path and byte length written, suppressing raw content", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };
      const content = "x".repeat(32768); // 32KB

      // Tool start
      emitToolStartEvent(
        "write",
        { path: "src/generated/blob.bin", content },
        "call-write-1",
        "CODER",
        { stream }
      );

      const startEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(startEnv?.data.toolName, "write");
      assert.equal(startEnv?.data.path, "src/generated/blob.bin");
      assert.equal(startEnv?.data.bytes, 32768);
      // Suppresses serializing raw file content
      assert.ok(!chunks[0].includes("xxxxxxx"), "Must not serialize raw content in tool_start");
      assert.ok(chunks[0].length < 400);

      // Tool result
      emitToolResultEvent(
        "write",
        { content: [{ type: "text", text: "Successfully wrote to src/generated/blob.bin" }] },
        false,
        "call-write-1",
        "CODER",
        42,
        { stream, path: "src/generated/blob.bin", bytes: 32768 }
      );

      const resultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(resultEnv?.data.toolName, "write");
      assert.equal(resultEnv?.data.path, "src/generated/blob.bin");
      assert.equal(resultEnv?.data.bytes, 32768);
      assert.equal(resultEnv?.data.durationMs, 42);
      assert.ok(!chunks[1].includes("xxxxxxx"), "Must not serialize raw content in tool_result");
    });

    it("edit tool: extracts target path and generates unified patch diff, omitting verbose instructions", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      // Tool start with verbose edits
      emitToolStartEvent(
        "edit",
        {
          path: "src/components/Header.tsx",
          edits: [
            {
              oldText: "const TITLE = 'Old App Title';",
              newText: "const TITLE = 'New App Title';",
            },
          ],
        },
        "call-edit-1",
        "CODER",
        { stream }
      );

      const startEnv = parseTelemetryEnvelope(chunks[0]);
      assert.equal(startEnv?.data.toolName, "edit");
      assert.equal(startEnv?.data.path, "src/components/Header.tsx");
      // Verbose instructions (oldText/newText) omitted from payload
      assert.ok(!chunks[0].includes("Old App Title"), "Must omit verbose instructions from tool_start payload");

      // Tool result with unified patch diff
      const patch = "--- src/components/Header.tsx\n+++ src/components/Header.tsx\n@@ -1,3 +1,3 @@\n import React from 'react';\n-const TITLE = 'Old App Title';\n+const TITLE = 'New App Title';\n export default TITLE;\n";
      emitToolResultEvent(
        "edit",
        {
          content: [{ type: "text", text: "Successfully replaced 1 block(s) in src/components/Header.tsx." }],
          details: {
            patch,
            diff: " 1 import React from 'react';\n-2 const TITLE = 'Old App Title';\n+2 const TITLE = 'New App Title';\n 3 export default TITLE;",
          },
        },
        false,
        "call-edit-1",
        "CODER",
        55,
        { stream, path: "src/components/Header.tsx" }
      );

      const resultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(resultEnv?.data.toolName, "edit");
      assert.equal(resultEnv?.data.path, "src/components/Header.tsx");
      assert.ok(resultEnv?.data.diff, "Must include unified diff");
      assert.ok(resultEnv?.data.diff.includes("-const TITLE = 'Old App Title';"));
      assert.ok(resultEnv?.data.diff.includes("+const TITLE = 'New App Title';"));
      assert.equal(resultEnv?.data.isError, false);
      assert.equal(resultEnv?.data.durationMs, 55);
    });

    it("grep and diff tools: record target path and match/line counts, suppressing verbatim output", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      // Grep start and result
      emitToolStartEvent(
        "grep",
        { pattern: "useState", path: "src/components" },
        "call-grep-1",
        "PLANNER",
        { stream }
      );

      const grepMatches = [
        "src/components/Header.tsx:3: const [open, setOpen] = useState(false);",
        "src/components/Header.tsx:4: const [user, setUser] = useState(null);",
        "src/components/Footer.tsx:2: const [year, setYear] = useState(2026);",
      ].join("\n");

      emitToolResultEvent(
        "grep",
        { content: [{ type: "text", text: grepMatches }] },
        false,
        "call-grep-1",
        "PLANNER",
        20,
        { stream, path: "src/components", pattern: "useState" }
      );

      const grepResultEnv = parseTelemetryEnvelope(chunks[1]);
      assert.equal(grepResultEnv?.data.toolName, "grep");
      assert.equal(grepResultEnv?.data.pattern, "useState");
      assert.equal(grepResultEnv?.data.path, "src/components");
      assert.equal(grepResultEnv?.data.matchCount, 3);
      assert.ok(!chunks[1].includes("const [open, setOpen]"), "Must suppress verbatim grep lines from stdout");

      // Diff start and result
      emitToolStartEvent(
        "diff",
        { path: "src/utils.ts" },
        "call-diff-1",
        "REVIEWER",
        { stream }
      );

      const rawDiff = "--- a/src/utils.ts\n+++ b/src/utils.ts\n@@ -1,2 +1,3 @@\n+export const helper = () => true;\n";
      emitToolResultEvent(
        "diff",
        { content: [{ type: "text", text: rawDiff }] },
        false,
        "call-diff-1",
        "REVIEWER",
        30,
        { stream, path: "src/utils.ts" }
      );

      const diffResultEnv = parseTelemetryEnvelope(chunks[3]);
      assert.equal(diffResultEnv?.data.toolName, "diff");
      assert.equal(diffResultEnv?.data.path, "src/utils.ts");
      assert.equal(diffResultEnv?.data.lineCount, 4);
      assert.ok(!chunks[3].includes("export const helper"), "Must suppress verbatim diff text in chip payload");
    });

    it("subscribeAgentTelemetry: intercepts and sanitizes read, write, edit, grep, and diff tool calls end-to-end", () => {
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
        workspaceDir: "/workspace",
      });
      eventStream.subscribe(fakeAgent);

      // 1. Read tool call
      listener({
        type: "tool_execution_start",
        toolCallId: "call-read-sub",
        toolName: "read",
        args: { path: "package.json" },
      });
      listener({
        type: "tool_execution_end",
        toolCallId: "call-read-sub",
        toolName: "read",
        result: { content: [{ type: "text", text: "{\n  \"name\": \"app\",\n  \"version\": \"1.0.0\"\n}\n" }] },
        isError: false,
        durationMs: 12,
      });

      // 2. Edit tool call
      listener({
        type: "tool_execution_start",
        toolCallId: "call-edit-sub",
        toolName: "edit",
        args: {
          path: "src/index.ts",
          edits: [{ oldText: "const a = 1;", newText: "const a = 2;" }],
        },
      });
      listener({
        type: "tool_execution_end",
        toolCallId: "call-edit-sub",
        toolName: "edit",
        result: {
          content: [{ type: "text", text: "Successfully replaced 1 block(s) in src/index.ts." }],
          details: {
            patch: "--- src/index.ts\n+++ src/index.ts\n@@ -1 +1 @@\n-const a = 1;\n+const a = 2;\n",
          },
        },
        isError: false,
        durationMs: 25,
      });

      assert.equal(chunks.length, 4);

      // Read start & result
      const readStart = parseTelemetryEnvelope(chunks[0]);
      assert.equal(readStart?.data.toolName, "read");
      assert.equal(readStart?.data.path, "package.json");

      const readEnd = parseTelemetryEnvelope(chunks[1]);
      assert.equal(readEnd?.data.toolName, "read");
      assert.equal(readEnd?.data.path, "package.json");
      assert.equal(readEnd?.data.lineCount, 4);
      assert.ok(!chunks[1].includes("\"version\": \"1.0.0\""));

      // Edit start & result
      const editStart = parseTelemetryEnvelope(chunks[2]);
      assert.equal(editStart?.data.toolName, "edit");
      assert.equal(editStart?.data.path, "src/index.ts");
      assert.ok(!chunks[2].includes("const a = 1;"));

      const editEnd = parseTelemetryEnvelope(chunks[3]);
      assert.equal(editEnd?.data.toolName, "edit");
      assert.equal(editEnd?.data.path, "src/index.ts");
      assert.ok(editEnd?.data.diff.includes("+const a = 2;"));
    });

    it("edit tool: preserves failure error message when edit operation errors", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      emitToolResultEvent(
        "edit",
        { error: "Could not find unique match for replacement text", isError: true },
        true,
        "call-edit-err",
        "CODER",
        15,
        { stream, path: "src/bad.ts" }
      );

      const res = parseTelemetryEnvelope(chunks[0]);
      assert.equal(res?.data.toolName, "edit");
      assert.equal(res?.data.isError, true);
      assert.equal(res?.data.path, "src/bad.ts");
      assert.equal(res?.data.error, "Could not find unique match for replacement text");
      assert.equal(res?.data.result, "Could not find unique match for replacement text");
    });

    it("grep tool: counts match lines accurately and ignores trailing notice blocks", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      const grepOutputWithNotice = [
        "src/a.ts:10: const x = 1;",
        "src/b.ts:25: const x = 2;",
        "",
        "[10 matches limit reached. Use limit=20 for more]",
      ].join("\n");

      emitToolResultEvent(
        "grep",
        { content: [{ type: "text", text: grepOutputWithNotice }] },
        false,
        "call-grep-limit",
        "PLANNER",
        10,
        { stream, path: "src/", pattern: "const x" }
      );

      const res = parseTelemetryEnvelope(chunks[0]);
      assert.equal(res?.data.matchCount, 2);
    });
  });
});




