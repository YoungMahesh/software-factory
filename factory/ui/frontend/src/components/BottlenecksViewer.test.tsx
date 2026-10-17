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
    expect(within(rows[1]).getByTestId("bottleneck-title")).toHaveTextContent(/Thinking/i);
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

  it("displays infrastructure category badges, stage badges, and exit code indicators", () => {
    const errorEvents: AgentEvent[] = [
      ...sampleEvents,
      {
        type: "tool_result",
        stage: "REVIEWER",
        data: {
          toolName: "bash",
          command: "pnpm install left-pad",
          exitCode: 1,
          durationMs: 800,
          isError: true,
          output: "npm ERR! 404 Not Found",
          toolCallId: "r-err",
        },
      },
    ];

    render(<BottlenecksViewer events={errorEvents} />);

    const rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(5);

    // Verify category badges
    const categoryBadges = screen.getAllByTestId("category-badge");
    const badgeTexts = categoryBadges.map((b) => b.textContent?.trim());
    expect(badgeTexts).toContain("Build / Compile"); // pnpm build
    expect(badgeTexts).toContain("LLM Thinking"); // thinking
    expect(badgeTexts).toContain("Test Suite"); // pytest
    expect(badgeTexts).toContain("Package Install"); // pnpm install left-pad
    expect(badgeTexts).toContain("Git / VCS"); // git status

    // Verify stage badges
    const stageBadges = screen.getAllByTestId("stage-badge");
    const stages = stageBadges.map((s) => s.textContent?.trim());
    expect(stages).toContain("PLANNER");
    expect(stages).toContain("CODER");
    expect(stages).toContain("VERIFIER");
    expect(stages).toContain("REVIEWER");

    // Verify exit code indicators
    const exitIndicators = screen.getAllByTestId("exit-code-indicator");
    expect(exitIndicators.length).toBe(4); // 4 command operations
    // Success exit code 0
    expect(exitIndicators.some((el) => el.textContent?.includes("exit 0"))).toBe(true);
    // Failure exit code 1
    const failureIndicator = exitIndicators.find((el) => el.textContent?.includes("exit 1"));
    expect(failureIndicator).toBeInTheDocument();
    expect(failureIndicator?.className).toMatch(/bg-coral\/10/);
  });

  it("filters items interactively with stage filter pills", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    // Initially all 4 items are displayed
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);

    // Filter by Planner
    const plannerPill = screen.getByTestId("stage-filter-planner");
    fireEvent.click(plannerPill);
    let rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByTestId("bottleneck-title")).toHaveTextContent(/Thinking/i);

    // Filter by Coder
    const coderPill = screen.getByTestId("stage-filter-coder");
    fireEvent.click(coderPill);
    rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText(/pnpm build/)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/git status/)).toBeInTheDocument();

    // Filter by Verifier
    const verifierPill = screen.getByTestId("stage-filter-verifier");
    fireEvent.click(verifierPill);
    rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText(/pytest tests\//)).toBeInTheDocument();

    // Filter by Reviewer (none)
    const reviewerPill = screen.getByTestId("stage-filter-reviewer");
    fireEvent.click(reviewerPill);
    expect(screen.queryAllByTestId("bottleneck-row")).toHaveLength(0);
    expect(screen.getByText(/no operations match/i)).toBeInTheDocument();

    // Reset back to All
    const allPill = screen.getByTestId("stage-filter-all");
    fireEvent.click(allPill);
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);
  });

  it("isolates shell commands vs LLM thinking phases with category toggle buttons", () => {
    render(<BottlenecksViewer events={sampleEvents} />);

    // Initially All (4 rows)
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);

    // Switch to Commands only
    const commandsToggle = screen.getByTestId("category-toggle-commands");
    fireEvent.click(commandsToggle);
    let rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(3);
    expect(screen.queryByText(/LLM Thinking/i)).not.toBeInTheDocument();

    // Switch to Thinking only
    const thinkingToggle = screen.getByTestId("category-toggle-thinking");
    fireEvent.click(thinkingToggle);
    rows = screen.getAllByTestId("bottleneck-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByTestId("bottleneck-title")).toHaveTextContent(/Thinking/i);
    expect(screen.queryByText(/pnpm build/)).not.toBeInTheDocument();

    // Switch back to All
    const allToggle = screen.getByTestId("category-toggle-all");
    fireEvent.click(allToggle);
    expect(screen.getAllByTestId("bottleneck-row")).toHaveLength(4);
  });

  it("expands a command card to display working directory, command string, and highlighted stdout/stderr", () => {
    const detailedEvents: AgentEvent[] = [
      {
        type: "tool_start",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm test",
          cwd: "/root/workspace/app",
          toolCallId: "cmd-det",
        },
      },
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm test",
          cwd: "/root/workspace/app",
          exitCode: 1,
          durationMs: 3400,
          output: "Running test suite\nFAIL src/index.test.ts\nError: AssertionError\nTests passed: 0",
          toolCallId: "cmd-det",
        },
      },
    ];

    render(<BottlenecksViewer events={detailedEvents} />);

    // Initially collapsed
    expect(screen.queryByTestId("bottleneck-expanded-details")).not.toBeInTheDocument();
    expect(screen.queryByTestId("expanded-cwd")).not.toBeInTheDocument();

    // Click card header to expand
    const cardHeader = screen.getByTestId("bottleneck-card-header");
    fireEvent.click(cardHeader);

    // Details are now visible
    expect(screen.getByTestId("bottleneck-expanded-details")).toBeInTheDocument();
    expect(screen.getByTestId("expanded-cwd")).toHaveTextContent("/root/workspace/app");
    expect(screen.getByTestId("expanded-command-string")).toHaveTextContent("pnpm test");

    // Output and highlighted error lines
    const outputContainer = screen.getByTestId("expanded-output");
    expect(outputContainer).toBeInTheDocument();
    const errorLines = within(outputContainer).getAllByTestId("stderr-line");
    expect(errorLines).toHaveLength(2); // "FAIL src/index.test.ts" and "Error: AssertionError"
    expect(errorLines[0]).toHaveTextContent("FAIL src/index.test.ts");
    expect(errorLines[1]).toHaveTextContent("Error: AssertionError");

    // Click expand button to collapse
    const expandBtn = screen.getByTestId("bottleneck-expand-btn");
    fireEvent.click(expandBtn);
    expect(screen.queryByTestId("bottleneck-expanded-details")).not.toBeInTheDocument();
  });

  it("expands a thinking block to display the complete reasoning text with word wrap", () => {
    const longReasoning =
      "Step 1: Analyze user requirements.\nStep 2: Inspect codebase.\nStep 3: Implement modular components and maintain line budget ratchet.";
    const thinkingEvents: AgentEvent[] = [
      {
        type: "thinking",
        stage: "PLANNER",
        data: {
          delta: longReasoning,
          durationMs: 5200,
          done: true,
        },
      },
    ];

    render(<BottlenecksViewer events={thinkingEvents} />);

    // Initially collapsed
    expect(screen.queryByTestId("expanded-thinking-text")).not.toBeInTheDocument();

    // Click to expand
    const cardHeader = screen.getByTestId("bottleneck-card-header");
    fireEvent.click(cardHeader);

    // Reasoning is visible with word wrap class
    const reasoningElem = screen.getByTestId("expanded-thinking-text");
    expect(reasoningElem).toBeInTheDocument();
    expect(reasoningElem.textContent).toBe(longReasoning);
    expect(reasoningElem.className).toMatch(/whitespace-pre-wrap/);
    expect(reasoningElem.className).toMatch(/break-words/);

    // Click again to collapse
    fireEvent.click(cardHeader);
    expect(screen.queryByTestId("expanded-thinking-text")).not.toBeInTheDocument();
  });
});

