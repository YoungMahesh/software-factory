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

describe("StudioView - Grilling & Issues", () => {
  it("renders assistant grilling interview round with questions, recommended answers, and sharpened terms", () => {
    const messages = [
      {
        id: "m-user-1",
        role: "user" as const,
        text: "Add an analytics chart with redux store",
        timestamp: Date.now() - 60000,
      },
      {
        id: "m-assistant-grill-1",
        role: "assistant" as const,
        timestamp: Date.now() - 30000,
        grillTurn: {
          type: "grill_round" as const,
          round: 1,
          summary: "Clarifying chart placement and state cache strategy.",
          questions: [
            {
              id: "Q1",
              title: "Route Placement",
              question: "Where should the analytics route be located?",
              recommended: "app/routes/analytics.tsx",
              options: ["app/routes/analytics.tsx", "app/routes/dashboard/analytics.tsx"],
            },
            {
              id: "Q2",
              title: "State Management",
              question: "How should chart metrics data be cached?",
              recommended: "TanStack Query cache",
              options: ["TanStack Query cache", "React local state"],
            },
          ],
          sharpened_terms: [
            {
              fuzzy_term: "redux store",
              canonical_term: "Client State",
              explanation: "TanStack Start projects use TanStack Query cache for shared client state.",
            },
          ],
        },
      },
    ];

    renderStudio({ messages });

    // 1. Verify grilling round badge and summary
    expect(screen.getByTestId("grilling-round-badge")).toHaveTextContent("Grill & Align (Round 1)");
    expect(screen.getByText("Clarifying chart placement and state cache strategy.")).toBeInTheDocument();

    // 2. Verify sharpened terms banner
    expect(screen.getByTestId("sharpened-terms-banner")).toBeInTheDocument();
    expect(screen.getByText("Client State")).toBeInTheDocument();
    expect(screen.getByText("redux store")).toBeInTheDocument();

    // 3. Verify question cards and recommended answers
    expect(screen.getByTestId("grill-question-Q1")).toBeInTheDocument();
    expect(screen.getByText("Where should the analytics route be located?")).toBeInTheDocument();
    expect(screen.getByTestId("recommended-answer-Q1")).toHaveTextContent("app/routes/analytics.tsx");

    expect(screen.getByTestId("grill-question-Q2")).toBeInTheDocument();
    expect(screen.getByText("How should chart metrics data be cached?")).toBeInTheDocument();
    expect(screen.getByTestId("recommended-answer-Q2")).toHaveTextContent("TanStack Query cache");
  });

  it("renders interactive 'Approve Plan & Build' card upon ready_for_approval and triggers onApprovePlan", async () => {
    const handleApprove = vi.fn();
    const readyTurn = {
      type: "ready_for_approval" as const,
      round: 2,
      summary: "Interview completed. Ready to build analytics dashboard.",
      plan: "### Implementation Plan\n1. Scaffold route\n2. Add chart component",
      draft_adr: {
        title: "0002: Analytics Dashboard Architecture",
        filename: "docs/adr/0002-analytics-dashboard-architecture.md",
        content: "# 0002: Analytics Dashboard Architecture\n\n**Status**: Proposed",
      },
      questions: [],
    };

    const messages = [
      {
        id: "m-user-1",
        role: "user" as const,
        text: "Add an analytics chart",
        timestamp: Date.now() - 60000,
      },
      {
        id: "m-assistant-approval",
        role: "assistant" as const,
        timestamp: Date.now() - 10000,
        grillTurn: readyTurn,
      },
    ];

    const { user } = renderStudio({
      messages,
      onApprovePlan: handleApprove,
    });

    // 1. Verify ApprovalCard is rendered in the chat timeline
    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText("Plan Ready for Approval")).toBeInTheDocument();
    expect(screen.getByText("docs/adr/0002-analytics-dashboard-architecture.md")).toBeInTheDocument();

    // 2. Click "Approve Plan & Build"
    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    await user.click(approveBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith(readyTurn);
  });

  it("renders ApprovalCard cleanly without draft ADR preview when ready_for_approval has null draft_adr", async () => {
    const handleApprove = vi.fn();
    const readyTurnWithoutAdr: GrillTurnResult = {
      type: "ready_for_approval",
      round: 2,
      summary: "Deletion scope confirmed and layout reflow requirements settled.",
      plan: "### Implementation Plan: Remove Social Links\n1. Locate Footer.tsx\n2. Prune links",
      draft_adr: null,
      questions: [],
    };

    const messages = [
      {
        id: "m-user-del",
        role: "user" as const,
        text: "remove social media links like github, x.com, etc",
        timestamp: Date.now() - 60000,
      },
      {
        id: "m-assistant-approval-del",
        role: "assistant" as const,
        timestamp: Date.now() - 10000,
        grillTurn: readyTurnWithoutAdr,
      },
    ];

    const { user } = renderStudio({
      messages,
      onApprovePlan: handleApprove,
    });

    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText("Plan Ready for Approval")).toBeInTheDocument();
    expect(screen.getByTestId("plan-details")).toHaveTextContent(/Remove Social Links/i);
    expect(screen.queryByTestId("draft-adr-preview")).not.toBeInTheDocument();

    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    await user.click(approveBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith(readyTurnWithoutAdr);
  });

  it("renders visual confirmation banner in timeline when isChatCleared is true", () => {
    renderStudio({
      selectedRepo: "cool-app",
      messages: [],
      isChatCleared: true,
    });

    expect(screen.getByTestId("chat-cleared-banner")).toBeInTheDocument();
    expect(screen.getByText("Chat history cleared for cool-app.")).toBeInTheDocument();
  });

  it("renders 'Issues' trigger button in top control bar with live open issues count and opens IssueDrawer on click", async () => {
    const handleOpenIssues = vi.fn();
    const { user } = renderStudio({
      selectedRepo: "cool-app",
      onOpenIssueDrawer: handleOpenIssues,
    });

    const issuesBtn = screen.getByTestId("studio-issues-btn");
    expect(issuesBtn).toBeInTheDocument();
    expect(issuesBtn).toHaveTextContent(/Issues/i);

    const badge = screen.getByTestId("studio-issues-badge");
    expect(badge).toBeInTheDocument();

    await user.click(issuesBtn);
    expect(handleOpenIssues).toHaveBeenCalledTimes(1);
  });

  it("opens IssueDrawer without interrupting live preview state or chat scroll history", async () => {
    const { user } = renderStudio({
      selectedRepo: "cool-app",
      previewState: {
        repo: "cool-app",
        status: "SERVING",
        branch: "factory/feature-live",
        preview_url: "https://cool-app-3000.modal.host",
        logs: [],
        error_message: null,
      },
      messages: [
        {
          id: "m-user-persist",
          role: "user",
          text: "Persistent chat item before drawer open",
          timestamp: Date.now(),
        },
      ],
    });

    // 1. Verify live preview and chat message are in the DOM
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/feature-live");
    expect(screen.getByText("Persistent chat item before drawer open")).toBeInTheDocument();

    // 2. Open drawer via top bar Issues button
    const issuesBtn = screen.getByTestId("studio-issues-btn");
    await user.click(issuesBtn);

    // 3. Drawer is visible
    expect(screen.getByTestId("studio-issue-drawer")).toBeInTheDocument();
    expect(screen.getByText("GitHub Issues")).toBeInTheDocument();

    // 4. Live preview and chat history remain intact and undisturbed
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/feature-live");
    expect(screen.getByText("Persistent chat item before drawer open")).toBeInTheDocument();
  });

  it("renders error callout banner with failure reason and diagnostic details when inference fails", () => {
    const errorTurn = {
      type: "error" as const,
      round: 1,
      questions: [],
      error_message: "Network connection error to OpenCode Go: Connection refused",
      error_details: "Provider: OpenCode Go (https://opencode.ai/zen/go/v1)\nException: ConnectError",
      summary: "Inference request failed: Connection refused",
    };

    const messages = [
      {
        id: "m-user-prompt",
        role: "user" as const,
        text: "Remove social media links from footer",
        timestamp: Date.now() - 30000,
      },
      {
        id: "m-assistant-error",
        role: "assistant" as const,
        timestamp: Date.now(),
        grillTurn: errorTurn,
      },
    ];

    renderStudio({ messages });

    expect(screen.getByTestId("grilling-error-banner")).toBeInTheDocument();
    expect(screen.getByText("Inference Service Error")).toBeInTheDocument();
    expect(screen.getByTestId("grilling-error-reason")).toHaveTextContent(
      "Network connection error to OpenCode Go: Connection refused"
    );
    expect(screen.getByTestId("grilling-error-details")).toHaveTextContent("https://opencode.ai/zen/go/v1");
    expect(screen.getByTestId("grilling-retry-btn")).toBeInTheDocument();
  });

  it("triggers retry action with the original user prompt when Retry button is clicked on error turn", async () => {
    const handleRetry = vi.fn();
    const handleSend = vi.fn();
    const errorTurn = {
      type: "error" as const,
      round: 1,
      questions: [],
      error_message: "HTTP 503 error from inference provider",
      error_details: "Endpoint: https://opencode.ai/zen/go/v1/chat/completions\nStatus: 503",
    };

    const messages = [
      {
        id: "m-user-orig",
        role: "user" as const,
        text: "Remove social media links from footer",
        timestamp: Date.now() - 30000,
      },
      {
        id: "m-assistant-err",
        role: "assistant" as const,
        timestamp: Date.now(),
        grillTurn: errorTurn,
      },
    ];

    const { user } = renderStudio({
      messages,
      onRetryTurn: handleRetry,
      onSendPrompt: handleSend,
    });

    const retryBtn = screen.getByTestId("grilling-retry-btn");
    await user.click(retryBtn);

    expect(handleRetry).toHaveBeenCalledWith("Remove social media links from footer");
  });


});
