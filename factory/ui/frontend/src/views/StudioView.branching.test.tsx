import { screen, within, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StudioView } from "./StudioView";
import { renderWithProviders } from "../test/test-utils";
import { StudioContextValue } from "../context/StudioContext";
import * as api from "../api";
import { studioQueryKeys } from "../hooks/useStudioQueries";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchIssues: vi.fn().mockResolvedValue({ repo: "cool-app", issues: [] }),
    fetchPullRequests: vi.fn().mockResolvedValue({ repo: "cool-app", pulls: [] }),
    mergePullRequest: vi.fn(),
    syncPreview: vi.fn(),
    rollbackTurn: vi.fn(),
  };
});

const renderStudio = (overrides: Partial<StudioContextValue> = {}) =>
  renderWithProviders(<StudioView />, { contextOverrides: overrides });

  describe("Live Preview Branch Selector in StudioView", () => {
    it("invalidates branch query cache when selected repository changes", () => {
      const { queryClient, rerenderWithContext } = renderStudio({
        selectedRepo: "cool-app",
      });
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      rerenderWithContext({
        selectedRepo: "test-app",
      });

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: studioQueryKeys.branches("test-app"),
      });
    });

    it("invalidates branch query cache when active job completes with SUCCESS", () => {
      const { queryClient, rerenderWithContext } = renderStudio({
        selectedRepo: "cool-app",
        activeJob: {
          id: "job-1",
          repo: "cool-app",
          status: "RUNNING",
          stage: "CODER",
          model: "deepseek-v4.1-flash",
          vm: false,
          dev: true,
          created_at: "2026-10-15T00:00:00Z",
          log_count: 0,
          event_count: 0,
        },
      });

      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      rerenderWithContext({
        selectedRepo: "cool-app",
        activeJob: {
          id: "job-1",
          repo: "cool-app",
          status: "SUCCESS",
          stage: "COMPLETED",
          model: "deepseek-v4.1-flash",
          vm: false,
          dev: true,
          created_at: "2026-10-15T00:00:00Z",
          log_count: 0,
          event_count: 0,
        },
      });

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: studioQueryKeys.branches("cool-app"),
      });
    });

    it("invalidates branch query cache on IssueDrawer open and close", async () => {
      const { user, queryClient } = renderStudio({
        selectedRepo: "cool-app",
      });

      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      // Open issues drawer
      const issuesBtn = screen.getByTestId("studio-issues-btn");
      await user.click(issuesBtn);

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: studioQueryKeys.branches("cool-app"),
      });

      // Close issues drawer
      const closeBtn = screen.getByTestId("close-issue-drawer-btn");
      await user.click(closeBtn);

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: studioQueryKeys.branches("cool-app"),
      });
    });

    it("strictly locks branch selector in LivePreview when an Assembly Line Pipeline job is RUNNING", () => {
      renderStudio({
        selectedRepo: "cool-app",
        activeJob: {
          id: "job-lock-1",
          repo: "cool-app",
          status: "RUNNING",
          stage: "CODER",
          model: "deepseek-v4.1-flash",
          vm: false,
          dev: true,
          created_at: "2026-10-15T00:00:00Z",
          log_count: 0,
          event_count: 0,
        },
        previewState: {
          repo: "cool-app",
          status: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://sandbox-3000.modal.host",
          logs: [],
          error_message: null,
        },
        branches: ["main", "factory/feature-1"],
      });

      const badge = screen.getByTestId("preview-branch-badge");
      expect(badge).toBeDisabled();
      expect(screen.getByTestId("preview-branch-lock-icon")).toBeInTheDocument();
    });

    it("handles branch selection in StudioView and triggers onSelectBranch", async () => {
      const handleSelectBranch = vi.fn();
      const { user } = renderStudio({
        selectedRepo: "cool-app",
        previewState: {
          repo: "cool-app",
          status: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://sandbox-3000.modal.host",
          logs: [],
          error_message: null,
        },
        branches: ["main", "factory/feature-1"],
        onSelectBranch: handleSelectBranch,
      });

      const badge = screen.getByTestId("preview-branch-badge");
      await user.click(badge);

      const mainOption = screen.getByTestId("preview-branch-option-main");
      await user.click(mainOption);

      expect(handleSelectBranch).toHaveBeenCalledWith("main");
    });
  });

  describe("Trunk Synchronization in StudioView", () => {
    it("handles trunk synchronization mutation and displays success toast notification", async () => {
      const syncSpy = vi.spyOn(api, "syncPreview").mockResolvedValue({
        success: true,
        branch: "main",
        commit: "abcdef1",
        updated: true,
        message: "Synchronized with origin/main",
      });

      const { user } = renderStudio({
        selectedRepo: "test-app",
        previewState: {
          repo: "test-app",
          status: "SERVING",
          branch: "main",
          preview_url: "https://preview.modal.host",
          logs: [],
          error_message: null,
        },
      });

      const syncBtn = screen.getByTestId("sync-preview-btn");
      await user.click(syncBtn);

      expect(syncSpy).toHaveBeenCalledWith("test-app", "main");

      const toast = await screen.findByTestId("studio-toast");
      expect(toast).toBeInTheDocument();
      expect(toast).toHaveTextContent(/Preview synchronized with main \[abcdef1\]/i);

      syncSpy.mockRestore();
    });

    it("handles trunk synchronization failure and surfaces error alert toast", async () => {
      const syncSpy = vi.spyOn(api, "syncPreview").mockRejectedValue(
        new Error("Git remote ref failed: authentication error")
      );

      const { user } = renderStudio({
        selectedRepo: "test-app",
        previewState: {
          repo: "test-app",
          status: "SERVING",
          branch: "main",
          preview_url: "https://preview.modal.host",
          logs: [],
          error_message: null,
        },
      });

      const syncBtn = screen.getByTestId("sync-preview-btn");
      await user.click(syncBtn);

      const toast = await screen.findByTestId("studio-toast");
      expect(toast).toBeInTheDocument();
      expect(toast).toHaveTextContent(/Git remote ref failed: authentication error/i);

      syncSpy.mockRestore();
    });

    it("disables sync button with lock icon when active job is running", () => {
      renderStudio({
        selectedRepo: "test-app",
        activeJob: {
          id: "job-1",
          repo: "test-app",
          feature: "feature-test",
          issue: null,
          status: "RUNNING",
          stage: "CODER",
          model: "deepseek-v4.1-flash",
          vm: false,
          created_at: Date.now(),
          logs: [],
          events: [],
        },
      });

      const syncBtn = screen.getByTestId("sync-preview-btn");
      expect(syncBtn).toBeDisabled();
      expect(screen.getByTestId("sync-lock-icon")).toBeInTheDocument();
    });
  });
