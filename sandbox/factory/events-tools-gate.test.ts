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


describe("Agent Event Stream Telemetry Emitter - Tools & Gate", () => {
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

  describe("delivery_gate telemetry events", () => {
    it("emits formatted delivery_gate envelope for gate initialization", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      const eventData: DeliveryGateEventData = {
        pullRequestNumber: 42,
        pull_request_number: 42,
        pullRequestUrl: "https://github.com/org/repo/pull/42",
        pull_request_url: "https://github.com/org/repo/pull/42",
        html_url: "https://github.com/org/repo/pull/42",
        branch: "factory/feature-auth",
        title: "feat(auth): implement user authentication",
        draft: true,
      };

      const emitted = emitDeliveryGateEvent(eventData, undefined, { stream });
      assert.ok(emitted.startsWith(EVENT_PREFIX));
      assert.equal(chunks.length, 1);

      const parsed = parseTelemetryEnvelope<DeliveryGateEventData>(chunks[0]);
      assert.ok(parsed);
      assert.equal(parsed.type, "delivery_gate");
      assert.equal(parsed.data.pull_number, 42);
      assert.equal(parsed.data.pullRequestNumber, 42);
      assert.equal(parsed.data.pull_request_number, 42);
      assert.equal(parsed.data.pullRequestUrl, "https://github.com/org/repo/pull/42");
      assert.equal(parsed.data.branch, "factory/feature-auth");
      assert.equal(parsed.data.title, "feat(auth): implement user authentication");
      assert.equal(parsed.data.draft, true);
      assert.equal(parsed.data.ready_for_review, undefined);
    });

    it("emits formatted delivery_gate envelope for gate finalization", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };

      const eventData: DeliveryGateEventData = {
        pullRequestNumber: 42,
        pull_request_number: 42,
        pullRequestUrl: "https://github.com/org/repo/pull/42",
        pull_request_url: "https://github.com/org/repo/pull/42",
        html_url: "https://github.com/org/repo/pull/42",
        branch: "factory/feature-auth",
        title: "feat(auth): implement user authentication",
        ready_for_review: true,
      };

      const emitted = emitDeliveryGateEvent(eventData, undefined, { stream });
      assert.ok(emitted.startsWith(EVENT_PREFIX));

      const parsed = parseTelemetryEnvelope<DeliveryGateEventData>(chunks[0]);
      assert.ok(parsed);
      assert.equal(parsed.type, "delivery_gate");
      assert.equal(parsed.data.pull_number, 42);
      assert.equal(parsed.data.pullRequestNumber, 42);
      assert.equal(parsed.data.pull_request_number, 42);
      assert.equal(parsed.data.pullRequestUrl, "https://github.com/org/repo/pull/42");
      assert.equal(parsed.data.branch, "factory/feature-auth");
      assert.equal(parsed.data.ready_for_review, true);
      assert.equal(parsed.data.draft, undefined);
    });

    it("AgentEventStream emits delivery_gate event through stream", () => {
      const chunks: string[] = [];
      const stream = { write: (c: string) => chunks.push(c) };
      const aes = new AgentEventStream({ stream });

      aes.emitDeliveryGate({
        pullRequestNumber: 99,
        pull_request_number: 99,
        pullRequestUrl: "https://github.com/org/repo/pull/99",
        pull_request_url: "https://github.com/org/repo/pull/99",
        html_url: "https://github.com/org/repo/pull/99",
        branch: "factory/issue-99",
        title: "feat: resolve #99 - Fix login",
        draft: true,
      });

      assert.equal(chunks.length, 1);
      const parsed = parseTelemetryEnvelope<DeliveryGateEventData>(chunks[0]);
      assert.ok(parsed);
      assert.equal(parsed.type, "delivery_gate");
      assert.equal(parsed.data.pullRequestNumber, 99);
      assert.equal(parsed.data.draft, true);
    });
  });

});
