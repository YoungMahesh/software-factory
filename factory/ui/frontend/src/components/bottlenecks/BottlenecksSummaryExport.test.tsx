import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { BottlenecksViewer } from "../BottlenecksViewer";
import { RepoBottlenecksTable } from "./RepoBottlenecksTable";
import { AgentEvent, RepoBottleneck } from "../../types";

describe("BottlenecksSummaryExport", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  const sampleEvents: AgentEvent[] = [
    {
      type: "thinking",
      stage: "PLANNER",
      data: { delta: "Drafting plan", durationMs: 2500, done: true },
    },
    {
      type: "tool_start",
      stage: "CODER",
      data: { toolName: "bash", command: "git status", toolCallId: "c-1" },
    },
    {
      type: "tool_result",
      stage: "CODER",
      data: {
        toolName: "bash",
        command: "git status",
        exitCode: 0,
        durationMs: 45,
        output: "clean",
        toolCallId: "c-1",
      },
    },
    {
      type: "tool_start",
      stage: "CODER",
      data: { toolName: "bash", command: "pnpm build", toolCallId: "c-2" },
    },
    {
      type: "tool_result",
      stage: "CODER",
      data: {
        toolName: "bash",
        command: "pnpm build",
        exitCode: 0,
        durationMs: 4200,
        output: "Built in 4.2s",
        toolCallId: "c-2",
      },
    },
    {
      type: "tool_start",
      stage: "VERIFIER",
      data: { toolName: "bash", command: "pytest tests/", toolCallId: "v-1" },
    },
    {
      type: "tool_result",
      stage: "VERIFIER",
      data: {
        toolName: "bash",
        command: "pytest tests/",
        exitCode: 1,
        isError: true,
        durationMs: 1800,
        output: "1 failed",
        toolCallId: "v-1",
      },
    },
  ];

  it("renders Copy Summary button with id and initial label", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    const copyBtn = document.getElementById("btn-copy-bottlenecks-summary");
    expect(copyBtn).toBeInTheDocument();
    expect(copyBtn).toHaveTextContent("Copy Summary");
  });

  it("formats the active bottleneck list into a markdown table and copies it to clipboard", async () => {
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    render(<BottlenecksViewer events={sampleEvents} />);

    const copyBtn = screen.getByTestId("btn-copy-bottlenecks-summary");
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextSpy).toHaveBeenCalledTimes(1);
    const copiedText = writeTextSpy.mock.calls[0][0];

    // Verify markdown headers and rows
    expect(copiedText).toContain("| Rank | Category | Stage | Operation | Duration | Status |");
    expect(copiedText).toContain("| ---: | :--- | :--- | :--- | ---: | :--- |");
    expect(copiedText).toContain("| 1 | Build / Compile | CODER | `pnpm build` | 4.20s (4200ms) | Exit 0 |");
    expect(copiedText).toContain("| 2 | LLM Thinking | PLANNER | LLM Thinking (PLANNER) | 2.50s (2500ms) | Success |");
    expect(copiedText).toContain("| 3 | Test Suite | VERIFIER | `pytest tests/` | 1.80s (1800ms) | Exit 1 |");
    expect(copiedText).toContain("| 4 | Git / VCS | CODER | `git status` | 0.04s (45ms) | Exit 0 |");
  });

  it("provides visual feedback by switching to 'Copied' for 2 seconds", async () => {
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    render(<BottlenecksViewer events={sampleEvents} />);

    const copyBtn = screen.getByTestId("btn-copy-bottlenecks-summary");
    expect(copyBtn).toHaveTextContent("Copy Summary");

    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(copyBtn).toHaveTextContent("Copied");

    // Advance 1999ms - should still be "Copied"
    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(copyBtn).toHaveTextContent("Copied");

    // Advance 1ms more (2000ms total) - should revert to "Copy Summary"
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(copyBtn).toHaveTextContent("Copy Summary");
  });

  it("copies only filtered operations when stage or micro-command filters are active", async () => {
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    render(<BottlenecksViewer events={sampleEvents} />);

    // Filter to VERIFIER stage
    const verifierPill = screen.getByTestId("stage-filter-verifier");
    fireEvent.click(verifierPill);

    const copyBtn = screen.getByTestId("btn-copy-bottlenecks-summary");
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    const copiedText = writeTextSpy.mock.calls[0][0];
    // Only verifier command should be in the exported table
    expect(copiedText).toContain("`pytest tests/`");
    expect(copiedText).not.toContain("`pnpm build`");
    expect(copiedText).not.toContain("`git status`");
    expect(copiedText).not.toContain("LLM Thinking");
  });

  it("copies repository aggregated bottlenecks table when in RepoBottlenecksTable", async () => {
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    const bottlenecks: RepoBottleneck[] = [
      {
        command: "pnpm install",
        category: "Package Install",
        stage: "CODER",
        count: 5,
        invocation_count: 5,
        total_duration_ms: 15000,
        avg_duration_ms: 3000,
        max_duration_ms: 4500,
      },
    ];

    render(<RepoBottlenecksTable repo="test-org/test-repo" bottlenecks={bottlenecks} />);

    const copyBtn = screen.getByTestId("btn-copy-repo-bottlenecks-summary");
    expect(copyBtn).toBeInTheDocument();
    expect(copyBtn).toHaveTextContent("Copy Summary");

    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextSpy).toHaveBeenCalledTimes(1);
    const copiedText = writeTextSpy.mock.calls[0][0];

    expect(copiedText).toContain("| Rank | Operation | Category | Stage | Total Duration | Invocations | Avg Duration | Max Duration |");
    expect(copiedText).toContain("| 1 | `pnpm install` | Package Install | CODER | 15.00s | 5 | 3.00s | 4.50s |");

    expect(copyBtn).toHaveTextContent("Copied");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(copyBtn).toHaveTextContent("Copy Summary");
  });
});
