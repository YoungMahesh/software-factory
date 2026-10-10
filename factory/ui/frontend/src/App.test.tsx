import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
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
  listJobs: vi.fn(),
  getJob: vi.fn(),
  cancelJob: vi.fn(),
}));

describe("App Root Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchStudioRepos).mockResolvedValue({
      org: "software-factory-09-test",
      repos: [{ name: "my-app", is_tanstack_compatible: true }],
    });
    vi.mocked(api.listJobs).mockResolvedValue({ jobs: [] });
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
    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();

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
});
