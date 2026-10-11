import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StudioView } from "./StudioView";

const mockRepos = [
  { name: "cool-app", is_tanstack_compatible: true },
  { name: "test-app", is_tanstack_compatible: false },
];

describe("StudioView", () => {
  it("renders repo select, prompt input, send button and live preview", () => {
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send/i })).toBeInTheDocument();
    expect(screen.getByText("New App")).toBeInTheDocument();
  });

  it("handles prompt submission", () => {
    const handleSend = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={handleSend}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/Describe what you want to build/i);
    fireEvent.change(input, { target: { value: "Add a dark mode toggle" } });

    const sendBtn = screen.getByRole("button", { name: /Send/i });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith("Add a dark mode toggle");
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

    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={messages}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    expect(screen.getByText(/Request cannot be processed/i)).toBeInTheDocument();
    expect(screen.getByText(/Out-of-scope backend infrastructure modification/i)).toBeInTheDocument();
  });

  it("renders 'Preview App' button in top control bar next to repo selector and triggers onLaunchPreview", () => {
    const handleLaunch = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        onLaunchPreview={handleLaunch}
      />
    );

    const previewBtn = screen.getByTestId("preview-app-btn");
    expect(previewBtn).toBeInTheDocument();
    expect(previewBtn).toHaveTextContent(/Preview App/i);

    fireEvent.click(previewBtn);
    expect(handleLaunch).toHaveBeenCalledTimes(1);
  });

  it("renders red 'Stop' button in top control bar when preview is active and triggers onStopPreview", () => {
    const handleStop = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "SERVING",
          branch: "factory/feature-x",
          preview_url: "https://sandbox-3000.modal.host",
          sandbox_id: "sb-123",
          created_at: Date.now(),
          started_at: Date.now(),
          ended_at: null,
          error_message: null,
          log_count: 5,
        }}
        onStopPreview={handleStop}
      />
    );

    const stopBtn = screen.getByTestId("studio-stop-preview-btn");
    expect(stopBtn).toBeInTheDocument();
    expect(stopBtn).toHaveTextContent(/Stop/i);

    fireEvent.click(stopBtn);
    expect(handleStop).toHaveBeenCalledTimes(1);
  });

  it("dynamically updates preview pane when switching repositories without losing running state", () => {
    const handleSelect = vi.fn();
    const { rerender } = render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={handleSelect}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "SERVING",
          stage: "SERVING",
          branch: "factory/cool-feat",
          preview_url: "https://cool-app-3000.modal.host",
        }}
      />
    );

    // Initial repo preview
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/cool-feat");
    expect(screen.getByText("https://cool-app-3000.modal.host")).toBeInTheDocument();

    // Switch repo via dropdown
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "test-app" } });
    expect(handleSelect).toHaveBeenCalledWith("test-app");

    // Rerender with test-app active preview
    rerender(
      <StudioView
        repos={mockRepos}
        selectedRepo="test-app"
        onSelectRepo={handleSelect}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "test-app",
          status: "PROVISIONING",
          stage: "INSTALLING_DEPS",
          branch: "factory/test-feat",
          preview_url: null,
          logs: ["Installing dependencies..."],
        }}
      />
    );

    // Preview pane updates dynamically to test-app
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/test-feat");
    expect(screen.getByTestId("preview-progress-stepper")).toBeInTheDocument();
    expect(screen.getByTestId("preview-step-installing_deps")).toHaveAttribute("data-state", "active");
  });

  it("triggers onRetryPreview when retry is clicked in failed preview", () => {
    const handleRetry = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "FAILED",
          stage: "INSTALLING_DEPS",
          branch: "main",
          error_message: "Compilation error: module not found",
          logs: ["pnpm install failed"],
        }}
        onRetryPreview={handleRetry}
      />
    );

    const retryButtons = screen.getAllByTestId("retry-preview-btn");
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(retryButtons[0]);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it("locks prompt input and displays in-flight status indicator while assembly line turn is executing", () => {
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
      created_at: Date.now(),
      started_at: Date.now(),
      ended_at: null,
      exit_code: null,
      error_message: null,
      logs_count: 10,
    };

    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={runningJob}
        messages={[]}
        onSendPrompt={handleSend}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

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
    fireEvent.change(textarea, { target: { value: "Concurrent prompt" } });
    fireEvent.click(sendBtn);
    expect(handleSend).not.toHaveBeenCalled();
  });

  it("displays explicit 'Sandbox Disconnected' dialog on STOPPED status, preserves chat history, and triggers onReconnectPreview", () => {
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

    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={initialMessages}
        onSendPrompt={handleSend}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "STOPPED",
          branch: "factory/dashboard-overview",
          preview_url: "https://sandbox-3000.modal.host",
        }}
        onReconnectPreview={handleReconnect}
      />
    );

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

    fireEvent.click(reconnectBtn);
    expect(handleReconnect).toHaveBeenCalledTimes(1);
  });

  it("reloads preview iframe when manual Refresh button is clicked or refreshKey prop changes", () => {
    const { rerender } = render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "SERVING",
          stage: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://sandbox-3000.modal.host",
        }}
        refreshKey={0}
      />
    );

    const initialIframe = screen.getByTitle("Live Application Preview");
    expect(initialIframe).toBeInTheDocument();

    // Click explicit toolbar Refresh button
    const refreshBtn = screen.getByTestId("reload-preview-btn");
    fireEvent.click(refreshBtn);

    const reloadedIframe = screen.getByTitle("Live Application Preview");
    expect(reloadedIframe).toBeInTheDocument();
    expect(reloadedIframe).not.toBe(initialIframe);

    // Update refreshKey prop (simulating telemetry preview_refresh event)
    rerender(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        previewState={{
          repo: "cool-app",
          status: "SERVING",
          stage: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://sandbox-3000.modal.host",
        }}
        refreshKey={1}
      />
    );

    const streamReloadedIframe = screen.getByTitle("Live Application Preview");
    expect(streamReloadedIframe).toBeInTheDocument();
    expect(streamReloadedIframe).not.toBe(reloadedIframe);
  });
});


