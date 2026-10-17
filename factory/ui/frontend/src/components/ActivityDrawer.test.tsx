import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ActivityDrawer } from "./ActivityDrawer";
import { Job } from "../types";

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

  const mockJobs: Job[] = [
    {
      id: "job-101",
      repo: "my-app",
      feature: "auth-flow",
      status: "RUNNING",
      stage: "CODER",
      created_at: new Date(Date.now() - 120000).toISOString(),
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: true,
      log_count: 10,
      event_count: 5,
    },
    {
      id: "job-100",
      repo: "my-app",
      feature: "checkout",
      status: "SUCCESS",
      stage: "COMPLETED",
      created_at: new Date(Date.now() - 3600000).toISOString(),
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: false,
      log_count: 42,
      event_count: 15,
    },
  ];

  it("renders 4 tabs (Timeline, Terminal Logs, History, and Bottlenecks)", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-12345"
        stage="CODER"
        events={events}
        logs={["Started job\n"]}
        jobs={mockJobs}
      />
    );

    expect(screen.getByRole("button", { name: /Timeline/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Terminal Logs/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /History/i })).toBeInTheDocument();
    const bottlenecksBtn = screen.getByRole("button", { name: /Bottlenecks/i });
    expect(bottlenecksBtn).toBeInTheDocument();
    expect(bottlenecksBtn).toHaveAttribute("id", "btn-drawer-tab-bottlenecks");
  });

  it("switches to Bottlenecks tab when clicking tab button", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-12345"
        stage="CODER"
        events={events}
        logs={["Started job\n"]}
        jobs={mockJobs}
      />
    );

    const bottlenecksBtn = screen.getByRole("button", { name: /Bottlenecks/i });
    fireEvent.click(bottlenecksBtn);

    expect(document.getElementById("studio-drawer-bottlenecks")).toBeInTheDocument();
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
        jobs={mockJobs}
      />
    );

    // Timeline tab active by default
    expect(screen.getByText("pnpm test")).toBeInTheDocument();

    // Switch to Terminal Logs tab
    const logsTabBtn = screen.getByRole("button", { name: /Terminal Logs/i });
    fireEvent.click(logsTabBtn);

    expect(screen.getByText(/Started job/i)).toBeInTheDocument();
  });

  it("renders multi-run table in History tab with job ID, repo, feature, status badge, stage, and relative timestamp", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-101"
        stage="CODER"
        events={events}
        logs={["Started job\n"]}
        jobs={mockJobs}
      />
    );

    // Switch to History tab
    const historyTabBtn = screen.getByRole("button", { name: /History/i });
    fireEvent.click(historyTabBtn);

    // Check table headers
    expect(screen.getByText("Job ID")).toBeInTheDocument();
    expect(screen.getByText("Repo")).toBeInTheDocument();
    expect(screen.getByText("Feature")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Stage")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();

    // Check row data within table
    const table = screen.getByRole("table");
    expect(within(table).getByText("job-101")).toBeInTheDocument();
    expect(within(table).getByText("auth-flow")).toBeInTheDocument();
    expect(within(table).getByText("RUNNING")).toBeInTheDocument();
    expect(within(table).getByText("2m ago")).toBeInTheDocument();

    expect(within(table).getByText("job-100")).toBeInTheDocument();
    expect(within(table).getByText("checkout")).toBeInTheDocument();
    expect(within(table).getByText("SUCCESS")).toBeInTheDocument();
    expect(within(table).getByText("1h ago")).toBeInTheDocument();
  });

  it("inspects job logs in place and switches to Logs tab", () => {
    const handleSelectJob = vi.fn();
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-101"
        stage="CODER"
        events={events}
        logs={["Started job\n"]}
        jobs={mockJobs}
        onSelectJob={handleSelectJob}
      />
    );

    // Switch to History tab
    fireEvent.click(screen.getByRole("button", { name: /History/i }));

    // Click inspect logs on job-100
    const inspectBtn = screen.getByTestId("inspect-job-logs-job-100");
    fireEvent.click(inspectBtn);

    expect(handleSelectJob).toHaveBeenCalledWith(mockJobs[1]);
    // Verifies tab switched to logs in place
    expect(screen.getByText(/Started job/i)).toBeInTheDocument();
  });

  it("renders cancel button for running jobs and triggers onCancelJob", () => {
    const handleCancelJob = vi.fn();
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-101"
        stage="CODER"
        events={events}
        logs={["Started job\n"]}
        jobs={mockJobs}
        onCancelJob={handleCancelJob}
      />
    );

    // Switch to History tab
    fireEvent.click(screen.getByRole("button", { name: /History/i }));

    // Running job (job-101) has cancel button
    const cancelBtn = screen.getByTestId("cancel-job-job-101");
    expect(cancelBtn).toBeInTheDocument();
    fireEvent.click(cancelBtn);
    expect(handleCancelJob).toHaveBeenCalledWith("job-101");

    // Non-running job (job-100) does not have cancel button
    expect(screen.queryByTestId("cancel-job-job-100")).not.toBeInTheDocument();
  });

  it("filters jobs by target selectedRepo when specified", () => {
    const multiRepoJobs: Job[] = [
      {
        id: "job-repo-1",
        repo: "target-repo",
        status: "SUCCESS",
        stage: "COMPLETED",
        created_at: new Date().toISOString(),
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: false,
        log_count: 5,
        event_count: 2,
      },
      {
        id: "job-repo-2",
        repo: "other-repo",
        status: "SUCCESS",
        stage: "COMPLETED",
        created_at: new Date().toISOString(),
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: false,
        log_count: 5,
        event_count: 2,
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobs={multiRepoJobs}
        selectedRepo="target-repo"
        initialTab="history"
      />
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText("job-repo-1")).toBeInTheDocument();
    expect(within(table).queryByText("job-repo-2")).not.toBeInTheDocument();
    expect(screen.getByText("1 job")).toBeInTheDocument();
  });
});

