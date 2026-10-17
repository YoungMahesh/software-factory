import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { FailedCommandsTab } from "./FailedCommandsTab";
import { FailedCommand, Job } from "../../types";

describe("FailedCommandsTab", () => {
  const activeCommands: FailedCommand[] = [
    {
      id: "cmd-1",
      command: "pnpm test",
      cwd: "/app/frontend",
      stage: "CODER",
      exitCode: 1,
      isError: true,
      durationMs: 450,
      stderr: "SyntaxError: Unexpected token",
      output: "FAIL src/index.test.ts",
    },
    {
      id: "cmd-2",
      command: "pytest tests/test_api.py",
      cwd: "/app/backend",
      stage: "VERIFIER",
      exitCode: 2,
      isError: true,
      durationMs: 1200,
      stderr: "AssertionError: 404 != 200",
      output: "FAIL tests/test_api.py::test_get",
    },
  ];

  const mockJobs: Job[] = [
    {
      id: "job-active",
      repo: "my-app",
      feature: "live-feature",
      status: "RUNNING",
      stage: "CODER",
      created_at: new Date(Date.now() - 60000).toISOString(),
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: true,
      log_count: 10,
      event_count: 5,
    },
    {
      id: "job-past-1",
      repo: "my-app",
      feature: "past-feature-1",
      status: "FAILED",
      stage: "VERIFIER",
      created_at: new Date(Date.now() - 3600000).toISOString(),
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: false,
      log_count: 25,
      event_count: 12,
    },
    {
      id: "job-other-repo",
      repo: "other-app",
      feature: "unrelated",
      status: "SUCCESS",
      stage: "COMPLETED",
      created_at: new Date(Date.now() - 7200000).toISOString(),
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: false,
      log_count: 5,
      event_count: 2,
    },
  ];

  const mockHistoricalFailedResponse = {
    job_id: "job-past-1",
    total_failed: 1,
    failed_commands: [
      {
        id: "hist-cmd-1",
        command: "cargo check",
        cwd: "/app/rust",
        stage: "CODER",
        exitCode: 101,
        isError: true,
        durationMs: 850,
        stderr: "error[E0432]: unresolved import",
        output: "error[E0432]: unresolved import\nbuild failed",
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders stage filter chips with correct counts for active failed commands", () => {
    render(
      <FailedCommandsTab
        failedCommands={activeCommands}
        activeJobId="job-active"
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    // Filter chips exist
    const allChip = screen.getByTestId("stage-filter-all");
    const coderChip = screen.getByTestId("stage-filter-coder");
    const verifierChip = screen.getByTestId("stage-filter-verifier");

    expect(allChip).toBeInTheDocument();
    expect(coderChip).toBeInTheDocument();
    expect(verifierChip).toBeInTheDocument();

    // Verify failure counts in chips: 2 Total, 1 Coder, 1 Verifier
    expect(allChip).toHaveTextContent("All");
    expect(allChip).toHaveTextContent("2");

    expect(coderChip).toHaveTextContent("Coder");
    expect(coderChip).toHaveTextContent("1");

    expect(verifierChip).toHaveTextContent("Verifier");
    expect(verifierChip).toHaveTextContent("1");

    // All failed commands rendered initially
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("pytest tests/test_api.py")).toBeInTheDocument();
  });

  it("filters displayed failure cards when stage filter chips are clicked", () => {
    render(
      <FailedCommandsTab
        failedCommands={activeCommands}
        activeJobId="job-active"
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    const coderChip = screen.getByTestId("stage-filter-coder");
    const verifierChip = screen.getByTestId("stage-filter-verifier");
    const allChip = screen.getByTestId("stage-filter-all");

    // Filter by Coder
    fireEvent.click(coderChip);
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.queryByText("pytest tests/test_api.py")).not.toBeInTheDocument();

    // Filter by Verifier
    fireEvent.click(verifierChip);
    expect(screen.queryByText("pnpm test")).not.toBeInTheDocument();
    expect(screen.getByText("pytest tests/test_api.py")).toBeInTheDocument();

    // Return to All
    fireEvent.click(allChip);
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("pytest tests/test_api.py")).toBeInTheDocument();
  });

  it("renders past-run selector dropdown listing recent jobs for current repository", () => {
    render(
      <FailedCommandsTab
        failedCommands={activeCommands}
        activeJobId="job-active"
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    const selector = screen.getByTestId("failed-commands-job-selector") as HTMLSelectElement;
    expect(selector).toBeInTheDocument();

    // Should include active job and my-app past jobs, but exclude other-repo
    const options = Array.from(selector.options).map((opt) => opt.value);
    expect(options).toContain("job-active");
    expect(options).toContain("job-past-1");
    expect(options).not.toContain("job-other-repo");

    // Default selected should be active job
    expect(selector.value).toBe("job-active");
  });

  it("loads historical failed commands via GET /api/jobs/{job_id}/failed-commands when viewing a non-active job", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHistoricalFailedResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FailedCommandsTab
        failedCommands={activeCommands}
        activeJobId="job-active"
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    const selector = screen.getByTestId("failed-commands-job-selector");

    // Select the past job
    fireEvent.change(selector, { target: { value: "job-past-1" } });

    // Verify API called
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job-past-1/failed-commands");

    // Verify historical failed command is rendered
    await waitFor(() => {
      expect(screen.getByText("cargo check")).toBeInTheDocument();
    });
    expect(screen.getByText("/app/rust")).toBeInTheDocument();
    expect(screen.getByText("error[E0432]: unresolved import")).toBeInTheDocument();

    // Verify active commands are replaced
    expect(screen.queryByText("pnpm test")).not.toBeInTheDocument();

    // Verify stage filter counts updated for historical job: 1 Total, 1 Coder, 0 Verifier
    const allChip = screen.getByTestId("stage-filter-all");
    const coderChip = screen.getByTestId("stage-filter-coder");
    const verifierChip = screen.getByTestId("stage-filter-verifier");

    expect(allChip).toHaveTextContent("1");
    expect(coderChip).toHaveTextContent("1");
    expect(verifierChip).toHaveTextContent("0");
  });

  it("restores active stream failed commands when switching back to active job", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHistoricalFailedResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FailedCommandsTab
        failedCommands={activeCommands}
        activeJobId="job-active"
        jobs={mockJobs}
        selectedRepo="my-app"
      />
    );

    const selector = screen.getByTestId("failed-commands-job-selector");

    // Switch to past job
    fireEvent.change(selector, { target: { value: "job-past-1" } });
    await waitFor(() => {
      expect(screen.getByText("cargo check")).toBeInTheDocument();
    });

    // Switch back to active job
    fireEvent.change(selector, { target: { value: "job-active" } });

    // Active commands restored immediately without calling fetch for active job
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("pytest tests/test_api.py")).toBeInTheDocument();
    expect(screen.queryByText("cargo check")).not.toBeInTheDocument();
  });

  it("defaults to the first past job and fetches failures when activeJobId is not provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHistoricalFailedResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FailedCommandsTab
        failedCommands={[]}
        jobs={mockJobs.filter((job) => job.id !== "job-active")}
        selectedRepo="my-app"
      />
    );

    const selector = screen.getByTestId("failed-commands-job-selector") as HTMLSelectElement;
    expect(selector.value).toBe("job-past-1");

    // Should fetch failures for job-past-1
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job-past-1/failed-commands");

    await waitFor(() => {
      expect(screen.getByText("cargo check")).toBeInTheDocument();
    });
  });
});
