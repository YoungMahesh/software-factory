import { screen, within, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StudioView } from "./StudioView";
import { renderWithProviders } from "../test/test-utils";
import { StudioContextValue } from "../context/StudioContext";
import * as api from "../api";
import { studioQueryKeys } from "../hooks/useStudioQueries";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchIssues: vi.fn().mockResolvedValue({ repo: "cool-app", issues: [] }),
    fetchPullRequests: vi.fn().mockResolvedValue({ repo: "cool-app", pulls: [] }),
    mergePullRequest: vi.fn(),
    syncPreview: vi.fn(),
    rollbackTurn: vi.fn(),
  };
});

const renderStudio = (overrides: Partial<StudioContextValue> = {}) =>
  renderWithProviders(<StudioView />, { contextOverrides: overrides });

describe("StudioView - Delivery & PRs", () => {
  it("renders Feature Pull Request button in top control bar with Draft status badge and toggles popover", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 101,
          title: "Feature: Navigation Bar",
          body: "Fixes #1",
          state: "open",
          status: "draft",
          draft: true,
          merged: false,
          head_branch: "factory/navbar",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/101",
        },
      ],
    });

    const { user } = renderStudio({ selectedRepo: "cool-app" });

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    expect(prBtn).toBeInTheDocument();
    expect(screen.getByTestId("studio-pr-badge-draft")).toHaveTextContent(/Draft/i);

    // Click to open popover
    await user.click(prBtn);

    const popover = screen.getByTestId("studio-pr-popover");
    expect(popover).toBeInTheDocument();
    expect(within(popover).getByText(/Feature: Navigation Bar/i)).toBeInTheDocument();
    expect(within(popover).getByText(/#101/i)).toBeInTheDocument();

    const ghLink = screen.getByTestId("studio-pr-gh-link");
    expect(ghLink).toHaveAttribute("href", "https://github.com/software-factory-09-test/cool-app/pull/101");

    // In Draft status, In-Studio Merge Control in popover is disabled
    const mergeBtn = screen.getByTestId("btn-studio-popover-merge");
    expect(mergeBtn).toBeDisabled();
  });

  it("renders Ready for Review badge and handles popover squash merge flow", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 102,
          title: "Feature: User Profile",
          body: "Fixes #2",
          state: "open",
          status: "ready_for_review",
          draft: false,
          merged: false,
          mergeable: true,
          head_branch: "factory/profile",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/102",
        },
      ],
    });

    vi.mocked(api.mergePullRequest).mockResolvedValue({
      accepted: true,
      merged: true,
      result: { sha: "feedface", branch: "factory/profile", pull_number: 102, branch_deleted: true },
      preview_synced: true,
    });

    const { user } = renderStudio({ selectedRepo: "cool-app" });

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    expect(screen.getByTestId("studio-pr-badge-ready")).toHaveTextContent(/Ready for Review/i);

    await user.click(prBtn);

    const mergeBtn = screen.getByTestId("btn-studio-popover-merge");
    expect(mergeBtn).not.toBeDisabled();
    await user.click(mergeBtn);

    // Inline confirmation inside popover
    const confirmBtn = screen.getByTestId("btn-studio-popover-confirm-merge");
    expect(confirmBtn).toBeInTheDocument();
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(api.mergePullRequest).toHaveBeenCalledWith("cool-app", 102, expect.any(Object));
    });
  });

  it("renders DeliveryGateCard in conversational timeline for Delivery Gate Card event", async () => {
    const deliveryGateMessage = {
      id: "msg-delivery-gate-1",
      role: "assistant" as const,
      timestamp: Date.now(),
      deliveryGate: {
        phase: "finalized",
        pull_number: 105,
        pull_request: {
          number: 105,
          title: "Feature: Settings Page",
          state: "open",
          status: "ready_for_review",
          draft: false,
          merged: false,
          mergeable: true,
          head_branch: "factory/settings",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/105",
        },
        resolved_issues: ["#10"],
        test_verdict: "passed",
      },
    };

    renderStudio({
      selectedRepo: "cool-app",
      messages: [deliveryGateMessage],
    });

    expect(screen.getByTestId("delivery-gate-card")).toBeInTheDocument();
    expect(screen.getByText(/Feature: Settings Page/i)).toBeInTheDocument();
  });

  it("disables In-Studio Merge Control and displays active job warning in popover when job is running", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 103,
          title: "Feature: In Flight Job",
          state: "open",
          status: "ready_for_review",
          draft: false,
          merged: false,
          head_branch: "factory/in-flight",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/103",
        },
      ],
    });

    const activeJob = {
      id: "job-running-1",
      repo: "cool-app",
      model: "test-model",
      vm: false,
      dev: true,
      status: "RUNNING" as const,
      stage: "CODER" as const,
      created_at: "2026-10-15T00:00:00Z",
      log_count: 0,
      event_count: 0,
    };

    const { user } = renderStudio({ selectedRepo: "cool-app", activeJob });

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    await user.click(prBtn);

    const mergeBtn = screen.getByTestId("btn-studio-popover-merge");
    expect(mergeBtn).toBeDisabled();
    expect(screen.getByText(/Job running/i)).toBeInTheDocument();
  });

  it("displays Conflict badge and disables merge action when PR has merge conflicts", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 104,
          title: "Feature: Conflicting Changes",
          state: "open",
          status: "conflict",
          draft: false,
          merged: false,
          mergeable: false,
          mergeable_state: "dirty",
          head_branch: "factory/conflicts",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/104",
        },
      ],
    });

    const { user } = renderStudio({ selectedRepo: "cool-app" });

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    expect(screen.getByTestId("studio-pr-badge-conflict")).toHaveTextContent(/Conflict/i);

    await user.click(prBtn);

    expect(screen.getByTestId("studio-popover-conflict-warning")).toBeInTheDocument();
    const conflictLink = screen.getByTestId("studio-popover-conflict-link");
    expect(conflictLink).toBeInTheDocument();
    expect(conflictLink).toHaveAttribute("href", "https://github.com/software-factory-09-test/cool-app/pull/104");

    const mergeBtn = screen.getByTestId("btn-studio-popover-merge");
    expect(mergeBtn).toBeDisabled();
  });

  it("displays Merged status badge when PR is merged", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 105,
          title: "Feature: Merged Feature",
          state: "closed",
          status: "merged",
          draft: false,
          merged: true,
          head_branch: "factory/merged-feat",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/105",
        },
      ],
    });

    const { user } = renderStudio({ selectedRepo: "cool-app" });

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    expect(screen.getByTestId("studio-pr-badge-merged")).toHaveTextContent(/Merged/i);

    await user.click(prBtn);

    expect(screen.getByText(/Merged into main/i)).toBeInTheDocument();
    expect(screen.queryByTestId("btn-studio-popover-merge")).not.toBeInTheDocument();
  });

  it("synchronizes Live Preview branch indicator to main upon successful squash merge", async () => {
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "cool-app",
      pulls: [
        {
          id: 1,
          number: 106,
          title: "Feature: Live Sync Test",
          state: "open",
          status: "ready_for_review",
          draft: false,
          merged: false,
          mergeable: true,
          head_branch: "factory/live-sync",
          base_branch: "main",
          html_url: "https://github.com/software-factory-09-test/cool-app/pull/106",
        },
      ],
    });

    vi.mocked(api.mergePullRequest).mockResolvedValue({
      accepted: true,
      merged: true,
      result: { sha: "abc999", branch: "factory/live-sync", pull_number: 106, branch_deleted: true },
      preview_synced: true,
    });

    const onMergeSuccess = vi.fn();
    const { user } = renderStudio({
      selectedRepo: "cool-app",
      previewState: {
        status: "SERVING",
        branch: "factory/live-sync",
        preview_url: "https://cool-app-3000.modal.host",
        logs: [],
        error_message: null,
      },
      onMergeSuccess,
    });

    // Preview branch badge initially shows feature branch
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/live-sync");

    const prBtn = await screen.findByTestId("studio-pr-control-btn");
    await user.click(prBtn);

    const mergeBtn = screen.getByTestId("btn-studio-popover-merge");
    await user.click(mergeBtn);

    const confirmBtn = screen.getByTestId("btn-studio-popover-confirm-merge");
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(api.mergePullRequest).toHaveBeenCalledWith("cool-app", 106, expect.any(Object));
      expect(onMergeSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ accepted: true, merged: true, preview_synced: true })
      );
    });
  });


});
