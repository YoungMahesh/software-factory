import { screen, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { LivePreview } from "./LivePreview";
import { renderWithProviders, userEvent } from "../test/test-utils";

describe("LivePreview - Controls", () => {
  describe("Live Preview Branch Selector", () => {
    it("renders interactive branch dropdown trigger with GitBranch icon, branch label, and ChevronDown", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1", "factory/feature-2"]}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("factory/feature-1");
      expect(screen.getByTestId("preview-branch-icon")).toBeInTheDocument();
      expect(screen.getByTestId("preview-branch-chevron")).toBeInTheDocument();

      // Click to open dropdown
      await user.click(badge);

      const dropdown = screen.getByTestId("preview-branch-dropdown");
      expect(dropdown).toBeInTheDocument();
      expect(screen.getByTestId("preview-branch-option-main")).toHaveTextContent("main");
      expect(screen.getByTestId("preview-branch-option-factory/feature-1")).toHaveTextContent("factory/feature-1");
      expect(screen.getByTestId("preview-branch-option-factory/feature-2")).toHaveTextContent("factory/feature-2");

      // Verify checkmark indicator on active branch
      const activeOption = screen.getByTestId("preview-branch-option-factory/feature-1");
      expect(within(activeOption).getByTestId("preview-branch-check")).toBeInTheDocument();
    });

    it("selects a branch from dropdown, invokes onSelectBranch, and closes dropdown", async () => {
      const user = userEvent.setup();
      const handleSelectBranch = vi.fn();
      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1", "factory/feature-2"]}
          onSelectBranch={handleSelectBranch}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      await user.click(badge);

      const mainOption = screen.getByTestId("preview-branch-option-main");
      await user.click(mainOption);

      expect(handleSelectBranch).toHaveBeenCalledWith("main");
      expect(screen.queryByTestId("preview-branch-dropdown")).toBeNull();
    });

    it("displays loading spinner inside badge and disables interaction during branch transition", () => {
      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1"]}
          isSwitchingBranch={true}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      expect(badge).toBeDisabled();
      expect(screen.getByTestId("preview-branch-spinner")).toBeInTheDocument();
      expect(screen.queryByTestId("preview-branch-chevron")).toBeNull();
    });

    it("strictly disables branch selector with lock icon and explanatory tooltip when concurrency locked", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1"]}
          isConcurrencyLocked={true}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      expect(badge).toBeDisabled();
      expect(screen.getByTestId("preview-branch-lock-icon")).toBeInTheDocument();
      expect(badge).toHaveAttribute(
        "title",
        expect.stringMatching(/branch switching is disabled|locked/i)
      );

      // Verify clicking disabled badge does not open dropdown
      await user.click(badge);
      expect(screen.queryByTestId("preview-branch-dropdown")).toBeNull();
    });

    it("supports keyboard navigation (ArrowDown, Enter) and click-away closing", async () => {
      const user = userEvent.setup();
      const handleSelectBranch = vi.fn();
      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1", "factory/feature-2"]}
          onSelectBranch={handleSelectBranch}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      badge.focus();
      await user.keyboard("{Enter}");

      expect(screen.getByTestId("preview-branch-dropdown")).toBeInTheDocument();

      // Press Escape to close
      await user.keyboard("{Escape}");
      expect(screen.queryByTestId("preview-branch-dropdown")).toBeNull();

      // Open again and click outside to close
      await user.click(badge);
      expect(screen.getByTestId("preview-branch-dropdown")).toBeInTheDocument();

      await user.click(document.body);
      expect(screen.queryByTestId("preview-branch-dropdown")).toBeNull();
    });

    it("triggers automatic preview iframe refresh upon branch switch completion", async () => {
      const user = userEvent.setup();
      const handleRefresh = vi.fn();
      const handleSelectBranch = vi.fn().mockImplementation(() => {
        // simulate async completion
      });

      renderWithProviders(
        <LivePreview
          previewUrl="https://sandbox-3000.modal.host"
          status="SERVING"
          branch="factory/feature-1"
          branches={["main", "factory/feature-1"]}
          onSelectBranch={handleSelectBranch}
          onRefresh={handleRefresh}
        />
      );

      const badge = screen.getByTestId("preview-branch-badge");
      await user.click(badge);

      const mainOption = screen.getByTestId("preview-branch-option-main");
      await user.click(mainOption);

      expect(handleSelectBranch).toHaveBeenCalledWith("main");
      expect(handleRefresh).toHaveBeenCalledTimes(1);
    });
  });

  describe("Trunk Synchronization in LivePreview", () => {
    it("renders dedicated sync button adjacent to branch badge with tooltip", () => {
      const handleSync = vi.fn();
      renderWithProviders(
        <LivePreview
          status="SERVING"
          branch="main"
          onSync={handleSync}
        />
      );

      const syncBtn = screen.getByTestId("sync-preview-btn");
      expect(syncBtn).toBeInTheDocument();
      expect(syncBtn).toHaveAttribute("title", "Pull latest from remote");
      expect(screen.getByTestId("sync-icon")).toBeInTheDocument();
    });

    it("calls onSync when sync button is clicked", async () => {
      const user = userEvent.setup();
      const handleSync = vi.fn();
      renderWithProviders(
        <LivePreview
          status="SERVING"
          branch="main"
          onSync={handleSync}
        />
      );

      const syncBtn = screen.getByTestId("sync-preview-btn");
      await user.click(syncBtn);
      expect(handleSync).toHaveBeenCalledTimes(1);
    });

    it("renders animated loading spinner and disables clicks when isSyncing is true", async () => {
      const user = userEvent.setup();
      const handleSync = vi.fn();
      renderWithProviders(
        <LivePreview
          status="SERVING"
          branch="main"
          isSyncing={true}
          onSync={handleSync}
        />
      );

      const syncBtn = screen.getByTestId("sync-preview-btn");
      expect(syncBtn).toBeDisabled();
      expect(screen.getByTestId("sync-loading-spinner")).toBeInTheDocument();

      await user.click(syncBtn);
      expect(handleSync).not.toHaveBeenCalled();
    });

    it("renders lock icon and disables clicks with concurrency lock tooltip when isJobActive is true", async () => {
      const user = userEvent.setup();
      const handleSync = vi.fn();
      renderWithProviders(
        <LivePreview
          status="SERVING"
          branch="main"
          isJobActive={true}
          onSync={handleSync}
        />
      );

      const syncBtn = screen.getByTestId("sync-preview-btn");
      expect(syncBtn).toBeDisabled();
      expect(screen.getByTestId("sync-lock-icon")).toBeInTheDocument();
      expect(syncBtn.getAttribute("title")).toMatch(/job/i);

      await user.click(syncBtn);
      expect(handleSync).not.toHaveBeenCalled();
    });
  });

  describe("Turn Rollback Controls", () => {
    it("does not render duplicate rollback button in toolbar (canonicalized to PromptComposer)", () => {
      renderWithProviders(
        <LivePreview
          status="SERVING"
          branch="factory/feature-1"
        />
      );

      expect(screen.queryByTestId("preview-rollback-btn")).not.toBeInTheDocument();
    });
  });

});
