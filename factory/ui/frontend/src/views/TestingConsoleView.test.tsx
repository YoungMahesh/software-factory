import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TestingConsoleView } from "./TestingConsoleView";

const mockRepos = [
  { name: "test1", is_tanstack_compatible: false },
  { name: "cool-app", is_tanstack_compatible: true },
];

describe("TestingConsoleView", () => {
  it("renders repository select, launch controls, and terminal log viewer", () => {
    render(
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
  });

  it("handles launch action with selected parameters", async () => {
    const handleLaunch = vi.fn();
    render(
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
    fireEvent.click(launchBtn);

    expect(handleLaunch).toHaveBeenCalledWith(
      expect.objectContaining({
        repo: "cool-app",
      })
    );
  });
});
