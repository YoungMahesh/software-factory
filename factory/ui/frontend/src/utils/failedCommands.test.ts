import { describe, it, expect } from "vitest";
import { extractFailedCommands } from "./failedCommands";
import { AgentEvent } from "../types";

describe("extractFailedCommands", () => {
  it("returns empty array for empty or missing events", () => {
    expect(extractFailedCommands([])).toEqual([]);
    expect(extractFailedCommands(undefined as any)).toEqual([]);
  });

  it("isolates non-zero exit code bash tools in CODER and VERIFIER stages", () => {
    const events: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm build",
          cwd: "/workspace",
          exitCode: 1,
          durationMs: 350,
          output: "tsc: not found",
          stderr: "tsc: not found",
          isError: true,
          toolCallId: "call-1",
        },
      },
      {
        type: "tool_result",
        stage: "VERIFIER",
        data: {
          toolName: "bash",
          command: "pytest tests/test_app.py",
          cwd: "/workspace",
          exitCode: 2,
          durationMs: 820,
          output: "FAILED test_app.py",
          stderr: "FAILED test_app.py",
          isError: true,
          toolCallId: "call-2",
        },
      },
    ];

    const result = extractFailedCommands(events);
    expect(result).toHaveLength(2);

    expect(result[0]).toMatchObject({
      id: "call-1",
      command: "pnpm build",
      cwd: "/workspace",
      stage: "CODER",
      exitCode: 1,
      durationMs: 350,
      stderr: "tsc: not found",
      isError: true,
    });

    expect(result[1]).toMatchObject({
      id: "call-2",
      command: "pytest tests/test_app.py",
      cwd: "/workspace",
      stage: "VERIFIER",
      exitCode: 2,
      durationMs: 820,
      stderr: "FAILED test_app.py",
      isError: true,
    });
  });

  it("excludes exit code 0 bash commands", () => {
    const events: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm test",
          exitCode: 0,
          isError: false,
          output: "PASS",
        },
      },
    ];

    expect(extractFailedCommands(events)).toEqual([]);
  });

  it("excludes read-only and non-bash tools even if error", () => {
    const events: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "read",
          path: "/workspace/missing.ts",
          isError: true,
          exitCode: 1,
        },
      },
      {
        type: "tool_result",
        stage: "PLANNER",
        data: {
          toolName: "grep",
          pattern: "foo",
          isError: true,
        },
      },
    ];

    expect(extractFailedCommands(events)).toEqual([]);
  });

  it("excludes bash tools executed in stages other than CODER and VERIFIER", () => {
    const events: AgentEvent[] = [
      {
        type: "tool_result",
        stage: "PLANNER",
        data: {
          toolName: "bash",
          command: "ls -la",
          exitCode: 1,
          isError: true,
        },
      },
      {
        type: "tool_result",
        stage: "REVIEWER",
        data: {
          toolName: "bash",
          command: "git diff",
          exitCode: 1,
          isError: true,
        },
      },
    ];

    expect(extractFailedCommands(events)).toEqual([]);
  });
});
