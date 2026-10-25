import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import App, { STORAGE_KEY_SELECTED_REPO } from "./App";
import * as api from "./api";

vi.mock("./api", () => ({
  fetchRepos: vi.fn(),
  createRepo: vi.fn(),
  fetchMilestones: vi.fn(),
  fetchIssues: vi.fn(),
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

describe("App Root - URL Routing & State Hydration", () => {
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

  it("hydrates selectedRepo from URL query parameter on page load", async () => {
    window.history.replaceState(null, "", "/?repo=counter-2");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("counter-2");
    });
    expect(localStorage.getItem(STORAGE_KEY_SELECTED_REPO)).toBe("counter-2");
  });

  it("hydrates selectedRepo from localStorage fallback when URL has no query parameter", async () => {
    window.history.replaceState(null, "", "/");
    localStorage.setItem(STORAGE_KEY_SELECTED_REPO, "counter-2");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("counter-2");
    });
    expect(window.location.search).toBe("?repo=counter-2");
  });

  it("falls back to repos[0] when URL query parameter points to an unknown repository", async () => {
    window.history.replaceState(null, "", "/?repo=deleted-app");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("calculator-app");
    });
    expect(window.location.search).toBe("?repo=calculator-app");
    expect(localStorage.getItem(STORAGE_KEY_SELECTED_REPO)).toBe("calculator-app");
  });

  it("updates URL and localStorage and pushes history when user selects a different repository", async () => {
    window.history.replaceState(null, "", "/");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("calculator-app");
    });

    fireEvent.change(repoSelect, { target: { value: "counter-2" } });

    await waitFor(() => {
      expect(repoSelect).toHaveValue("counter-2");
    });
    expect(window.location.search).toBe("?repo=counter-2");
    expect(localStorage.getItem(STORAGE_KEY_SELECTED_REPO)).toBe("counter-2");
  });

  it("synchronizes selectedRepo and activeTab on browser popstate navigation", async () => {
    window.history.replaceState(null, "", "/?repo=calculator-app");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("calculator-app");
    });

    // Simulate browser Back navigation to /?repo=counter-2
    window.history.pushState(null, "", "/?repo=counter-2");
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    await waitFor(() => {
      expect(repoSelect).toHaveValue("counter-2");
    });
    expect(localStorage.getItem(STORAGE_KEY_SELECTED_REPO)).toBe("counter-2");
  });

  it("redirects to newly created repository instead of falling back to top alphabetical repo (calculator-app)", async () => {
    window.history.replaceState(null, "", "/?repo=counter-2");
    vi.mocked(api.fetchRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [
        { name: "calculator-app", is_tanstack_compatible: true },
        { name: "counter-2", is_tanstack_compatible: true },
      ],
    });
    vi.mocked(api.createRepo).mockResolvedValue({
      name: "zen-notes",
      is_tanstack_compatible: true,
      private: true,
    });
    vi.mocked(api.fetchPreview).mockResolvedValue({
      repo: "zen-notes",
      status: "STOPPED",
      stage: "IDLE",
      branch: "main",
      preview_url: null,
      sandbox_id: "sb-2",
      created_at: Date.now(),
      started_at: null,
      ended_at: null,
      error_message: null,
      logs: [],
      log_count: 0,
    });
    vi.mocked(api.fetchChatMessages).mockResolvedValue({
      repo: "zen-notes",
      messages: [],
    });
    vi.mocked(api.fetchRepoBranches).mockResolvedValue({
      repo: "zen-notes",
      org: "software-factory-09-test",
      branches: ["main"],
      default_branch: "main",
    });

    render(<App />);

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("counter-2");
    });

    // Open New App modal
    const newAppBtn = screen.getByRole("button", { name: /New App/i });
    fireEvent.click(newAppBtn);

    // Modal is rendered
    expect(screen.getByText("Create New App")).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText(/e\.g\. inventory-tracker/i);
    fireEvent.change(nameInput, { target: { value: "zen-notes" } });

    const submitBtn = screen.getByRole("button", { name: /^Create App$/i });
    fireEvent.click(submitBtn);

    // Should redirect to zen-notes, NOT calculator-app
    await waitFor(() => {
      expect(repoSelect).toHaveValue("zen-notes");
    });

    expect(window.location.search).toBe("?repo=zen-notes");
    expect(localStorage.getItem(STORAGE_KEY_SELECTED_REPO)).toBe("zen-notes");
  });

  it("does not prematurely fall back to repos[0].name while repos query is fetching", async () => {
    window.history.replaceState(null, "", "/?repo=in-flight-app");

    let resolveRepos!: (val: any) => void;
    const pendingPromise = new Promise((resolve) => {
      resolveRepos = resolve;
    });
    vi.mocked(api.fetchRepos).mockReturnValue(pendingPromise as any);

    render(<App />);

    // Since query is loading, selectedRepo should remain in-flight-app in URL
    expect(window.location.search).toBe("?repo=in-flight-app");

    // Now resolve with repos that include in-flight-app
    await act(async () => {
      resolveRepos({
        org: "software-factory-09-test",
        repos: [
          { name: "calculator-app", is_tanstack_compatible: true },
          { name: "in-flight-app", is_tanstack_compatible: true },
        ],
      });
    });

    const repoSelect = await screen.findByRole("combobox");
    await waitFor(() => {
      expect(repoSelect).toHaveValue("in-flight-app");
    });
    expect(window.location.search).toBe("?repo=in-flight-app");
  });
});
