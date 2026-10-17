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

describe("StudioView - Core", () => {
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

  it("renders StudioHeader cleanly without floating status badge or duplicate telemetry buttons even when active job is present", () => {
    const { container } = renderStudio({
      activeJob: {
        id: "job-studio-badge-test",
        repo: "cool-app",
        feature: "auth",
        issue: "1",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        status: "RUNNING",
        stage: "CODER",
        created_at: "2026-10-11T00:00:00Z",
        log_count: 10,
        event_count: 5,
      },
    });

    expect(container.querySelector("#studio-floating-status-badge")).toBeNull();
    expect(container.querySelector("#btn-studio-activity")).toBeNull();
    expect(container.querySelector("#btn-inspect-logs")).toBeNull();
    expect(container.querySelector("#btn-studio-cancel")).toBeNull();
  });
});
