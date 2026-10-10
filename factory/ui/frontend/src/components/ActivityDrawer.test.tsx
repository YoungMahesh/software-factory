import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ActivityDrawer } from "./ActivityDrawer";

describe("ActivityDrawer", () => {
  const events = [
    {
      type: "thinking",
      stage: "PLANNER",
      data: { delta: "Plan drafted", done: true, durationMs: 1500 },
    },
    {
      type: "tool_result",
      stage: "CODER",
      data: { toolName: "bash", command: "pnpm test", exitCode: 0, output: "OK" },
    },
  ];

  it("renders when open with job ID and stage badge", () => {
    const handleClose = vi.fn();
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={handleClose}
        jobId="job-12345"
        stage="CODER"
        events={events}
        logs={["Started job\n", "Compiling\n"]}
      />
    );

    expect(screen.getByText("Agent Activity")).toBeInTheDocument();
    expect(screen.getByText("job-12345")).toBeInTheDocument();
    expect(screen.getAllByText("CODER").length).toBeGreaterThanOrEqual(1);

    const closeBtn = screen.getByTestId("close-drawer-btn");
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalled();
  });

  it("switches between Timeline tab and Terminal Logs tab", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-12345"
        stage="CODER"
        events={events}
        logs={["Started job\n", "Compiling\n"]}
      />
    );

    // Timeline tab active by default
    expect(screen.getByText("pnpm test")).toBeInTheDocument();

    // Switch to Terminal Logs tab
    const logsTabBtn = screen.getByRole("button", { name: /Terminal Logs/i });
    fireEvent.click(logsTabBtn);

    expect(screen.getByText(/Started job/i)).toBeInTheDocument();
  });
});
