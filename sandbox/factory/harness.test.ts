import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

import { fauxProvider, fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import {
  runPlannerAgent,
  runCoderAgent,
  runReviewerAgent,
} from "./harness.ts";
import {
  LeastPrivilegeViolationError,
  createRoleTools,
} from "./tools.ts";
import { parseTelemetryEnvelope } from "./events.ts";

test("runPlannerAgent: throws LeastPrivilegeViolationError if forbidden tools are provided", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  try {
    // Pass tools with mutating write capability
    const badTools = [
      ...createRoleTools("planner", tmpDir),
      { name: "write", description: "write file", parameters: {}, execute: async () => ({ content: [] }) },
    ];

    await assert.rejects(
      () =>
        runPlannerAgent({
          workspaceDir: tmpDir,
          ticket: { id: "03", content: "Test ticket" },
          tools: badTools,
          model: faux.models[0],
          streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
        }),
      (err) => err instanceof LeastPrivilegeViolationError && /least-privilege/i.test(err.message)
    );
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runPlannerAgent: executes read-only inspection and produces structured plan", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  await fs.writeFile(path.join(tmpDir, "README.md"), "# Target Repo\nSome info.");

  const faux = fauxProvider();
  faux.setResponses([
    // First turn: Planner reads README.md
    fauxAssistantMessage([fauxToolCall("read", { path: "README.md" })]),
    // Second turn: Planner returns structured plan JSON
    fauxAssistantMessage(`
I inspected the workspace. Here is the plan:
\`\`\`json
{
  "ticketId": "03",
  "summary": "Implement OpenCode Go provider and agents",
  "affectedFiles": ["sandbox/factory/provider.ts", "sandbox/factory/tools.ts"],
  "testCommands": ["pnpm test"],
  "steps": ["Step 1", "Step 2"],
  "rationale": "Following ADR 0025"
}
\`\`\`
`),
  ]);

  try {
    const result = await runPlannerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "03", title: "OpenCode Go Provider", content: "Implement provider harness" },
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    assert.equal(result.plan.ticketId, "03");
    assert.deepEqual(result.plan.affectedFiles, [
      "sandbox/factory/provider.ts",
      "sandbox/factory/tools.ts",
    ]);
    assert.deepEqual(result.plan.testCommands, ["pnpm test"]);
    assert.equal(result.plan.steps.length, 2);

    // Verify messages captured the tool call interaction
    const toolCallMsg = result.messages.find(
      (m: any) =>
        m.role === "assistant" &&
        Array.isArray(m.content) &&
        m.content.some((c: any) => c.type === "toolCall" && c.name === "read")
    );
    assert.ok(toolCallMsg, "Planner should have executed read tool call");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runCoderAgent: executes with coding tools and writes files", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    // First turn: Coder uses write tool to create a new file
    fauxAssistantMessage([
      fauxToolCall("write", {
        path: "solution.txt",
        content: "Implemented solution",
      }),
    ]),
    // Second turn: Coder completes
    fauxAssistantMessage("I implemented the solution and created solution.txt."),
  ]);

  try {
    const result = await runCoderAgent({
      workspaceDir: tmpDir,
      ticket: { id: "03", content: "Implement solution" },
      plan: {
        ticketId: "03",
        summary: "Create solution",
        affectedFiles: ["solution.txt"],
        testCommands: ["pnpm test"],
        steps: ["Write solution.txt"],
        rawContent: "{}",
      },
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    assert.ok(result.summary.includes("created solution.txt"));
    const createdFile = await fs.readFile(path.join(tmpDir, "solution.txt"), "utf-8");
    assert.equal(createdFile, "Implemented solution");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runCoderAgent: incorporates retry diagnostics during self-correction", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage("I fixed the test failure indicated in diagnostics."),
  ]);

  try {
    const result = await runCoderAgent({
      workspaceDir: tmpDir,
      ticket: { id: "03", content: "Fix bug" },
      plan: {
        ticketId: "03",
        summary: "Fix bug",
        affectedFiles: ["src/index.ts"],
        testCommands: ["pnpm test"],
        steps: ["Fix index.ts"],
        rawContent: "{}",
      },
      diagnostics: "Error: Expected 42 but got 40 in test_calc",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    // Check that prompt included the diagnostics
    const userPrompt = result.messages.find((m: any) => m.role === "user");
    assert.ok(userPrompt);
    const userPromptText = JSON.stringify(userPrompt.content);
    assert.ok(
      userPromptText.includes("Expected 42 but got 40"),
      "User prompt to coder must include diagnostics"
    );
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runReviewerAgent: throws LeastPrivilegeViolationError if forbidden tools are provided", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  try {
    // Pass tools with mutating bash capability
    const badTools = [
      ...createRoleTools("reviewer", tmpDir),
      { name: "bash", description: "bash shell", parameters: {}, execute: async () => ({ content: [] }) },
    ];

    await assert.rejects(
      () =>
        runReviewerAgent({
          workspaceDir: tmpDir,
          ticket: { id: "03", content: "Review ticket" },
          plan: "Plan for 03",
          tools: badTools,
          model: faux.models[0],
          streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
        }),
      (err) => err instanceof LeastPrivilegeViolationError && /least-privilege/i.test(err.message)
    );
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runReviewerAgent: inspects workspace with read-only tools and emits review verdict", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage(`
\`\`\`json
{
  "verdict": "approved",
  "summary": "Clean implementation meeting all requirements",
  "specCompliance": {
    "passed": true,
    "details": "All requirements satisfied"
  },
  "standardsCompliance": {
    "passed": true,
    "details": "Compliant with repo standards"
  },
  "issues": []
}
\`\`\`
`),
  ]);

  try {
    const result = await runReviewerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "03", content: "Review ticket" },
      plan: "Plan for 03",
      diff: "diff --git a/a.ts b/a.ts\n+const x = 1;",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    assert.equal(result.verdict.verdict, "approved");
    assert.equal(result.verdict.specCompliance.passed, true);
    assert.equal(result.verdict.standardsCompliance.passed, true);
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("agent runners throw HarnessExecutionError when assistant run errors", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();
  // No responses queued causes stopReason: "error"
  faux.setResponses([]);

  try {
    await assert.rejects(
      () =>
        runPlannerAgent({
          workspaceDir: tmpDir,
          ticket: { id: "03", content: "Test ticket" },
          model: faux.models[0],
          streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
        }),
      (err: any) => err.name === "HarnessExecutionError" && /failed/i.test(err.message)
    );
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runPlannerAgent: subscribes to agent events, emits stage-attributed thinking, and strips <think> tags from output", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const chunks: string[] = [];
  const faux = fauxProvider();

  // Model outputs reasoning in <think> tags followed by plan
  faux.setResponses([
    fauxAssistantMessage(`<think>Inspecting dependencies and planning the seam modifications.</think>
\`\`\`json
{
  "ticketId": "02",
  "summary": "Implement reasoning telemetry",
  "affectedFiles": ["sandbox/factory/events.ts"],
  "testCommands": ["pnpm test"],
  "steps": ["Step 1"]
}
\`\`\``),
  ]);

  try {
    const result = await runPlannerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "02", content: "Implement reasoning telemetry" },
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
      telemetryStream: { write: (c: string) => chunks.push(c) },
    });

    assert.equal(result.plan.ticketId, "02");
    assert.deepEqual(result.plan.affectedFiles, ["sandbox/factory/events.ts"]);

    // Verify thinking envelopes were emitted over telemetryStream
    const thinkingEnvelopes = chunks
      .map((c) => parseTelemetryEnvelope(c))
      .filter((e) => e?.type === "thinking");

    assert.ok(thinkingEnvelopes.length >= 1, "Should emit thinking envelopes over telemetry stream");
    assert.equal(thinkingEnvelopes[0]?.stage, "PLANNER");
    assert.ok(typeof thinkingEnvelopes[0]?.data.durationMs === "number");

    // Verify that <think> was stripped from the response text
    const assistantContent = result.messages.find((m) => m.role === "assistant")?.content;
    const rawText = typeof assistantContent === "string" ? assistantContent : "";
    assert.ok(!result.plan.rawContent.includes("<think>"), "Implementation plan rawContent should strip <think> tag");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runCoderAgent: subscribes to agent events, streams CODER reasoning, and flushes before tool start", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const chunks: string[] = [];
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage([
      { type: "text", text: "<think>Let me run tests to see failure.</think>" },
      fauxToolCall("read", { path: "package.json" }),
    ]),
    fauxAssistantMessage("Implementation finished successfully."),
  ]);

  try {
    await runCoderAgent({
      workspaceDir: tmpDir,
      ticket: { id: "02", content: "Implement reasoning" },
      plan: {
        ticketId: "02",
        summary: "test",
        affectedFiles: ["package.json"],
        testCommands: ["pnpm test"],
        steps: ["step"],
        rawContent: "...",
      },
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
      telemetryStream: { write: (c: string) => chunks.push(c) },
    });

    const parsed = chunks.map((c) => parseTelemetryEnvelope(c)).filter(Boolean);
    const thinkingEnvs = parsed.filter((e) => e?.type === "thinking");
    const toolEnvs = parsed.filter((e) => e?.type === "tool_start");

    assert.ok(thinkingEnvs.length >= 1, "Should emit thinking envelopes for CODER");
    assert.equal(thinkingEnvs[0]?.stage, "CODER");
    assert.ok(toolEnvs.length >= 1, "Should emit tool_start envelope");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runReviewerAgent: subscribes to agent events and emits REVIEWER reasoning telemetry", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const chunks: string[] = [];
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage(`<think>Reviewing diff and checking against CONTEXT.md standards.</think>
\`\`\`json
{
  "verdict": "approved",
  "summary": "Looks great",
  "specCompliance": { "passed": true, "details": "ok" },
  "standardsCompliance": { "passed": true, "details": "ok" },
  "issues": []
}
\`\`\``),
  ]);

  try {
    const result = await runReviewerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "02", content: "Review ticket" },
      plan: "Plan for 02",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
      telemetryStream: { write: (c: string) => chunks.push(c) },
    });

    assert.equal(result.verdict.verdict, "approved");

    const thinkingEnvs = chunks
      .map((c) => parseTelemetryEnvelope(c))
      .filter((e) => e?.type === "thinking");

    assert.ok(thinkingEnvs.length >= 1, "Should emit thinking envelopes for REVIEWER");
    assert.equal(thinkingEnvs[0]?.stage, "REVIEWER");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runCoderAgent: captures bash tool invocations and emits tool_start and tool_result telemetry envelopes with command, cwd, exitCode, durationMs", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const chunks: string[] = [];
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage([
      fauxToolCall("bash", { command: "echo 'hello from bash'" }),
    ]),
    fauxAssistantMessage("I executed the bash command and tested the code."),
  ]);

  try {
    await runCoderAgent({
      workspaceDir: tmpDir,
      ticket: { id: "03", content: "Run bash command" },
      plan: {
        ticketId: "03",
        summary: "test",
        affectedFiles: [],
        testCommands: ["echo 'hello from bash'"],
        steps: ["run echo"],
        rawContent: "...",
      },
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
      telemetryStream: { write: (c: string) => chunks.push(c) },
    });

    const parsed = chunks.map((c) => parseTelemetryEnvelope(c)).filter(Boolean);
    const toolStartEnvs = parsed.filter((e) => e?.type === "tool_start" && e?.data?.toolName === "bash");
    const toolResultEnvs = parsed.filter((e) => e?.type === "tool_result" && e?.data?.toolName === "bash");

    assert.equal(toolStartEnvs.length, 1, "Should emit 1 tool_start envelope for bash");
    assert.equal(toolStartEnvs[0]?.stage, "CODER");
    assert.equal(toolStartEnvs[0]?.data.command, "echo 'hello from bash'");
    assert.equal(toolStartEnvs[0]?.data.cwd, tmpDir);

    assert.equal(toolResultEnvs.length, 1, "Should emit 1 tool_result envelope for bash");
    assert.equal(toolResultEnvs[0]?.stage, "CODER");
    assert.equal(toolResultEnvs[0]?.data.command, "echo 'hello from bash'");
    assert.equal(toolResultEnvs[0]?.data.cwd, tmpDir);
    assert.equal(toolResultEnvs[0]?.data.exitCode, 0);
    assert.equal(toolResultEnvs[0]?.data.isError, false);
    assert.ok(typeof toolResultEnvs[0]?.data.durationMs === "number");
    assert.ok(toolResultEnvs[0]?.data.output.includes("hello from bash"));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

