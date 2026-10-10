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
  AgentEventStream,
  ThinkingBatchBuffer,
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
});
