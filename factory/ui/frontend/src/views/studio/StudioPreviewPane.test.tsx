import React from "react";
import { screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test/test-utils";
import { StudioPreviewPane, StudioPreviewPaneProps } from "./StudioPreviewPane";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    fetchRepoTree: vi.fn().mockResolvedValue({
      repo: "my-app",
      branch: "main",
      source: "github",
      tree: [{ path: "src/App.tsx", type: "blob", size: 100 }],
    }),
    fetchRepoFile: vi.fn().mockResolvedValue({
      repo: "my-app",
      branch: "main",
      path: "src/App.tsx",
      size: 100,
      is_binary: false,
      is_truncated: false,
      content: "console.log('hi');",
      source: "github",
    }),
    fetchRepoDiff: vi.fn().mockResolvedValue({
      repo: "my-app",
      branch: "main",
      base: "main",
      scope: "working_tree",
      source: "sandbox",
      summary: { total_files: 0, additions: 0, deletions: 0 },
      files: [],
      clean: true,
    }),
  };
});

describe("StudioPreviewPane", () => {
  const defaultProps: StudioPreviewPaneProps = {
    repo: "my-app",
    previewState: {
      status: "IDLE",
      stage: "IDLE",
      branch: "main",
      logs: [],
    } as any,
    branches: ["main", "factory/feature"],
    onSelectBranch: vi.fn(),
    isSwitchingBranch: false,
    activeJob: null,
    refreshKey: 0,
    branchRefreshKey: 0,
    isLaunchingPreview: false,
    isSyncing: false,
    onSync: vi.fn(),
    isExecutingTurn: false,
    latestRollbackInfo: { target: null, isMerged: false },
    onOpenRollback: vi.fn(),
    isRollingBack: false,
    isLatestTurnMerged: false,
  };

  it("renders the canvas view mode switcher with Live Preview, Files & Code, and Git Diff", () => {
    renderWithProviders(<StudioPreviewPane {...defaultProps} />);

    expect(screen.getByTestId("canvas-view-mode-switcher")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-view-mode-preview")).toHaveTextContent("Live Preview");
    expect(screen.getByTestId("canvas-view-mode-files")).toHaveTextContent("Files & Code");
    expect(screen.getByTestId("canvas-view-mode-diff")).toHaveTextContent("Git Diff");
  });

  it("switches view mode between Live Preview, Files & Code, and Git Diff", async () => {
    const { user } = renderWithProviders(<StudioPreviewPane {...defaultProps} />);

    // Initially in Live Preview mode
    expect(screen.getByTestId("canvas-view-mode-preview")).toHaveClass("bg-primary");

    // Switch to Files & Code
    await user.click(screen.getByTestId("canvas-view-mode-files"));

    await waitFor(() => {
      expect(screen.getByTestId("in-studio-code-viewer")).toBeInTheDocument();
      expect(screen.getByTestId("canvas-view-mode-files")).toHaveClass("bg-primary");
    });

    // Switch to Git Diff
    await user.click(screen.getByTestId("canvas-view-mode-diff"));

    await waitFor(() => {
      expect(screen.getByTestId("pre-merge-diff-viewer")).toBeInTheDocument();
      expect(screen.getByTestId("canvas-view-mode-diff")).toHaveClass("bg-primary");
    });

    // Switch back to Live Preview
    await user.click(screen.getByTestId("canvas-view-mode-preview"));

    await waitFor(() => {
      expect(screen.getByTestId("canvas-view-mode-preview")).toHaveClass("bg-primary");
    });
  });
});
