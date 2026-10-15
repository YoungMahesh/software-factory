import { screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TestingConsoleView } from "./TestingConsoleView";
import { renderWithProviders, userEvent } from "../test/test-utils";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchMilestones: vi.fn(),
  fetchIssues: vi.fn(),
}));

const mockRepos = [
  { name: "test1", is_tanstack_compatible: false },
  { name: "cool-app", is_tanstack_compatible: true },
];

describe("TestingConsoleView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchMilestones).mockResolvedValue({ repo: "cool-app", milestones: [] });
    vi.mocked(api.fetchIssues).mockResolvedValue({ repo: "cool-app", issues: [] });
  });

  it("renders repository select, launch controls, and terminal log viewer", async () => {
    renderWithProviders(
      <TestingConsoleView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onRefreshRepos={vi.fn()}
        activeJob={null}
        jobs={[]}
        onLaunch={vi.fn()}
        onCancel={vi.fn()}
        onSelectJob={vi.fn()}
      />
    );

    expect(screen.getByText("Launch Parameters")).toBeInTheDocument();
    expect(screen.getByText("cool-app")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Launch Assembly Line/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(api.fetchMilestones).toHaveBeenCalledWith("cool-app");
    });
  });

  it("handles launch action with selected parameters", async () => {
    const user = userEvent.setup();
    const handleLaunch = vi.fn();

    renderWithProviders(
      <TestingConsoleView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onRefreshRepos={vi.fn()}
        activeJob={null}
        jobs={[]}
        onLaunch={handleLaunch}
        onCancel={vi.fn()}
        onSelectJob={vi.fn()}
      />
    );

    const launchBtn = screen.getByRole("button", { name: /Launch Assembly Line/i });
    await user.click(launchBtn);

    expect(handleLaunch).toHaveBeenCalledWith(
      expect.objectContaining({
        repo: "cool-app",
      })
    );

    await waitFor(() => {
      expect(api.fetchMilestones).toHaveBeenCalledWith("cool-app");
    });
  });

  it("renders private repository badge when selected repo is private", async () => {
    const reposWithPrivate = [
      { name: "private-repo", is_tanstack_compatible: true, private: true },
      { name: "public-repo", is_tanstack_compatible: false, private: false },
    ];
    renderWithProviders(
      <TestingConsoleView
        repos={reposWithPrivate}
        selectedRepo="private-repo"
        onSelectRepo={vi.fn()}
        onRefreshRepos={vi.fn()}
        activeJob={null}
        jobs={[]}
        onLaunch={vi.fn()}
        onCancel={vi.fn()}
        onSelectJob={vi.fn()}
      />
    );

    expect(screen.getByTestId("console-repo-private-badge")).toBeInTheDocument();
    expect(screen.getByTestId("console-repo-private-badge")).toHaveTextContent(/Private/i);
    expect(screen.getByRole("option", { name: /private-repo ✦ \(TanStack\) 🔒/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(api.fetchMilestones).toHaveBeenCalledWith("private-repo");
    });
  });
});
