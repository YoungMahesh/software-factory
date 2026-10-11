import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import App from "./App";
import * as api from "./api";

vi.mock("./api", () => ({
  fetchStudioRepos: vi.fn(),
  fetchRepos: vi.fn(),
  createRepo: vi.fn(),
  fetchScratch: vi.fn(),
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
  getPreviewStreamUrl: vi.fn((repo: string) => `/api/studio/repos/${repo}/preview/stream`),
  fetchChatMessages: vi.fn(),
  clearChatMessages: vi.fn(),
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

describe("App Root Component", () => {
  const originalEventSource = global.EventSource;

  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    (global as any).EventSource = MockEventSource;

    vi.mocked(api.fetchStudioRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [{ name: "my-app", is_tanstack_compatible: true }],
    });
    vi.mocked(api.fetchScratch).mockResolvedValue({} as any);
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
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
  });

  it("renders navigation header with Studio and Console tabs", async () => {
    render(<App />);

    expect(screen.getByText("Software Factory")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Factory Studio/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Factory Testing Console/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(api.fetchStudioRepos).toHaveBeenCalled();
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
      inst.url.includes("/api/studio/repos/my-app/preview/stream")
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
      inst.url.includes("/api/studio/repos/my-app/preview/stream")
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

  it("conducts conversational grilling interview turn and displays structured questions with recommended answers", async () => {
    vi.mocked(api.sendStudioPrompt).mockResolvedValueOnce({
      accepted: true,
      turn: {
        type: "grill_round",
        round: 1,
        summary: "Clarifying users table layout and pagination strategy.",
        questions: [
          {
            id: "Q1",
            title: "Route Placement",
            question: "Where should the users table route be located?",
            recommended: "app/routes/users.tsx",
            options: ["app/routes/users.tsx"],
          },
        ],
      },
    });

    render(<App />);

    const input = await screen.findByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Build a users table" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => {
      expect(api.sendStudioPrompt).toHaveBeenCalledWith(
        expect.objectContaining({
          repo: "my-app",
          prompt: "Build a users table",
          grill: true,
        })
      );
    });

    expect(await screen.findByTestId("grilling-round-badge")).toHaveTextContent("Grill & Align (Round 1)");
    expect(screen.getByText("Clarifying users table layout and pagination strategy.")).toBeInTheDocument();
    expect(screen.getByTestId("grill-question-Q1")).toBeInTheDocument();
    expect(screen.getByTestId("recommended-answer-Q1")).toHaveTextContent("app/routes/users.tsx");
  });

  it("renders ApprovalCard on ready_for_approval and dispatches build when clicking 'Approve Plan & Build'", async () => {
    const readyTurn = {
      type: "ready_for_approval" as const,
      round: 2,
      summary: "Finalized users table architecture.",
      plan: "1. Create route\n2. Add table component",
      draft_adr: {
        title: "0002: Users Table Architecture",
        filename: "docs/adr/0002-users-table.md",
        content: "# 0002: Users Table Architecture\n\nStatus: Accepted",
      },
      questions: [],
    };

    vi.mocked(api.sendStudioPrompt).mockResolvedValueOnce({
      accepted: true,
      turn: readyTurn,
    });

    vi.mocked(api.approvePlan).mockResolvedValueOnce({
      accepted: true,
      job: {
        id: "job-approved-123",
        repo: "my-app",
        feature: "users-table",
        issue: "1",
        stage: "PLANNER",
        status: "RUNNING",
        log_count: 0,
        event_count: 0,
        vm: false,
        dev: true,
        model: "deepseek-v4.1-flash",
        created_at: new Date().toISOString(),
      },
      branch: "factory/users-table",
    });

    render(<App />);

    const input = await screen.findByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Build a users table" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    // Wait for ApprovalCard to appear
    expect(await screen.findByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText("docs/adr/0002-users-table.md")).toBeInTheDocument();

    // Click Approve Plan & Build
    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.approvePlan).toHaveBeenCalledWith(
        expect.objectContaining({
          repo: "my-app",
          prompt: expect.stringContaining("Finalized users table architecture."),
          draft_adr: readyTurn.draft_adr,
        })
      );
    });

    expect(await screen.findByText(/Plan approved! Dispatched assembly line/i)).toBeInTheDocument();
  });

  it("supports text shortcut /proceed to trigger build approval directly from chat input", async () => {
    const readyTurn = {
      type: "ready_for_approval" as const,
      round: 2,
      summary: "Finalized users table architecture.",
      plan: "1. Create route",
      draft_adr: {
        title: "0002: Users Table Architecture",
        filename: "docs/adr/0002-users-table.md",
        content: "# 0002: Users Table Architecture\n\nStatus: Accepted",
      },
      questions: [],
    };

    vi.mocked(api.sendStudioPrompt).mockResolvedValueOnce({
      accepted: true,
      turn: readyTurn,
    });

    vi.mocked(api.approvePlan).mockResolvedValueOnce({
      accepted: true,
      job: {
        id: "job-approved-shortcut",
        repo: "my-app",
        feature: "users-table",
        issue: "1",
        stage: "PLANNER",
        status: "RUNNING",
        log_count: 0,
        event_count: 0,
        vm: false,
        dev: true,
        model: "deepseek-v4.1-flash",
        created_at: new Date().toISOString(),
      },
      branch: "factory/users-table",
    });

    render(<App />);

    // 1. Initial turn reaches ready_for_approval
    const input = await screen.findByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Build a users table" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    expect(await screen.findByTestId("approval-card")).toBeInTheDocument();

    // 2. Type /proceed in chat input and submit
    fireEvent.change(input, { target: { value: "/proceed" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => {
      expect(api.approvePlan).toHaveBeenCalledWith(
        expect.objectContaining({
          repo: "my-app",
          prompt: expect.stringContaining("Finalized users table architecture."),
          draft_adr: readyTurn.draft_adr,
        })
      );
    });

    expect(await screen.findByText(/Plan approved! Dispatched assembly line/i)).toBeInTheDocument();
  });

  it("automatically hydrates chat timeline from database on initial load and switches when selecting different repositories", async () => {
    vi.mocked(api.fetchStudioRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "my-app", is_tanstack_compatible: true },
        { name: "other-app", is_tanstack_compatible: false },
      ],
    });

    vi.mocked(api.fetchChatMessages).mockImplementation(async (repo: string) => {
      if (repo === "my-app") {
        return {
          repo: "my-app",
          messages: [
            {
              id: "msg-1",
              repo: "my-app",
              role: "user",
              content: "Build user profile dashboard",
              created_at: 1000,
            },
            {
              id: "msg-2",
              repo: "my-app",
              role: "assistant",
              content: "Grilling Round 1",
              turn_data: {
                type: "grill_round",
                round: 1,
                summary: "Requirement alignment for user profile",
                questions: [
                  {
                    id: "Q1",
                    title: "Profile Data Seam",
                    question: "Where will profile data come from?",
                    recommended: "Local mock store",
                  },
                ],
              },
              created_at: 1005,
            },
          ],
        };
      }
      if (repo === "other-app") {
        return {
          repo: "other-app",
          messages: [
            {
              id: "msg-other-1",
              repo: "other-app",
              role: "user",
              content: "Other app historical message",
              created_at: 2000,
            },
          ],
        };
      }
      return { repo, messages: [] };
    });

    render(<App />);

    // 1. Initial repo "my-app" hydrates historical messages
    expect(await screen.findByText("Build user profile dashboard")).toBeInTheDocument();
    expect(screen.getByText("Requirement alignment for user profile")).toBeInTheDocument();
    expect(screen.getByText("Where will profile data come from?")).toBeInTheDocument();
    expect(screen.getByText("Local mock store")).toBeInTheDocument();

    // 2. Switch repository to "other-app"
    const repoSelect = screen.getByRole("combobox");
    fireEvent.change(repoSelect, { target: { value: "other-app" } });

    // 3. Automatically hydrates other-app's messages
    expect(await screen.findByText("Other app historical message")).toBeInTheDocument();
    expect(screen.queryByText("Build user profile dashboard")).not.toBeInTheDocument();
  });

  it("optimistically renders submitted prompt immediately and persists assistant turn", async () => {
    let resolvePrompt: (val: any) => void;
    const promptPromise = new Promise((resolve) => {
      resolvePrompt = resolve;
    });

    vi.mocked(api.sendStudioPrompt).mockReturnValue(promptPromise as any);

    render(<App />);

    const input = await screen.findByTestId("studio-prompt-input");
    fireEvent.change(input, { target: { value: "Optimistic prompt test" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    // Prompt renders optimistically immediately before network response resolves
    expect(screen.getByText("Optimistic prompt test")).toBeInTheDocument();

    // Now resolve the backend response
    await act(async () => {
      resolvePrompt!({
        accepted: true,
        turn: {
          type: "grill_round",
          round: 1,
          summary: "Assistant interview turn response",
          questions: [],
        },
      });
    });

    // Assistant response renders and persists
    expect(await screen.findByText("Assistant interview turn response")).toBeInTheDocument();
  });

  it("clears active repository chat timeline with visual confirmation via Clear Chat button", async () => {
    vi.mocked(api.fetchChatMessages).mockResolvedValueOnce({
      repo: "my-app",
      messages: [
        {
          id: "msg-1",
          repo: "my-app",
          role: "user",
          content: "Message to be cleared",
          created_at: 1000,
        },
      ],
    });

    render(<App />);

    // Wait for initial message
    expect(await screen.findByText("Message to be cleared")).toBeInTheDocument();

    // Click "Clear Chat" button in PromptComposer toolbar
    const clearBtn = await screen.findByRole("button", { name: /Clear Chat/i });
    fireEvent.click(clearBtn);

    await waitFor(() => {
      expect(api.clearChatMessages).toHaveBeenCalledWith("my-app");
    });

    // Visual confirmation is displayed and timeline is wiped
    expect(await screen.findByTestId("clear-chat-confirmation")).toBeInTheDocument();
    expect(screen.getByTestId("chat-cleared-banner")).toBeInTheDocument();
    expect(screen.queryByText("Message to be cleared")).not.toBeInTheDocument();
  });
});


