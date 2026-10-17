import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RepoBottlenecksTable } from "./RepoBottlenecksTable";
import { BottlenecksViewer } from "../BottlenecksViewer";
import * as api from "../../api";
import { RepoBottleneck } from "../../types";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchRepoBottlenecks: vi.fn(),
  };
});

describe("RepoBottlenecksTable", () => {
  it("renders loading state when isLoading is true", () => {
    render(
      <RepoBottlenecksTable
        repo="my-repo"
        bottlenecks={[]}
        isLoading={true}
      />
    );
    expect(screen.getByTestId("repo-bottlenecks-loading")).toBeInTheDocument();
  });

  it("renders error message and retry button on error", () => {
    const handleRetry = vi.fn();
    render(
      <RepoBottlenecksTable
        repo="my-repo"
        bottlenecks={[]}
        error="Network error"
        onRetry={handleRetry}
      />
    );
    expect(screen.getByTestId("repo-bottlenecks-error")).toBeInTheDocument();
    expect(screen.getByText("Network error")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it("renders prompt when repo is not selected", () => {
    render(<RepoBottlenecksTable bottlenecks={[]} />);
    expect(screen.getByText(/select a repository to view aggregated bottlenecks/i)).toBeInTheDocument();
  });

  it("renders empty state when no bottlenecks are recorded", () => {
    render(<RepoBottlenecksTable repo="empty-repo" bottlenecks={[]} />);
    expect(
      screen.getByText(/no aggregated bottlenecks recorded for this repository yet/i)
    ).toBeInTheDocument();
  });

  it("renders aggregated bottlenecks table with ranks, commands, badges, and metrics", () => {
    const mockData: RepoBottleneck[] = [
      {
        command: "pnpm install",
        category: "Package Install",
        stage: "CODER",
        count: 5,
        total_duration_ms: 12500,
        avg_duration_ms: 2500,
        max_duration_ms: 3200,
      },
      {
        command: "LLM Thinking (PLANNER)",
        category: "LLM Thinking",
        stage: "PLANNER",
        count: 3,
        total_duration_ms: 6000,
        avg_duration_ms: 2000,
        max_duration_ms: 2400,
      },
      {
        command: "pnpm test",
        category: "Test Suite",
        stage: "VERIFIER",
        count: 10,
        total_duration_ms: 3500,
        avg_duration_ms: 350,
        max_duration_ms: 500,
      },
    ];

    render(<RepoBottlenecksTable repo="my-repo" bottlenecks={mockData} />);

    expect(screen.getByTestId("repo-bottlenecks-table")).toBeInTheDocument();

    // Headers
    expect(screen.getByText("#")).toBeInTheDocument();
    expect(screen.getByText(/command \/ phase/i)).toBeInTheDocument();
    expect(screen.getByText(/total duration/i)).toBeInTheDocument();
    expect(screen.getByText(/invocations/i)).toBeInTheDocument();
    expect(screen.getByText(/avg duration/i)).toBeInTheDocument();
    expect(screen.getByText(/max duration/i)).toBeInTheDocument();

    // Row 1
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("pnpm install")).toBeInTheDocument();
    expect(screen.getByText("Package Install")).toBeInTheDocument();
    expect(screen.getByText("12.50s")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("2.50s")).toBeInTheDocument();
    expect(screen.getByText("3.20s")).toBeInTheDocument();

    // Row 2
    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.getByText("LLM Thinking (PLANNER)")).toBeInTheDocument();
    expect(screen.getByText("LLM Thinking")).toBeInTheDocument();
    expect(screen.getByText("6.00s")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2.00s")).toBeInTheDocument();
    expect(screen.getByText("2.40s")).toBeInTheDocument();

    // Row 3
    expect(screen.getByText("#3")).toBeInTheDocument();
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("Test Suite")).toBeInTheDocument();
    expect(screen.getByText("3.50s")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("350ms")).toBeInTheDocument();
    expect(screen.getByText("500ms")).toBeInTheDocument();
  });
});

describe("BottlenecksViewer - Scope Toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const sampleEvents = [
    {
      type: "tool_result",
      stage: "CODER",
      data: {
        toolName: "bash",
        command: "npm run lint",
        durationMs: 450,
        exitCode: 0,
      },
    },
  ];

  it("renders scope toggle with 'Current Run' and 'Repository Aggregates'", () => {
    render(<BottlenecksViewer events={sampleEvents} repo="my-repo" />);

    expect(screen.getByTestId("scope-toggle-current-run")).toBeInTheDocument();
    expect(screen.getByTestId("scope-toggle-repo-aggregates")).toBeInTheDocument();
    // Default is Current Run, so npm run lint is shown
    expect(screen.getByText("npm run lint")).toBeInTheDocument();
  });

  it("switches to repository aggregates and queries API", async () => {
    vi.mocked(api.fetchRepoBottlenecks).mockResolvedValueOnce({
      repo: "my-repo",
      bottlenecks: [
        {
          command: "pnpm test",
          category: "Test Suite",
          stage: "VERIFIER",
          count: 8,
          total_duration_ms: 2400,
          avg_duration_ms: 300,
          max_duration_ms: 450,
        },
      ],
    });

    render(<BottlenecksViewer events={sampleEvents} repo="my-repo" />);

    fireEvent.click(screen.getByTestId("scope-toggle-repo-aggregates"));

    expect(api.fetchRepoBottlenecks).toHaveBeenCalledWith("my-repo");

    await waitFor(() => {
      expect(screen.getByTestId("repo-bottlenecks-table")).toBeInTheDocument();
    });

    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();

    // Switch back to Current Run
    fireEvent.click(screen.getByTestId("scope-toggle-current-run"));
    expect(screen.getByText("npm run lint")).toBeInTheDocument();
    expect(screen.queryByTestId("repo-bottlenecks-table")).not.toBeInTheDocument();
  });
});
