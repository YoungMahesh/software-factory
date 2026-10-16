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
  loadPromptTemplate,
  renderPromptTemplate,
  PLANNER_SYSTEM_PROMPT,
  CODER_SYSTEM_PROMPT,
  REVIEWER_SYSTEM_PROMPT,
} from "./harness/prompts.ts";
import {
  LeastPrivilegeViolationError,
  createRoleTools,
} from "./tools.ts";
import { parseTelemetryEnvelope } from "./events.ts";


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

test("runPlannerAgent: receives adrsContent in prompt and ingests ADR context", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage(`
\`\`\`json
{
  "ticketId": "05",
  "summary": "Adheres to ADR 0001 SPA architecture",
  "affectedFiles": ["app/routes/index.tsx"],
  "testCommands": ["pnpm test"],
  "steps": ["Create route"],
  "rationale": "Complies strictly with ADR 0001"
}
\`\`\`
`),
  ]);

  try {
    const result = await runPlannerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "05", content: "Implement route" },
      adrsContent: "### 0001-tanstack-start-spa-architecture.md\n\nMust use TanStack Start file-based routing.",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    const userPrompt = result.messages.find((m: any) => m.role === "user");
    assert.ok(userPrompt);
    const userPromptText = JSON.stringify(userPrompt.content);
    assert.ok(
      userPromptText.includes("0001-tanstack-start-spa-architecture.md"),
      "Planner prompt must include bundled ADR content"
    );
    assert.ok(
      userPromptText.includes("Must use TanStack Start file-based routing"),
      "Planner prompt must include ADR specifics"
    );
    assert.equal(result.plan.ticketId, "05");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runReviewerAgent: receives adrsContent and rejects diff when standardsCompliance fails due to ADR violation", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage(`
\`\`\`json
{
  "verdict": "rejected",
  "summary": "Violates ADR 0001 by introducing prohibited Redux store",
  "specCompliance": {
    "passed": true,
    "details": "Layout implemented"
  },
  "standardsCompliance": {
    "passed": false,
    "details": "Violates ADR 0001: Redux is prohibited in favor of React state primitives and TanStack Query"
  },
  "issues": [
    {
      "severity": "blocker",
      "description": "Prohibited Redux store introduced in src/store.ts",
      "file": "src/store.ts"
    }
  ],
  "remediation": "Remove Redux store and replace with local component state and TanStack Query cache per ADR 0001."
}
\`\`\`
`),
  ]);

  try {
    const result = await runReviewerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "05", content: "Implement state management" },
      plan: "Plan for 05",
      diff: "diff --git a/src/store.ts b/src/store.ts\n+import { createStore } from 'redux';",
      adrsContent: "### 0001-tanstack-start-spa-architecture.md\n\nAvoid Redux store in favor of React state primitives.",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    const userPrompt = result.messages.find((m: any) => m.role === "user");
    assert.ok(userPrompt);
    const userPromptText = JSON.stringify(userPrompt.content);
    assert.ok(
      userPromptText.includes("0001-tanstack-start-spa-architecture.md"),
      "Reviewer prompt must include bundled ADR content"
    );

    assert.equal(result.verdict.verdict, "rejected");
    assert.equal(result.verdict.specCompliance.passed, true);
    assert.equal(result.verdict.standardsCompliance.passed, false);
    assert.ok(result.verdict.issues.some((i) => i.severity === "blocker" && i.description.includes("Redux")));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("runReviewerAgent: enforces rejection if standardsCompliance failed even if model verdict claims approved", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "harness-test-"));
  const faux = fauxProvider();

  faux.setResponses([
    fauxAssistantMessage(`
\`\`\`json
{
  "verdict": "approved",
  "summary": "Contradictory output test",
  "specCompliance": {
    "passed": true,
    "details": "Pass"
  },
  "standardsCompliance": {
    "passed": false,
    "details": "Contradicts ADR 0001 architectural decisions"
  },
  "issues": [
    {
      "severity": "blocker",
      "description": "ADR violation"
    }
  ]
}
\`\`\`
`),
  ]);

  try {
    const result = await runReviewerAgent({
      workspaceDir: tmpDir,
      ticket: { id: "05", content: "Review ticket" },
      plan: "Plan for 05",
      adrsContent: "### 0001-tanstack-start-spa-architecture.md\n\nBaseline ADR.",
      model: faux.models[0],
      streamFn: (m, ctx, opt) => faux.provider.streamSimple(m, ctx, opt),
    });

    assert.equal(
      result.verdict.verdict,
      "rejected",
      "Review verdict must be forced to rejected when standardsCompliance fails"
    );
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("loadPromptTemplate: loads markdown prompt file for planner, coder, and reviewer", () => {
  assert.ok(PLANNER_SYSTEM_PROMPT.includes("Planner Agent in the Software Factory assembly line"));
  assert.ok(PLANNER_SYSTEM_PROMPT.includes('"ticketId": "<ticket-id>"'));
  assert.ok(CODER_SYSTEM_PROMPT.includes("Coder Agent in the Software Factory assembly line"));
  assert.ok(REVIEWER_SYSTEM_PROMPT.includes("Reviewer Agent in the Software Factory assembly line"));
  assert.ok(REVIEWER_SYSTEM_PROMPT.includes('"verdict": "approved" | "rejected"'));
});

test("loadPromptTemplate: caches loaded prompt templates and supports reload", () => {
  const loaded1 = loadPromptTemplate("planner_system");
  const loaded2 = loadPromptTemplate("planner_system");
  assert.equal(loaded1, loaded2);

  const reloaded = loadPromptTemplate("planner_system", true);
  assert.equal(reloaded, loaded1);
});

test("loadPromptTemplate: throws descriptive error for missing template", () => {
  assert.throws(
    () => loadPromptTemplate("non_existent_prompt_template_xyz"),
    (err: any) =>
      err instanceof Error &&
      err.message.includes("non_existent_prompt_template_xyz") &&
      err.message.includes("not found")
  );
});

test("renderPromptTemplate: substitutes double-curly brace variables and leaves unreferenced/json braces intact", () => {
  const rendered = renderPromptTemplate("planner_system", {
    custom_var: "custom_value",
  });
  // Unaltered JSON schemas with single curly braces remain intact
  assert.ok(rendered.includes('"ticketId": "<ticket-id>"'));
  assert.ok(rendered.includes("Planner Agent"));
});
