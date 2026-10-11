import { screen, within, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { IssueDrawer } from "./IssueDrawer";
import { renderWithProviders } from "../test/test-utils";
import { Issue } from "../types";
import * as api from "../api";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchIssues: vi.fn(),
    dispatchStudio: vi.fn(),
  };
});

describe("IssueDrawer", () => {
  const mockMilestone1 = {
    number: 1,
    title: "v1: Core Feature",
    slug: "v1-core-feature",
  };

  const mockIssues: Issue[] = [
    {
      number: 1,
      title: "Setup API routes",
      body: "Scaffold backend routes for data synchronization.\n\nBlocked by: None",
      state: "open",
      status: "ready-for-agent",
      labels: ["factory:ready", "backend"],
      blocked_by: [],
      milestone: mockMilestone1,
    },
    {
      number: 2,
      title: "Add frontend client view",
      body: "Build the UI view.\n\nBlocked by: #1",
      state: "open",
      status: "ready-for-agent",
      labels: ["factory:ready", "frontend"],
      blocked_by: ["1"],
      milestone: mockMilestone1,
    },
    {
      number: 3,
      title: "Database migrations",
      body: "Create tables.\n\nBlocked by: None",
      state: "closed",
      status: "resolved",
      labels: ["factory:resolved"],
      blocked_by: [],
      milestone: mockMilestone1,
    },
    {
      number: 4,
      title: "Worker background job",
      body: "Execute background task.\n\nBlocked by: None",
      state: "open",
      status: "claimed",
      labels: ["factory:claimed"],
      blocked_by: [],
      milestone: null,
    },
    {
      number: 5,
      title: "Human review required issue",
      body: "Need architectural guidance.\n\nBlocked by: None",
      state: "open",
      status: "ready-for-human",
      labels: ["factory:ready-for-human"],
      blocked_by: [],
      milestone: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchIssues).mockResolvedValue({
      repo: "test-repo",
      issues: mockIssues,
    });
  });

  const renderDrawer = (props: Partial<Parameters<typeof IssueDrawer>[0]> = {}) => {
    const handleClose = vi.fn();
    const handleGrillAndAlign = vi.fn();
    const handleInstantDispatch = vi.fn();
    const handleRunMilestone = vi.fn();
    const handleRefresh = vi.fn();

    const result = renderWithProviders(
      <IssueDrawer
        isOpen={true}
        onClose={handleClose}
        repo="test-repo"
        onGrillAndAlign={handleGrillAndAlign}
        onInstantDispatch={handleInstantDispatch}
        onRunMilestone={handleRunMilestone}
        onRefresh={handleRefresh}
        {...props}
      />
    );

    return {
      ...result,
      handleClose,
      handleGrillAndAlign,
      handleInstantDispatch,
      handleRunMilestone,
      handleRefresh,
    };
  };

  it("does not render when isOpen is false", () => {
    const { container } = renderWithProviders(
      <IssueDrawer isOpen={false} onClose={vi.fn()} repo="test-repo" />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders slide-over drawer when open, displaying repository and title", async () => {
    renderDrawer();

    expect(screen.getByText("GitHub Issues")).toBeInTheDocument();
    expect(screen.getByText("test-repo")).toBeInTheDocument();
    expect(screen.getByTestId("close-issue-drawer-btn")).toBeInTheDocument();
  });

  it("closes when close button, backdrop, or Escape key is triggered", async () => {
    const { handleClose } = renderDrawer();

    // 1. Close button
    const closeBtn = screen.getByTestId("close-issue-drawer-btn");
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    // 2. Backdrop click
    const backdrop = screen.getByTestId("issue-drawer-backdrop");
    fireEvent.click(backdrop);
    expect(handleClose).toHaveBeenCalledTimes(2);

    // 3. Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(3);
  });

  it("groups issues by GitHub milestone with progress counts and unassigned backlog", async () => {
    renderDrawer();

    // Wait for issues query to populate
    await waitFor(() => {
      expect(screen.getByText(/v1: Core Feature/i)).toBeInTheDocument();
    });

    // Milestone header shows progress count (1 closed / resolved, 2 open in mock)
    const milestoneSection = screen.getByTestId("milestone-group-v1-core-feature");
    expect(milestoneSection).toBeInTheDocument();
    expect(within(milestoneSection).getByText("Setup API routes")).toBeInTheDocument();
    expect(within(milestoneSection).getByText("Add frontend client view")).toBeInTheDocument();

    // Unassigned Backlog section
    const backlogSection = screen.getByTestId("milestone-group-backlog");
    expect(backlogSection).toBeInTheDocument();
    expect(within(backlogSection).getByText(/Backlog/i)).toBeInTheDocument();
    expect(within(backlogSection).getByText("Worker background job")).toBeInTheDocument();
    expect(within(backlogSection).getByText("Human review required issue")).toBeInTheDocument();
  });

  it("filters between Open, Closed, and All issues", async () => {
    const { user } = renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    });

    // Default filter is 'Open': open issues are shown, closed issue (#3) is hidden
    expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    expect(screen.queryByText("Database migrations")).not.toBeInTheDocument();

    // Switch to 'Closed' filter
    const closedFilterBtn = screen.getByTestId("filter-closed");
    await user.click(closedFilterBtn);

    expect(screen.getByText("Database migrations")).toBeInTheDocument();
    expect(screen.queryByText("Setup API routes")).not.toBeInTheDocument();

    // Switch to 'All' filter
    const allFilterBtn = screen.getByTestId("filter-all");
    await user.click(allFilterBtn);

    expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    expect(screen.getByText("Database migrations")).toBeInTheDocument();
  });

  it("supports real-time text search filtering by number, title, and label", async () => {
    const { user } = renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    });

    const searchInput = screen.getByTestId("issue-search-input");

    // Search by title
    await user.type(searchInput, "frontend");
    expect(screen.getByText("Add frontend client view")).toBeInTheDocument();
    expect(screen.queryByText("Setup API routes")).not.toBeInTheDocument();

    // Clear search and search by issue number
    await user.clear(searchInput);
    await user.type(searchInput, "#1");
    expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    expect(screen.queryByText("Add frontend client view")).not.toBeInTheDocument();

    // Clear and search by label
    await user.clear(searchInput);
    await user.type(searchInput, "ready-for-human");
    expect(screen.getByText("Human review required issue")).toBeInTheDocument();
    expect(screen.queryByText("Setup API routes")).not.toBeInTheDocument();
  });

  it("renders distinct visual status pills for factory lifecycle labels", async () => {
    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    });

    // Verify factory:ready pill
    const readyPill = screen.getAllByTestId("status-pill-factory:ready");
    expect(readyPill.length).toBeGreaterThanOrEqual(1);
    expect(readyPill[0]).toHaveTextContent("factory:ready");

    // Verify factory:claimed pill
    const claimedPill = screen.getByTestId("status-pill-factory:claimed");
    expect(claimedPill).toBeInTheDocument();
    expect(claimedPill).toHaveTextContent("factory:claimed");

    // Verify factory:ready-for-human pill
    const humanPill = screen.getByTestId("status-pill-factory:ready-for-human");
    expect(humanPill).toBeInTheDocument();
    expect(humanPill).toHaveTextContent("factory:ready-for-human");
  });

  it("disables 'Instant Dispatch' when issue has open dependencies, while keeping 'Grill & Align' enabled", async () => {
    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Add frontend client view")).toBeInTheDocument();
    });

    // Issue #2 is blocked by #1 (which is open)
    const instantDispatchBtn = screen.getByTestId("instant-dispatch-btn-2");
    expect(instantDispatchBtn).toBeDisabled();
    expect(instantDispatchBtn).toHaveAttribute("title", expect.stringMatching(/Blocked by open issue/i));

    // Grill & Align button remains enabled
    const grillBtn = screen.getByTestId("grill-align-btn-2");
    expect(grillBtn).not.toBeDisabled();
  });

  it("disables 'Instant Dispatch' when issue has active claim (factory:claimed)", async () => {
    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Worker background job")).toBeInTheDocument();
    });

    // Issue #4 has factory:claimed
    const instantDispatchBtn = screen.getByTestId("instant-dispatch-btn-4");
    expect(instantDispatchBtn).toBeDisabled();
    expect(instantDispatchBtn).toHaveAttribute("title", expect.stringMatching(/claimed/i));

    // Grill & Align remains enabled
    const grillBtn = screen.getByTestId("grill-align-btn-4");
    expect(grillBtn).not.toBeDisabled();
  });

  it("enables 'Instant Dispatch' for unblocked, unclaimed issues and triggers dispatch handler", async () => {
    const { user, handleInstantDispatch } = renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Setup API routes")).toBeInTheDocument();
    });

    // Issue #1 is unblocked
    const instantDispatchBtn = screen.getByTestId("instant-dispatch-btn-1");
    expect(instantDispatchBtn).not.toBeDisabled();

    await user.click(instantDispatchBtn);
    expect(handleInstantDispatch).toHaveBeenCalledWith({
      repo: "test-repo",
      issue: expect.objectContaining({ number: 1, title: "Setup API routes" }),
    });
  });

  it("clicking 'Grill & Align' submits the issue specification and closes drawer", async () => {
    const { user, handleGrillAndAlign, handleClose } = renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("Add frontend client view")).toBeInTheDocument();
    });

    const grillBtn = screen.getByTestId("grill-align-btn-2");
    await user.click(grillBtn);

    expect(handleGrillAndAlign).toHaveBeenCalledWith(
      expect.objectContaining({
        number: 2,
        title: "Add frontend client view",
      })
    );
    expect(handleClose).toHaveBeenCalled();
  });

  it("reveals milestone batch confirmation popover with ticket counts and target branch on 'Run Milestone'", async () => {
    const { user, handleRunMilestone } = renderDrawer();

    await waitFor(() => {
      expect(screen.getByText(/v1: Core Feature/i)).toBeInTheDocument();
    });

    const runMilestoneBtn = screen.getByTestId("run-milestone-v1-core-feature");
    expect(runMilestoneBtn).toBeInTheDocument();

    // 1. Open confirmation popover
    await user.click(runMilestoneBtn);

    const popover = screen.getByTestId("milestone-batch-popover");
    expect(popover).toBeInTheDocument();
    expect(within(popover).getByText(/factory\/v1-core-feature/i)).toBeInTheDocument();
    expect(within(popover).getByText(/3 total/i)).toBeInTheDocument();
    expect(within(popover).getByText(/1 ready/i)).toBeInTheDocument();
    expect(within(popover).getByText(/1 blocked/i)).toBeInTheDocument();
    expect(within(popover).getByText(/1 resolved/i)).toBeInTheDocument();

    // 2. Test Cancel button closes popover
    const cancelBtn = within(popover).getByTestId("cancel-batch-btn");
    await user.click(cancelBtn);
    expect(screen.queryByTestId("milestone-batch-popover")).not.toBeInTheDocument();
    expect(handleRunMilestone).not.toHaveBeenCalled();

    // 3. Re-open and Confirm Batch
    await user.click(runMilestoneBtn);
    const confirmBtn = screen.getByTestId("confirm-batch-btn");
    await user.click(confirmBtn);

    expect(handleRunMilestone).toHaveBeenCalledWith(
      expect.objectContaining({
        repo: "test-repo",
        milestone: expect.objectContaining({
          number: 1,
          slug: "v1-core-feature",
          title: "v1: Core Feature",
        }),
      })
    );
  });

  it("triggers refresh when manual Refresh button is clicked", async () => {
    const { user, handleRefresh } = renderDrawer();

    const refreshBtn = screen.getByTestId("refresh-issues-btn");
    await user.click(refreshBtn);

    expect(handleRefresh).toHaveBeenCalled();
  });
});
