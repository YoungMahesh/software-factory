import { render, screen, fireEvent, within, waitFor } from "@testing-library/react";
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

  it("renders 4 tabs (Timeline, Terminal Logs, History, and Failed Commands)", () => {
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
    expect(screen.getByRole("button", { name: /Failed Commands/i })).toBeInTheDocument();
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

  it("isolates and renders structured command cards for failed commands in CODER and VERIFIER stages", () => {
    const mixedEvents = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm install",
          cwd: "/app",
          exitCode: 0,
          output: "Dependencies installed",
        },
      },
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm build",
          cwd: "/app/client",
          exitCode: 1,
          durationMs: 450,
          output: "tsc: not found",
          stderr: "tsc: not found",
          isError: true,
          toolCallId: "call-fail-1",
        },
      },
      {
        type: "tool_result",
        stage: "VERIFIER",
        data: {
          toolName: "bash",
          command: "pytest tests/",
          cwd: "/app/backend",
          exitCode: 2,
          durationMs: 1200,
          output: "FAIL test_api.py",
          stderr: "FAIL test_api.py",
          isError: true,
          toolCallId: "call-fail-2",
        },
      },
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "read",
          path: "/app/src/index.ts",
          exitCode: 1,
          isError: true,
        },
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-999"
        stage="CODER"
        events={mixedEvents}
      />
    );

    // Coral counter badge on tab button
    const failedTabBtn = screen.getByRole("button", { name: /Failed Commands/i });
    expect(failedTabBtn).toBeInTheDocument();
    expect(within(failedTabBtn).getByText("2")).toBeInTheDocument();

    // Click Failed Commands tab
    fireEvent.click(failedTabBtn);

    // Verify isolated failed commands are rendered
    expect(screen.getByText("pnpm build")).toBeInTheDocument();
    expect(screen.getByText("/app/client")).toBeInTheDocument();
    expect(screen.getByText("pytest tests/")).toBeInTheDocument();
    expect(screen.getByText("/app/backend")).toBeInTheDocument();

    // Verify exit codes and stderr lines
    expect(screen.getByText("Exit code 1")).toBeInTheDocument();
    expect(screen.getByText("Exit code 2")).toBeInTheDocument();
    expect(screen.getByText("tsc: not found")).toBeInTheDocument();
    expect(screen.getByText("FAIL test_api.py")).toBeInTheDocument();

    // Verify successful bash command is not in the failed commands view
    expect(screen.queryByText("pnpm install")).not.toBeInTheDocument();
    expect(screen.queryByText("Dependencies installed")).not.toBeInTheDocument();
  });

  it("renders clean empty state with confirmation message when zero commands failed", () => {
    const cleanEvents = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm test",
          exitCode: 0,
          output: "All tests pass",
        },
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-clean"
        stage="COMPLETED"
        events={cleanEvents}
      />
    );

    const failedTabBtn = screen.getByRole("button", { name: /Failed Commands/i });
    fireEvent.click(failedTabBtn);

    expect(screen.getByTestId("failed-commands-empty-state")).toBeInTheDocument();
    expect(screen.getByText("No Failed Commands")).toBeInTheDocument();
    expect(screen.getByText(/All shell commands executed successfully/i)).toBeInTheDocument();
  });

  it("supports initialTab='failed-commands' to open directly into Failed Commands tab", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-direct"
        stage="CODER"
        events={[]}
        initialTab="failed-commands"
      />
    );

    expect(screen.getByTestId("failed-commands-empty-state")).toBeInTheDocument();
  });

  it("renders stage filter chips and past-run selector in Failed Commands tab header", async () => {
    const failedEvents = [
      {
        type: "tool_result",
        stage: "CODER",
        data: {
          toolName: "bash",
          command: "pnpm build",
          exitCode: 1,
          output: "tsc: not found",
          isError: true,
          toolCallId: "call-c1",
        },
      },
      {
        type: "tool_result",
        stage: "VERIFIER",
        data: {
          toolName: "bash",
          command: "pytest tests/",
          exitCode: 2,
          output: "FAIL test_api.py",
          isError: true,
          toolCallId: "call-v1",
        },
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        jobId="job-101"
        stage="CODER"
        events={failedEvents}
        jobs={mockJobs}
        selectedRepo="my-app"
        initialTab="failed-commands"
      />
    );

    expect(screen.getByTestId("failed-commands-tab-header")).toBeInTheDocument();
    expect(screen.getByTestId("stage-filter-all")).toHaveTextContent("2");
    expect(screen.getByTestId("stage-filter-coder")).toHaveTextContent("1");
    expect(screen.getByTestId("stage-filter-verifier")).toHaveTextContent("1");

    const selector = screen.getByTestId("failed-commands-job-selector") as HTMLSelectElement;
    expect(selector).toBeInTheDocument();
    expect(selector.value).toBe("job-101");

    // Filter to Coder
    fireEvent.click(screen.getByTestId("stage-filter-coder"));
    expect(screen.getByText("pnpm build")).toBeInTheDocument();
    expect(screen.queryByText("pytest tests/")).not.toBeInTheDocument();

    // Select past job in drawer and verify historical fetch without mutating onSelectJob
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "job-100",
        total_failed: 1,
        failed_commands: [
          {
            id: "hist-100",
            command: "npm run lint",
            stage: "CODER",
            exitCode: 1,
            output: "eslint error",
            isError: true,
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    fireEvent.change(selector, { target: { value: "job-100" } });
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job-100/failed-commands");
    await waitFor(() => {
      expect(screen.getByText("npm run lint")).toBeInTheDocument();
    });
  });
});



