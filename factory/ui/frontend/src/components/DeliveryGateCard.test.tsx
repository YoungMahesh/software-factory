import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DeliveryGateCard } from "./DeliveryGateCard";
import * as api from "../api";
import { PullRequest, DeliveryGateData } from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchPullRequests: vi.fn(),
    mergePullRequest: vi.fn(),
  };
});

describe("DeliveryGateCard Component", () => {
  let queryClient: QueryClient;

  const mockPR: PullRequest = {
    id: 101,
    number: 12,
    title: "Feature: In-Studio Merge Controls",
    body: "- Fixes #3\n- Fixes #4",
    state: "open",
    status: "ready_for_review",
    draft: false,
    merged: false,
    mergeable: true,
    mergeable_state: "clean",
    head_branch: "factory/pr-merge-controls",
    base_branch: "main",
    html_url: "https://github.com/software-factory-09-test/test1/pull/12",
  };

  const mockDeliveryGateData: DeliveryGateData = {
    phase: "finalized",
    pull_number: 12,
    pull_request: mockPR,
    resolved_issues: ["#3", "#4"],
    test_verdict: "deterministic_tests_passed",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "test1",
      pulls: [mockPR],
    });
  });

  const renderCard = (props: Partial<React.ComponentProps<typeof DeliveryGateCard>> = {}) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <DeliveryGateCard
          repo="test1"
          data={mockDeliveryGateData}
          {...props}
        />
      </QueryClientProvider>
    );
  };

  it("renders PR title, number, and external link to GitHub", () => {
    renderCard();

    expect(screen.getByText(/Feature: In-Studio Merge Controls/i)).toBeInTheDocument();
    expect(screen.getByText(/#12/i)).toBeInTheDocument();

    const ghLink = screen.getByTestId("delivery-gate-gh-link");
    expect(ghLink).toHaveAttribute(
      "href",
      "https://github.com/software-factory-09-test/test1/pull/12"
    );
  });

  it("renders resolved issue checklist and verifier test verdict", () => {
    renderCard();

    expect(screen.getByText(/#3/)).toBeInTheDocument();
    expect(screen.getByText(/#4/)).toBeInTheDocument();
    expect(screen.getByTestId("delivery-gate-verifier-verdict")).toBeInTheDocument();
    expect(screen.getByText(/Tests Passing/i)).toBeInTheDocument();
  });

  it("renders verifier test verdict for failing quality gates", () => {
    renderCard({
      data: {
        ...mockDeliveryGateData,
        test_verdict: "failed",
      },
    });

    const verdict = screen.getByTestId("delivery-gate-verifier-verdict");
    expect(verdict).toBeInTheDocument();
    expect(within(verdict).getByText("Failed")).toBeInTheDocument();
    expect(within(verdict).getByText("Quality gate failed")).toBeInTheDocument();
  });

  it("renders 'Ready for Review' badge and enabled In-Studio Merge Control", () => {
    renderCard();

    expect(screen.getByTestId("pr-status-badge")).toHaveTextContent(/Ready for Review/i);
    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeInTheDocument();
    expect(mergeBtn).not.toBeDisabled();
  });

  it("disables In-Studio Merge Control when PR is in Draft state", () => {
    const draftPR: PullRequest = {
      ...mockPR,
      draft: true,
      status: "draft",
    };
    renderCard({
      data: {
        ...mockDeliveryGateData,
        pull_request: draftPR,
      },
    });

    expect(screen.getByTestId("pr-status-badge")).toHaveTextContent(/Draft/i);
    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeDisabled();
  });

  it("disables In-Studio Merge Control when an assembly line job is actively executing", () => {
    renderCard({ activeJobRunning: true });

    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeDisabled();
    expect(screen.getByText(/Job Actively Executing/i)).toBeInTheDocument();
  });

  it("disables In-Studio Merge Control when PR is closed without being merged", () => {
    const closedPR: PullRequest = {
      ...mockPR,
      state: "closed",
      merged: false,
      status: "closed",
    };
    renderCard({
      data: {
        ...mockDeliveryGateData,
        pull_request: closedPR,
      },
    });

    expect(screen.getByTestId("pr-status-badge")).toHaveTextContent(/Closed/i);
    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeDisabled();
  });

  it("displays Conflict badge and links to GitHub when PR has merge conflicts", () => {
    const conflictPR: PullRequest = {
      ...mockPR,
      mergeable: false,
      mergeable_state: "dirty",
      status: "conflict",
    };
    renderCard({
      data: {
        ...mockDeliveryGateData,
        pull_request: conflictPR,
      },
    });

    expect(screen.getByTestId("pr-status-badge")).toHaveTextContent(/Conflict/i);
    expect(screen.getByTestId("delivery-gate-conflict-warning")).toBeInTheDocument();
    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeDisabled();
  });

  it("handles inline confirmation flow and executes squash merge on confirmation", async () => {
    vi.mocked(api.mergePullRequest).mockResolvedValue({
      accepted: true,
      merged: true,
      result: {
        sha: "deadbeef",
        branch: "factory/pr-merge-controls",
        pull_number: 12,
        branch_deleted: true,
      },
      preview_synced: true,
    });

    const onMergeSuccess = vi.fn();
    renderCard({ onMergeSuccess });

    // Initial state: "Merge into main"
    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    fireEvent.click(mergeBtn);

    // Confirmation state: shows "Confirm Squash Merge" and "Cancel"
    const confirmBtn = screen.getByTestId("btn-delivery-gate-confirm-merge");
    const cancelBtn = screen.getByTestId("btn-delivery-gate-cancel-merge");
    expect(confirmBtn).toBeInTheDocument();
    expect(cancelBtn).toBeInTheDocument();

    // Click confirm
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.mergePullRequest).toHaveBeenCalledWith("test1", 12, expect.any(Object));
      expect(onMergeSuccess).toHaveBeenCalled();
    });
  });

  it("allows cancelling inline confirmation state", () => {
    renderCard();

    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    fireEvent.click(mergeBtn);

    const cancelBtn = screen.getByTestId("btn-delivery-gate-cancel-merge");
    fireEvent.click(cancelBtn);

    expect(screen.getByTestId("btn-delivery-gate-merge")).toBeInTheDocument();
    expect(screen.queryByTestId("btn-delivery-gate-confirm-merge")).not.toBeInTheDocument();
  });

  it("displays 'Merged into main' state when PR is merged", () => {
    const mergedPR: PullRequest = {
      ...mockPR,
      merged: true,
      status: "merged",
    };
    renderCard({
      data: {
        ...mockDeliveryGateData,
        merged: true,
        pull_request: mergedPR,
      },
    });

    expect(screen.getByTestId("pr-status-badge")).toHaveTextContent(/Merged/i);
    expect(screen.getByTestId("delivery-gate-merged-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("btn-delivery-gate-merge")).not.toBeInTheDocument();
  });
});
