import { screen, within, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StudioView } from "./StudioView";
import { renderWithProviders } from "../test/test-utils";
import { StudioContextValue } from "../context/StudioContext";
import * as api from "../api";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchIssues: vi.fn().mockResolvedValue({ repo: "cool-app", issues: [] }),
    fetchPullRequests: vi.fn().mockResolvedValue({ repo: "cool-app", pulls: [] }),
    mergePullRequest: vi.fn(),
  };
});

const renderStudio = (overrides: Partial<StudioContextValue> = {}) =>
  renderWithProviders(<StudioView />, { contextOverrides: overrides });

describe("StudioView", () => {
  it("renders private badge when selected repository is private", () => {
    renderStudio({
      repos: [
        { name: "private-app", is_tanstack_compatible: true, private: true },
        { name: "public-app", is_tanstack_compatible: true, private: false },
      ],
      selectedRepo: "private-app",
    });

    expect(screen.getByTestId("studio-repo-private-badge")).toBeInTheDocument();
    expect(screen.getByTestId("studio-repo-private-badge")).toHaveTextContent(/Private/i);
    expect(screen.getByRole("option", { name: /private-app ✦ 🔒/i })).toBeInTheDocument();
  });

  it("renders repo select, prompt input, send button and live preview", () => {
    renderStudio();

    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send/i })).toBeInTheDocument();
    expect(screen.getByText("New App")).toBeInTheDocument();
  });

  it("handles prompt submission", async () => {
    const handleSend = vi.fn();
    const { user } = renderStudio({ onSendPrompt: handleSend });

    const input = screen.getByPlaceholderText(/Describe what you want to build/i);
    await user.type(input, "Add a dark mode toggle");

    const sendBtn = screen.getByRole("button", { name: /Send/i });
    await user.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith("Add a dark mode toggle", true);
  });

  it("renders refusal card when intent guard rejects prompt", () => {
    const messages = [
      {
        id: "m-1",
        role: "assistant" as const,
        timestamp: Date.now(),
        refusal: {
          message: "Request cannot be processed because it falls outside frontend scope.",
          reason: "Out-of-scope backend infrastructure modification",
          category: "out_of_scope",
        },
      },
    ];

    renderStudio({ messages });

    expect(screen.getByText(/Request cannot be processed/i)).toBeInTheDocument();
    expect(screen.getByText(/Out-of-scope backend infrastructure modification/i)).toBeInTheDocument();
  });

  it("renders 'Preview App' button in top control bar next to repo selector and triggers onLaunchPreview", async () => {
    const handleLaunch = vi.fn();
    const { user } = renderStudio({ onLaunchPreview: handleLaunch });

    const previewBtn = screen.getByTestId("preview-app-btn");
    expect(previewBtn).toBeInTheDocument();
    expect(previewBtn).toHaveTextContent(/Preview App/i);

    await user.click(previewBtn);
    expect(handleLaunch).toHaveBeenCalledTimes(1);
  });

  it("renders red 'Stop' button in top control bar when preview is active and triggers onStopPreview", async () => {
    const handleStop = vi.fn();
    const { user } = renderStudio({
      previewState: {
        repo: "cool-app",
        status: "SERVING",
        branch: "factory/feature-x",
        preview_url: "https://sandbox-3000.modal.host",
        logs: [],
        error_message: null,
      },
      onStopPreview: handleStop,
    });

    const stopBtn = screen.getByTestId("studio-stop-preview-btn");
    expect(stopBtn).toBeInTheDocument();
    expect(stopBtn).toHaveTextContent(/Stop/i);

    await user.click(stopBtn);
    expect(handleStop).toHaveBeenCalledTimes(1);
  });

  it("dynamically updates preview pane when switching repositories without losing running state", async () => {
    const handleSelect = vi.fn();
    const { user, rerenderWithContext } = renderStudio({
      selectedRepo: "cool-app",
      onSelectRepo: handleSelect,
      previewState: {
        repo: "cool-app",
        status: "SERVING",
        branch: "factory/cool-feat",
        preview_url: "https://cool-app-3000.modal.host",
        logs: [],
        error_message: null,
      },
    });

    // Initial repo preview
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/cool-feat");
    expect(screen.getByText("https://cool-app-3000.modal.host")).toBeInTheDocument();

    // Switch repo via dropdown
    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "test-app");
    expect(handleSelect).toHaveBeenCalledWith("test-app");

    // Rerender with test-app active preview
    rerenderWithContext({
      selectedRepo: "test-app",
      previewState: {
        repo: "test-app",
        status: "PROVISIONING",
        stage: "INSTALLING_DEPS",
        branch: "factory/test-feat",
        preview_url: null,
        logs: ["Installing dependencies..."],
        error_message: null,
      },
    });

    // Preview pane updates dynamically to test-app
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/test-feat");
    expect(screen.getByTestId("preview-progress-stepper")).toBeInTheDocument();
    expect(screen.getByTestId("preview-step-installing_deps")).toHaveAttribute("data-state", "active");
  });

  it("triggers onRetryPreview when retry is clicked in failed preview", async () => {
    const handleRetry = vi.fn();
    const { user } = renderStudio({
      previewState: {
        repo: "cool-app",
        status: "FAILED",
        branch: "main",
        preview_url: null,
        error_message: "Compilation error: module not found",
        logs: ["pnpm install failed"],
      },
      onRetryPreview: handleRetry,
    });

    const retryButtons = screen.getAllByTestId("retry-preview-btn");
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);

    await user.click(retryButtons[0]);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it("locks prompt input and displays in-flight status indicator while assembly line turn is executing", async () => {
    const handleSend = vi.fn();
    const runningJob = {
      id: "job-turn-1",
      repo: "cool-app",
      feature: "auth",
      issue: "1",
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: true,
      status: "RUNNING" as const,
      stage: "CODER" as const,
      created_at: "2026-10-11T00:00:00Z",
      log_count: 10,
      event_count: 5,
    };

    const { user } = renderStudio({
      activeJob: runningJob,
      onSendPrompt: handleSend,
    });

    // Verify in-flight status indicator is visible
    const inFlightIndicator = screen.getByTestId("in-flight-indicator");
    expect(inFlightIndicator).toBeInTheDocument();
    expect(inFlightIndicator).toHaveTextContent(/in progress|CODER/i);

    // Verify prompt textarea and send button are disabled
    const textarea = screen.getByTestId("studio-prompt-input");
    expect(textarea).toBeDisabled();

    const sendBtn = screen.getByRole("button", { name: /Send/i });
    expect(sendBtn).toBeDisabled();

    // Verify prompt submission is prevented
    await user.click(sendBtn);
    expect(handleSend).not.toHaveBeenCalled();
  });

  it("displays explicit 'Sandbox Disconnected' dialog on STOPPED status, preserves chat history, and triggers onReconnectPreview", async () => {
    const handleReconnect = vi.fn();
    const handleSend = vi.fn();

    const initialMessages = [
      {
        id: "m-user-1",
        role: "user" as const,
        text: "Please add a dashboard overview component",
        timestamp: Date.now() - 60000,
      },
      {
        id: "m-assistant-1",
        role: "assistant" as const,
        text: "Generated dashboard overview component in src/components/Dashboard.tsx",
        timestamp: Date.now() - 30000,
      },
    ];

    const { user } = renderStudio({
      messages: initialMessages,
      onSendPrompt: handleSend,
      previewState: {
        repo: "cool-app",
        status: "STOPPED",
        branch: "factory/dashboard-overview",
        preview_url: null,
        logs: [],
        error_message: null,
      },
      onReconnectPreview: handleReconnect,
    });

    // 1. Verify "Sandbox Disconnected" dialog is displayed
    const dialog = screen.getByTestId("sandbox-disconnected-dialog");
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("Sandbox Disconnected")).toBeInTheDocument();
    expect(within(dialog).getByText(/30-minute idle timeout|stopped state/i)).toBeInTheDocument();

    // 2. Verify chat history is fully preserved across disconnection
    expect(screen.getByText("Please add a dashboard overview component")).toBeInTheDocument();
    expect(screen.getByText("Generated dashboard overview component in src/components/Dashboard.tsx")).toBeInTheDocument();

    // 3. Verify prompt input and send button are disabled in disconnected state
    const textarea = screen.getByTestId("studio-prompt-input");
    expect(textarea).toBeDisabled();
    const sendBtn = screen.getByRole("button", { name: /Send/i });
    expect(sendBtn).toBeDisabled();

    // 4. Verify clicking "Reconnect Environment" triggers onReconnectPreview
    const reconnectBtn = within(dialog).getByTestId("reconnect-environment-btn");
    expect(reconnectBtn).toBeInTheDocument();
    expect(reconnectBtn).toHaveTextContent(/Reconnect Environment/i);

    await user.click(reconnectBtn);
    expect(handleReconnect).toHaveBeenCalledTimes(1);
  });

  it("reloads preview iframe when manual Refresh button is clicked or refreshKey prop changes", async () => {
    const { user, rerenderWithContext } = renderStudio({
      previewState: {
        repo: "cool-app",
        status: "SERVING",
        branch: "factory/feature-1",
        preview_url: "https://sandbox-3000.modal.host",
        logs: [],
        error_message: null,
      },
      refreshKey: 0,
    });

    const initialIframe = screen.getByTitle("Live Application Preview");
    expect(initialIframe).toBeInTheDocument();

    // Click explicit toolbar Refresh button
    const refreshBtn = screen.getByTestId("reload-preview-btn");
    await user.click(refreshBtn);

    const reloadedIframe = screen.getByTitle("Live Application Preview");
    expect(reloadedIframe).toBeInTheDocument();
    expect(reloadedIframe).not.toBe(initialIframe);

    // Update refreshKey prop (simulating telemetry preview_refresh event)
    rerenderWithContext({
      previewState: {
        repo: "cool-app",
        status: "SERVING",
        branch: "factory/feature-1",
        preview_url: "https://sandbox-3000.modal.host",
        logs: [],
        error_message: null,
      },
      refreshKey: 1,
    });

    const streamReloadedIframe = screen.getByTitle("Live Application Preview");
    expect(streamReloadedIframe).toBeInTheDocument();
    expect(streamReloadedIframe).not.toBe(reloadedIframe);
  });

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

    // In Draft status, merge button in popover is disabled
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

  it("renders DeliveryGateCard in conversational timeline for delivery gate message", async () => {
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

  it("disables merge button and displays active job warning in popover when job is running", async () => {
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
});

