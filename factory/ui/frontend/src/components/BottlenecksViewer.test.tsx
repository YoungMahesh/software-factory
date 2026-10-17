import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BottlenecksViewer } from "./BottlenecksViewer";
import { AgentEvent } from "../types";

describe("BottlenecksViewer", () => {
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
        exitCode: 0,
        durationMs: 1800,
        output: "3 passed",
        toolCallId: "v-1",
      },
    },
  ];

  it("renders empty state when no events are provided", () => {
    render(<BottlenecksViewer events={[]} />);
    expect(screen.getByText(/no bottlenecks recorded/i)).toBeInTheDocument();
  });

  it("extracts completed operations and sorts them strictly in descending order of durationMs", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    const rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(4);

    // #1: pnpm build (4200ms)
    expect(within(rows[0]).getByText("#1")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/pnpm build/)).toBeInTheDocument();
    expect(within(rows[0]).getByText(/4\.2/)).toBeInTheDocument();

    // #2: LLM Thinking (2500ms)
    expect(within(rows[1]).getByText("#2")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Thinking/i)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/2\.5/)).toBeInTheDocument();

    // #3: pytest tests/ (1800ms)
    expect(within(rows[2]).getByText("#3")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/pytest tests\//)).toBeInTheDocument();
    expect(within(rows[2]).getByText(/1\.8/)).toBeInTheDocument();

    // #4: git status (45ms)
    expect(within(rows[3]).getByText("#4")).toBeInTheDocument();
    expect(within(rows[3]).getByText(/git status/)).toBeInTheDocument();
    expect(within(rows[3]).getByText(/45ms/)).toBeInTheDocument();
  });

  it("displays visual duration bars with relative percentage widths", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    const bars = screen.getAllByTestId("bottleneck-duration-bar");
    expect(bars).toHaveLength(4);

    // Longest is 4200ms -> 100%
    expect(bars[0]).toHaveStyle({ width: "100%" });

    // 2500ms / 4200ms -> ~60%
    const bar1Style = bars[1].getAttribute("style") || "";
    expect(bar1Style).toMatch(/width:\s*60%/);

    // 1800ms / 4200ms -> ~43%
    const bar2Style = bars[2].getAttribute("style") || "";
    expect(bar2Style).toMatch(/width:\s*43%/);
  });

  it("displays active execution banner with running spinner when a command is executing", () => {
    const runningEvents: AgentEvent[] = [
      ...sampleEvents,
      {
        type: "tool_start",
        stage: "VERIFIER",
        data: {
          toolName: "bash",
          command: "vitest run --coverage",
          toolCallId: "v-running",
        },
      },
    ];

    render(<BottlenecksViewer events={runningEvents} />);

    const activeBanner = screen.getByTestId("active-execution-banner");
    expect(activeBanner).toBeInTheDocument();
    expect(within(activeBanner).getByText(/vitest run --coverage/)).toBeInTheDocument();
    expect(within(activeBanner).getByTestId("active-running-spinner")).toBeInTheDocument();
  });

  it("does not display active banner when all operations are completed", () => {
    render(<BottlenecksViewer events={sampleEvents} />);
    expect(screen.queryByTestId("active-execution-banner")).not.toBeInTheDocument();
  });

  it("toggles hiding micro-commands under 100ms", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    // Initially all 4 rows are present (including 45ms git status)
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);
    expect(screen.getByText(/git status/)).toBeInTheDocument();

    const toggle = screen.getByRole("checkbox", { name: /hide micro-commands/i });
    expect(toggle).not.toBeChecked();

    // Enable hide micro-commands
    fireEvent.click(toggle);
    expect(toggle).toBeChecked();

    // Now git status (45ms) should be hidden, leaving 3 rows
    const filteredRows = screen.getAllByTestId("bottleneck-row");
    expect(filteredRows).toHaveLength(3);
    expect(screen.queryByText(/git status/)).not.toBeInTheDocument();

    // Uncheck toggle restores it
    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);
    expect(screen.getByText(/git status/)).toBeInTheDocument();
  });

  it("cross-references command metadata from tool_start when tool_result omits command", () => {
    const eventsWithStartMetadata: AgentEvent[] = [
      {
        type: "tool_start",
        stage: "CODER",
        data: { toolName: "bash", command: "pnpm dlx prisma migrate", toolCallId: "p-1" },
      },
      {
        type: "tool_result",
        stage: "CODER",
        data: { toolName: "bash", exitCode: 0, durationMs: 1200, toolCallId: "p-1" },
      },
    ];

    render(<BottlenecksViewer events={eventsWithStartMetadata} />);
    expect(screen.getByText(/pnpm dlx prisma migrate/)).toBeInTheDocument();
    expect(screen.getByText(/1\.20s \(1200ms\)/)).toBeInTheDocument();
  });

  it("preserves separate thinking blocks in the same stage when marked done", () => {
    const multiThinkingEvents: AgentEvent[] = [
      {
        type: "thinking",
        stage: "PLANNER",
        data: { delta: "Plan turn 1", done: true, durationMs: 900 },
      },
      {
        type: "thinking",
        stage: "PLANNER",
        data: { delta: "Plan turn 2", done: true, durationMs: 600 },
      },
    ];

    render(<BottlenecksViewer events={multiThinkingEvents} />);
    const rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("#1")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/0\.90s \(900ms\)/)).toBeInTheDocument();
    expect(within(rows[1]).getByText("#2")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/0\.60s \(600ms\)/)).toBeInTheDocument();
  });
});
