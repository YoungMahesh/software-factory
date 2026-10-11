import { describe, it, expect } from "vitest";
import { foldTelemetryEvents } from "./telemetryEvents";
import { ChatMessage, AgentEvent, Job } from "../types";

describe("foldTelemetryEvents", () => {
  it("returns original messages when events array is empty", () => {
    const initial: ChatMessage[] = [
      { id: "msg-1", role: "user", text: "Hello", timestamp: 1000 },
    ];
    const result = foldTelemetryEvents(initial, [], "job-1");
    expect(result).toBe(initial);
  });

  it("returns original messages when activeJobId is not provided", () => {
    const initial: ChatMessage[] = [
      { id: "msg-1", role: "user", text: "Hello", timestamp: 1000 },
    ];
    const events: AgentEvent[] = [{ type: "thinking", data: { delta: "thinking..." } }];
    const result = foldTelemetryEvents(initial, events, null);
    expect(result).toBe(initial);
  });

  it("creates a new assistant message if one does not exist for activeJobId", () => {
    const initial: ChatMessage[] = [
      { id: "msg-1", role: "user", text: "Build a navbar", timestamp: 1000 },
    ];
    const activeJob: Job = {
      id: "job-1",
      repo: "my-repo",
      feature: "navbar-feat",
      model: "test-model",
      vm: false,
      dev: true,
      status: "RUNNING",
      stage: "PLANNER",
      created_at: "2026-10-11T00:00:00Z",
      log_count: 0,
      event_count: 0,
    };
    const events: AgentEvent[] = [
      { type: "thinking", data: { delta: "Analyzing code..." } },
    ];

    const result = foldTelemetryEvents(initial, events, "job-1", activeJob);
    expect(result).toHaveLength(2);
    const assistantMsg = result.find((m) => m.jobId === "job-1");
    expect(assistantMsg).toBeDefined();
    expect(assistantMsg?.role).toBe("assistant");
    expect(assistantMsg?.stage).toBe("PLANNER");
    expect(assistantMsg?.thinking?.text).toBe("Analyzing code...");
    expect(assistantMsg?.thinking?.done).toBe(false);
  });

  it("accumulates thinking deltas into reasoning text across multiple events", () => {
    const initial: ChatMessage[] = [
      {
        id: "assistant-job-1",
        role: "assistant",
        jobId: "job-1",
        timestamp: 1000,
        text: "Executing job",
        thinking: {
          text: "Step 1: Inspect. ",
          done: false,
        },
      },
    ];

    const events: AgentEvent[] = [
      { type: "thinking", data: { delta: "Step 2: Plan. " } },
      { type: "thinking", data: { delta: "Step 3: Implement.", durationMs: 1250, done: true } },
    ];

    const result = foldTelemetryEvents(initial, events, "job-1");
    expect(result).toHaveLength(1);
    expect(result[0].thinking?.text).toBe("Step 1: Inspect. Step 2: Plan. Step 3: Implement.");
    expect(result[0].thinking?.durationMs).toBe(1250);
    expect(result[0].thinking?.done).toBe(true);
  });

  it("folds tool_result events into stepChips with formatted labels", () => {
    const initial: ChatMessage[] = [
      {
        id: "assistant-job-1",
        role: "assistant",
        jobId: "job-1",
        timestamp: 1000,
        stepChips: [],
      },
    ];

    const events: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "PLANNER",
        data: {
          toolCallId: "call-1",
          toolName: "read",
          path: "src/App.tsx",
          lineCount: 42,
        },
      },
    ];

    const result = foldTelemetryEvents(initial, events, "job-1");
    expect(result[0].stepChips).toHaveLength(1);
    expect(result[0].stepChips![0]).toEqual({
      id: "call-1",
      toolName: "read",
      label: "[Read src/App.tsx (42 lines)]",
      data: events[0].data,
      stage: "PLANNER",
      toolCallId: "call-1",
    });
  });

  it("deduplicates tool chips with identical toolCallId", () => {
    const initial: ChatMessage[] = [
      {
        id: "assistant-job-1",
        role: "assistant",
        jobId: "job-1",
        timestamp: 1000,
        stepChips: [
          {
            id: "call-1",
            toolName: "read",
            label: "[Read src/App.tsx]",
            data: {},
            toolCallId: "call-1",
          },
        ],
      },
    ];

    const duplicateEvents: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "PLANNER",
        data: {
          toolCallId: "call-1",
          toolName: "read",
          path: "src/App.tsx",
        },
      },
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolCallId: "call-2",
          toolName: "write",
          path: "src/Button.tsx",
          bytes: 120,
        },
      },
    ];

    const result = foldTelemetryEvents(initial, duplicateEvents, "job-1");
    expect(result[0].stepChips).toHaveLength(2);
    expect(result[0].stepChips![0].id).toBe("call-1");
    expect(result[0].stepChips![1].id).toBe("call-2");
    expect(result[0].stepChips![1].label).toBe("[Write src/Button.tsx (120 B)]");
  });

  it("does not mutate the input messages array or original message objects", () => {
    const initialMsg: ChatMessage = {
      id: "assistant-job-1",
      role: "assistant",
      jobId: "job-1",
      timestamp: 1000,
      stepChips: [],
    };
    const initial: ChatMessage[] = [initialMsg];

    const events: AgentEvent[] = [
      { type: "thinking", data: { delta: "Testing immutability" } },
      {
        type: "tool_result",
        data: { toolCallId: "call-mut", toolName: "read", path: "test.ts" },
      },
    ];

    const result = foldTelemetryEvents(initial, events, "job-1");
    expect(result).not.toBe(initial);
    expect(result[0]).not.toBe(initialMsg);
    expect(initialMsg.stepChips).toHaveLength(0);
    expect(initialMsg.thinking).toBeUndefined();
  });
});
