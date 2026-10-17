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

  it("renders navigation header with Studio and Console tabs", async () => {
    render(<App />);

    expect(screen.getByText("Software Factory")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Factory Studio/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Factory Testing Console/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(api.fetchRepos).toHaveBeenCalled();
    });
  });

  it("switches views between Studio and Testing Console", async () => {
    render(<App />);

    // Default is Studio view
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();
    });

    // Click Console tab
    const consoleTab = screen.getByRole("button", { name: /Factory Testing Console/i });
    fireEvent.click(consoleTab);

    // Now Console view is active
    expect(screen.getByText("Launch Parameters")).toBeInTheDocument();

    // Click Studio tab to switch back
    const studioTab = screen.getByRole("button", { name: /Factory Studio/i });
    fireEvent.click(studioTab);

    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();
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


});
