import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import App, { STORAGE_KEY_SELECTED_REPO } from "./App";
import * as api from "./api";

vi.mock("./api", () => ({
  fetchRepos: vi.fn(),
  createRepo: vi.fn(),
  fetchMilestones: vi.fn(),
  fetchIssues: vi.fn(),
  launchJob: vi.fn(),
  sendStudioPrompt: vi.fn(),
  approvePlan: vi.fn(),
  listJobs: vi.fn(),
  getJob: vi.fn(),
  cancelJob: vi.fn(),
  fetchPreview: vi.fn(),
  launchPreview: vi.fn(),
  stopPreview: vi.fn(),
  getPreviewStreamUrl: vi.fn((repo: string) => `/api/repos/${repo}/preview/stream`),
  fetchChatMessages: vi.fn(),
  clearChatMessages: vi.fn(),
  dispatchStudio: vi.fn(),
  fetchRepoBranches: vi.fn(),
  updatePreviewBranch: vi.fn(),
}));

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

describe("App Root - Navigation & Lifecycle", () => {
  const originalEventSource = global.EventSource;

  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    (global as any).EventSource = MockEventSource;

    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [{ name: "my-app", is_tanstack_compatible: true }],
    });
    vi.mocked(api.fetchMilestones).mockResolvedValue({ repo: "my-app", milestones: [] });
    vi.mocked(api.fetchIssues).mockResolvedValue({ repo: "my-app", issues: [] });
    vi.mocked(api.listJobs).mockResolvedValue({ jobs: [] });
    vi.mocked(api.fetchPreview).mockResolvedValue({
      repo: "my-app",
      status: "SERVING",
      stage: "SERVING",
      branch: "factory/feature-checkout",
      preview_url: "https://sb-1-3000.modal.host",
      sandbox_id: "sb-1",
      created_at: Date.now(),
      started_at: Date.now(),
      ended_at: null,
      error_message: null,
      logs: ["Vite dev server running on port 3000"],
      log_count: 1,
    });
    vi.mocked(api.fetchChatMessages).mockResolvedValue({
      repo: "my-app",
      messages: [],
    });
    vi.mocked(api.clearChatMessages).mockResolvedValue({
      repo: "my-app",
      deleted: 0,
      success: true,
    });
    vi.mocked(api.fetchRepoBranches).mockResolvedValue({
      repo: "my-app",
      org: "software-factory-09-test",
      branches: ["main", "factory/feature-checkout"],
      default_branch: "main",
    });
    vi.mocked(api.updatePreviewBranch).mockImplementation(async (repo: string, branch: string) => {
      vi.mocked(api.fetchPreview).mockResolvedValue({
        repo,
        status: "SERVING",
        stage: "SERVING",
        branch,
        preview_url: "https://sb-1-3000.modal.host",
        sandbox_id: "sb-1",
        created_at: Date.now(),
        started_at: Date.now(),
        ended_at: null,
        error_message: null,
        logs: ["Vite dev server running on port 3000"],
        log_count: 1,
      });
      return {
        repo,
        branch,
        status: "SERVING",
        preview_url: "https://sb-1-3000.modal.host",
        in_place: true,
        success: true,
      };
    });
    localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  afterEach(() => {
    localStorage.clear();
    window.history.replaceState(null, "", "/");
    global.EventSource = originalEventSource;
  });

  it("renders navigation header with product branding, active job indicator, and repo badge without switcher tabs", async () => {
    render(<App />);

    expect(screen.getByText("Software Factory")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Factory Studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Factory Testing Console/i })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("my-app").length).toBeGreaterThanOrEqual(1);
    });
    const navHeader = screen.getByRole("banner");
    expect(within(navHeader).queryByText("my-app")).toBeNull();
  });

  it("handles container timeout disconnect, preserves chat history, and reconnects to active branch", async () => {
    vi.mocked(api.sendStudioPrompt).mockResolvedValue({
      accepted: true,
      job: {
        id: "job-turn-1",
        repo: "my-app",
        feature: "feature-checkout",
        issue: "1",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        status: "RUNNING",
        stage: "CODER",
        created_at: Date.now(),
        started_at: Date.now(),
        ended_at: null,
        exit_code: null,
        error_message: null,
        logs_count: 5,
      },
      preview_url: "https://sb-1-3000.modal.host",
    });

    vi.mocked(api.launchPreview).mockResolvedValue({
      repo: "my-app",
      status: "SERVING",
      stage: "SERVING",
      branch: "factory/feature-checkout",
      preview_url: "https://sb-2-3000.modal.host",
      sandbox_id: "sb-2",
      created_at: Date.now(),
      started_at: Date.now(),
      ended_at: null,
      error_message: null,
      logs: ["Reconnected dev server"],
      log_count: 1,
    });

    render(<App />);

    // Wait for initial repo and preview load
    await waitFor(() => {
      expect(api.fetchPreview).toHaveBeenCalledWith("my-app");
    });

    // 1. Submit a prompt to generate conversation history
    const input = await screen.findByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Implement checkout cart modal" } });
    const sendBtn = screen.getByRole("button", { name: /Send/i });
    fireEvent.click(sendBtn);

    // Wait for prompt dispatch and assistant turn to mount
    await screen.findByText(/Dispatched assembly line/i);

    // Complete agent job turn via telemetry stream
    const jobEs = MockEventSource.instances.find((inst) =>
      inst.url.includes("/api/jobs/job-turn-1/stream")
    );
    expect(jobEs).toBeDefined();
    act(() => {
      jobEs?.onmessage?.({
        data: JSON.stringify({
          event: "init",
          job: {
            id: "job-turn-1",
            status: "RUNNING",
            stage: "CODER",
          },
        }),
      });
      jobEs?.onmessage?.({
        data: JSON.stringify({
          event: "status",
          status: "SUCCESS",
        }),
      });
    });

    // Find the preview SSE connection instance
    const previewEs = MockEventSource.instances.find((inst) =>
      inst.url.includes("/api/repos/my-app/preview/stream")
    );
    expect(previewEs).toBeDefined();

    // 2. Simulate container idle timeout transition to STOPPED
    act(() => {
      previewEs?.onmessage?.({
        data: JSON.stringify({
          event: "status",
          status: "STOPPED",
        }),
      });
    });

    // 3. Verify explicit Sandbox Disconnected dialog is displayed
    const dialog = await screen.findByTestId("sandbox-disconnected-dialog");
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("Sandbox Disconnected")).toBeInTheDocument();

    // 4. Verify conversation history is fully preserved across container disconnection
    expect(screen.getByText("Implement checkout cart modal")).toBeInTheDocument();

    // 5. Verify prompt input is locked while disconnected
    expect(screen.getByTestId("studio-prompt-input")).toBeDisabled();

    // 6. Click "Reconnect Environment" in dialog
    const reconnectBtn = within(dialog).getByTestId("reconnect-environment-btn");
    await act(async () => {
      fireEvent.click(reconnectBtn);
    });

    // 7. Verify launchPreview was called with active remote branch
    expect(api.launchPreview).toHaveBeenCalledWith("my-app", "factory/feature-checkout");

    // 8. Verify dialog closes, new tunnel URL is attached, and input is unlocked
    await waitFor(() => {
      expect(screen.queryByTestId("sandbox-disconnected-dialog")).toBeNull();
      expect(screen.getByTestId("studio-prompt-input")).not.toBeDisabled();
      expect(screen.getByText("https://sb-2-3000.modal.host")).toBeInTheDocument();
    });

    // Chat history remains preserved after reconnect
    expect(screen.getByText("Implement checkout cart modal")).toBeInTheDocument();
  });

  it("triggers iframe reload upon receiving preview_refresh telemetry event", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchPreview).toHaveBeenCalledWith("my-app");
    });

    const iframeBefore = await screen.findByTitle("Live Application Preview");
    expect(iframeBefore).toBeInTheDocument();

    // Find preview SSE instance
    const previewEs = MockEventSource.instances.find((inst) =>
      inst.url.includes("/api/repos/my-app/preview/stream")
    );
    expect(previewEs).toBeDefined();

    // Send preview_refresh event over telemetry stream
    act(() => {
      previewEs?.onmessage?.({
        data: JSON.stringify({
          event: "preview_refresh",
          repo: "my-app",
        }),
      });
    });

    // Verify iframe reloads cleanly
    const iframeAfter = await screen.findByTitle("Live Application Preview");
    expect(iframeAfter).toBeInTheDocument();
  });

  it("triggers iframe reload upon receiving preview_refresh from job telemetry stream", async () => {
    vi.mocked(api.sendStudioPrompt).mockResolvedValue({
      accepted: true,
      job: {
        id: "job-turn-telemetry",
        repo: "my-app",
        feature: "checkout",
        issue: "1",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        status: "RUNNING",
        stage: "CODER",
        created_at: Date.now(),
        started_at: Date.now(),
        ended_at: null,
        exit_code: null,
        error_message: null,
        logs_count: 5,
      },
      preview_url: "https://sb-1-3000.modal.host",
    });

    render(<App />);

    await waitFor(() => {
      expect(api.fetchPreview).toHaveBeenCalledWith("my-app");
    });

    const iframeBefore = await screen.findByTitle("Live Application Preview");
    expect(iframeBefore).toBeInTheDocument();

    // Submit prompt to launch active job
    const input = screen.getByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Build checkout" } });
    fireEvent.submit(screen.getByRole("button", { name: /Send/i }));

    // Wait for prompt dispatch
    await screen.findByText(/Dispatched assembly line/i);

    // Find job telemetry stream EventSource
    const jobEs = MockEventSource.instances.find((inst) =>
      inst.url.includes("/api/jobs/job-turn-telemetry/stream")
    );
    expect(jobEs).toBeDefined();

    // Send preview_refresh event over job telemetry stream
    act(() => {
      jobEs?.onmessage?.({
        data: JSON.stringify({
          event: "preview_refresh",
        }),
      });
    });

    // Verify iframe reloads cleanly
    const iframeAfter = await screen.findByTitle("Live Application Preview");
    expect(iframeAfter).toBeInTheDocument();
  });

  it("displays coral error counter badge on navigation Activity Drawer button when active job encounters failed commands and routes to Failed Commands tab", async () => {
    vi.mocked(api.sendStudioPrompt).mockResolvedValue({
      accepted: true,
      job: {
        id: "job-turn-errors",
        repo: "my-app",
        feature: "checkout",
        issue: "1",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        status: "RUNNING",
        stage: "CODER",
        created_at: Date.now(),
        started_at: Date.now(),
        ended_at: null,
        exit_code: null,
        error_message: null,
        logs_count: 5,
      },
      preview_url: "https://sb-1-3000.modal.host",
    });

    render(<App />);

    await waitFor(() => {
      expect(api.fetchPreview).toHaveBeenCalledWith("my-app");
    });

    // Before any job, navigation error badge must be absent
    expect(screen.queryByTestId("nav-failed-commands-badge")).toBeNull();

    // Submit prompt to launch active job
    const input = screen.getByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Build checkout" } });
    fireEvent.submit(screen.getByRole("button", { name: /Send/i }));

    await screen.findByText(/Dispatched assembly line/i);

    const jobEs = MockEventSource.instances.find((inst) =>
      inst.url.includes("/api/jobs/job-turn-errors/stream")
    );
    expect(jobEs).toBeDefined();

    // Initially zero failed commands, badge must not be visible
    expect(screen.queryByTestId("nav-failed-commands-badge")).toBeNull();

    // Stream a failed bash command tool result
    act(() => {
      jobEs?.onmessage?.({
        data: JSON.stringify({
          event: "agent_event",
          data: {
            type: "tool_result",
            stage: "CODER",
            data: {
              toolName: "bash",
              command: "pnpm add @stripe/stripe-js",
              cwd: "/root/workspace",
              exitCode: 1,
              isError: true,
              output: "ERR_PNPM_FETCH_404: Package not found",
              stderr: "ERR_PNPM_FETCH_404: Package not found",
              durationMs: 1200,
            },
          },
        }),
      });
    });

    // Verify navigation badge renders with count 1
    const badge = await screen.findByTestId("nav-failed-commands-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("1");
    expect(badge.className).toContain("bg-coral");

    // Click the navigation Activity button
    const activityBtn = screen.getByTestId("nav-activity-drawer-btn");
    fireEvent.click(activityBtn);

    // Verify ActivityDrawer opens directly into Failed Commands tab
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByTestId("failed-commands-job-selector")).toBeInTheDocument();
      expect(screen.getByText("pnpm add @stripe/stripe-js")).toBeInTheDocument();
      expect(screen.getByText("ERR_PNPM_FETCH_404: Package not found")).toBeInTheDocument();
    });
  });

  it("renders clickable active job pill in navigation, opens drawer on pill click, and triggers cancelJob on inline cancel click", async () => {
    vi.mocked(api.sendStudioPrompt).mockResolvedValue({
      accepted: true,
      job: {
        id: "job-cancel-test",
        repo: "my-app",
        feature: "checkout",
        issue: "1",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        status: "RUNNING",
        stage: "CODER",
        created_at: Date.now(),
        started_at: Date.now(),
        ended_at: null,
        exit_code: null,
        error_message: null,
        logs_count: 0,
      },
      preview_url: "https://sb-1-3000.modal.host",
    });

    render(<App />);
    await waitFor(() => expect(api.fetchPreview).toHaveBeenCalledWith("my-app"));

    const input = screen.getByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Run cancel test" } });
    fireEvent.submit(screen.getByRole("button", { name: /Send/i }));

    const pill = await screen.findByTestId("nav-active-job-indicator");
    expect(pill).toHaveTextContent("CODER");
    expect(pill).toHaveTextContent("job-cancel-test");

    const cancelBtn = within(pill).getByTestId("nav-cancel-job-btn");
    fireEvent.click(cancelBtn);
    expect(api.cancelJob).toHaveBeenCalledWith("job-cancel-test");
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(pill);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
  });
});

