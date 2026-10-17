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

describe("App Root - Instant Dispatch & Branches", () => {
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

  it("opens IssueDrawer, triggers Instant Dispatch, and updates active job and live preview", async () => {
    vi.mocked(api.fetchIssues).mockResolvedValue({
      repo: "my-app",
      issues: [
        {
          number: 101,
          title: "Build landing hero section",
          state: "open",
          status: "ready-for-agent",
          labels: ["factory:ready"],
          blocked_by: [],
          milestone: {
            number: 1,
            title: "v1: Landing Page",
            slug: "v1-landing-page",
          },
        },
      ],
    });

    vi.mocked(api.dispatchStudio).mockResolvedValue({
      accepted: true,
      job: {
        id: "job-landing-101",
        repo: "my-app",
        feature: "v1-landing-page",
        issue: "101",
        model: "deepseek-v4.1-flash",
        vm: false,
        dev: true,
        preview_url: "https://landing-101-3000.modal.host",
        status: "RUNNING",
        stage: "CODER",
        created_at: "2026-10-11T00:00:00Z",
        log_count: 0,
        event_count: 0,
      },
      issue_number: 101,
      milestone_slug: "v1-landing-page",
      branch: "factory/v1-landing-page",
      target_branch: "factory/v1-landing-page",
      preview_url: "https://landing-101-3000.modal.host",
      preview: {
        status: "SERVING",
        branch: "factory/v1-landing-page",
        preview_url: "https://landing-101-3000.modal.host",
        logs: [],
        error_message: null,
      },
      stage: "CODER",
    });

    render(<App />);

    // 1. Open IssueDrawer
    const issuesBtn = await screen.findByTestId("studio-issues-btn");
    fireEvent.click(issuesBtn);

    // 2. Drawer renders with issue 101
    expect(await screen.findByText("Build landing hero section")).toBeInTheDocument();

    // 3. Click Instant Dispatch
    const dispatchBtn = screen.getByTestId("instant-dispatch-btn-101");
    fireEvent.click(dispatchBtn);

    // 4. Verify dispatch endpoint was called
    await waitFor(() => {
      expect(api.dispatchStudio).toHaveBeenCalledWith(
        expect.objectContaining({
          repo: "my-app",
          issue_number: 101,
          milestone_slug: "v1-landing-page",
        })
      );
    });

    // 5. Active job badge in top control bar updates with job ID and stage
    expect(await screen.findByText("job-landing-101")).toBeInTheDocument();
    expect(screen.getAllByText("CODER").length).toBeGreaterThanOrEqual(1);

    // 6. Live preview updates
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/v1-landing-page");
  });

  it("renders Live Preview Branch Selector, switches branch via dropdown, and updates preview", async () => {
    render(<App />);

    // 1. Wait for repos and initial preview to load
    await waitFor(() => {
      expect(screen.getByTestId("preview-branch-badge")).toBeInTheDocument();
    });
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/feature-checkout");

    // 2. Open branch dropdown
    fireEvent.click(screen.getByTestId("preview-branch-badge"));
    expect(await screen.findByTestId("preview-branch-dropdown")).toBeInTheDocument();

    // 3. Select 'main' branch
    const mainOption = screen.getByTestId("preview-branch-option-main");
    fireEvent.click(mainOption);

    // 4. Verify updatePreviewBranch called
    await waitFor(() => {
      expect(api.updatePreviewBranch).toHaveBeenCalledWith("my-app", "main");
    });

    // 5. Verify branch badge reflects main branch
    await waitFor(() => {
      expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("main");
    });
  });


});
