import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ActivityDrawer } from "./ActivityDrawer";
import { Job, AgentEvent } from "../types";

describe("ActivityDrawer - Bottlenecks Subsystem", () => {
  const mockJobs: Job[] = [
    {
      id: "job-12345",
      repo: "my-app",
      feature: "auth-flow",
      status: "RUNNING",
      stage: "CODER",
      model: "MiMo-V2.6-Flash",
      created_at: 1718000000,
      dev: false,
      log_count: 42,
      event_count: 15,
    },
  ];

  const sampleEvents: AgentEvent[] = [
    {
      type: "tool_result",
      stage: "CODER",
      data: {
        toolName: "bash",
        command: "pnpm install",
        durationMs: 4200,
        exitCode: 0,
      },
    },
    {
      type: "thinking",
      stage: "PLANNER",
      data: {
        delta: "Thinking about design...",
        durationMs: 1500,
        done: true,
      },
    },
  ];

  it("switches to Bottlenecks tab and renders BottlenecksViewer", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-12345"
        stage="CODER"
        events={sampleEvents}
        logs={["Started job\n"]}
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    const bottlenecksBtn = screen.getByRole("button", { name: /Bottlenecks/i });
    expect(bottlenecksBtn).toBeInTheDocument();
    expect(bottlenecksBtn).toHaveAttribute("id", "btn-drawer-tab-bottlenecks");

    fireEvent.click(bottlenecksBtn);

    const bottlenecksContainer = document.getElementById("studio-drawer-bottlenecks");
    expect(bottlenecksContainer).toBeInTheDocument();
    expect(screen.getByText("pnpm install")).toBeInTheDocument();
    expect(screen.getByText("LLM Thinking (PLANNER)")).toBeInTheDocument();
  });

  it("supports initialTab='bottlenecks' to render directly into Bottlenecks view", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-12345"
        stage="CODER"
        events={sampleEvents}
        logs={["Started job\n"]}
        jobs={mockJobs}
        selectedRepo="my-app"
        initialTab="bottlenecks"
      />
    );

    expect(document.getElementById("studio-drawer-bottlenecks")).toBeInTheDocument();
    expect(screen.getByText("pnpm install")).toBeInTheDocument();
  });
});
