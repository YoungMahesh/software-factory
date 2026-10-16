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

  describe("Turn Rollback Integration", () => {
    it("renders dedicated TurnRollbackCard when turn_data.type === 'turn_rollback'", () => {
      const rollbackMessage = {
        id: "msg-rollback-1",
        role: "assistant" as const,
        timestamp: Date.now(),
        turn_data: {
          type: "turn_rollback",
          original_commit_sha: "abc1234567890",
          revert_commit_sha: "def0987654321",
          issue_number: 7,
          branch: "factory/feature-7",
        },
        text: "↩️ Rolled back turn for Issue #7 (commit abc1234 ➔ def0987). Live Preview restored to previous version.",
      };

      renderStudio({
        selectedRepo: "cool-app",
        messages: [rollbackMessage],
      });

      const card = screen.getByTestId("turn-rollback-card");
      expect(card).toBeInTheDocument();
      expect(card).toHaveTextContent(/Turn Rolled Back/i);
      expect(card).toHaveTextContent(/abc1234/i);
      expect(card).toHaveTextContent(/def0987/i);
      expect(card).toHaveTextContent(/factory\/feature-7/i);
    });

    it("renders visual Reverted badge on superseded assistant cards and disables approval buttons when turn_data.reverted === true", () => {
      const revertedMessage = {
        id: "msg-reverted-1",
        role: "assistant" as const,
        timestamp: Date.now(),
        turn_data: {
          reverted: true,
          reverted_at: Date.now(),
          revert_commit: "def0987654321",
        },
        grillTurn: {
          type: "ready_for_approval" as const,
          round: 1,
          questions: [],
          plan: "Add dark mode support",
        },
      };

      renderStudio({
        selectedRepo: "cool-app",
        messages: [revertedMessage],
      });

      expect(screen.getByTestId("turn-reverted-badge")).toBeInTheDocument();
      expect(screen.getByTestId("turn-reverted-badge")).toHaveTextContent(/Reverted/i);

      const approveBtn = screen.getByTestId("approve-plan-build-btn");
      expect(approveBtn).toBeDisabled();
      expect(approveBtn).toHaveTextContent(/Plan Reverted/i);
    });

    it("opens TurnRollbackModal when clicking Undo Last Turn in LivePreview, confirms, calls rollbackTurn, and displays success toast", async () => {
      const rollbackSpy = vi.spyOn(api, "rollbackTurn").mockResolvedValue({
        success: true,
        branch: "factory/feature-1",
        original_commit: "abc1234",
        revert_commit: "def5678",
        issue_number: 5,
        message: "Rolled back turn for Issue #5 (commit abc1234 ➔ def5678).",
      });

      const { user } = renderStudio({
        selectedRepo: "cool-app",
        previewState: {
          status: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://preview.modal.host",
          logs: [],
          error_message: null,
        },
        messages: [
          {
            id: "msg-code-1",
            role: "assistant" as const,
            timestamp: Date.now(),
            text: "Turn 1 completed",
            turn_data: {
              commit_sha: "abc1234",
              branch: "factory/feature-1",
              issue_number: 5,
            },
          },
        ],
      });

      const undoBtn = screen.getByTestId("preview-rollback-btn");
      await user.click(undoBtn);

      const modal = screen.getByTestId("turn-rollback-dialog");
      expect(modal).toBeInTheDocument();
      expect(modal).toHaveTextContent(/Roll Back Turn/i);

      const confirmBtn = screen.getByTestId("confirm-rollback-btn");
      await user.click(confirmBtn);

      expect(rollbackSpy).toHaveBeenCalledWith({
        repo: "cool-app",
        branch: "factory/feature-1",
        message_id: "msg-code-1",
      });

      const toast = await screen.findByTestId("studio-toast");
      expect(toast).toBeInTheDocument();
      expect(toast).toHaveTextContent(/Rolled back turn for Issue #5/i);

      rollbackSpy.mockRestore();
    });

    it("handles rollback failure and displays error toast", async () => {
      const rollbackSpy = vi.spyOn(api, "rollbackTurn").mockRejectedValue(
        new Error("Turn rollback failed: merge conflict during git revert")
      );

      const { user } = renderStudio({
        selectedRepo: "cool-app",
        previewState: {
          status: "SERVING",
          branch: "factory/feature-1",
          preview_url: "https://preview.modal.host",
          logs: [],
          error_message: null,
        },
        messages: [
          {
            id: "msg-code-1",
            role: "assistant" as const,
            timestamp: Date.now(),
            text: "Turn 1 completed",
            turn_data: {
              commit_sha: "abc1234",
              branch: "factory/feature-1",
            },
          },
        ],
      });

      const undoBtn = screen.getByTestId("preview-rollback-btn");
      await user.click(undoBtn);

      const confirmBtn = screen.getByTestId("confirm-rollback-btn");
      await user.click(confirmBtn);

      const toast = await screen.findByTestId("studio-toast");
      expect(toast).toBeInTheDocument();
      expect(toast).toHaveTextContent(/Turn rollback failed: merge conflict during git revert/i);

      rollbackSpy.mockRestore();
    });

    it("opens TurnRollbackModal when clicking inline Undo Turn on DeliveryGateCard and executes rollback", async () => {
      const rollbackSpy = vi.spyOn(api, "rollbackTurn").mockResolvedValue({
        success: true,
        branch: "factory/settings",
        original_commit: "commit123",
        revert_commit: "commit456",
        issue_number: 10,
        message: "Rolled back turn for Issue #10.",
      });

      const deliveryGateMessage = {
        id: "msg-delivery-gate-1",
        role: "assistant" as const,
        timestamp: Date.now(),
        deliveryGate: {
          phase: "finalized",
          pull_number: 105,
          sha: "commit123",
          branch: "factory/settings",
          pull_request: {
            number: 105,
            title: "Feature: Settings Page",
            state: "open",
            status: "ready_for_review",
            draft: false,
            merged: false,
            mergeable: true,
            head_branch: "factory/settings",
            base_branch: "main",
            html_url: "https://github.com/software-factory-09-test/cool-app/pull/105",
          },
          resolved_issues: ["#10"],
          test_verdict: "passed",
        },
      };

      const { user } = renderStudio({
        selectedRepo: "cool-app",
        previewState: {
          status: "SERVING",
          branch: "factory/settings",
          preview_url: "https://preview.modal.host",
          logs: [],
          error_message: null,
        },
        messages: [deliveryGateMessage],
      });

      const undoBtn = screen.getByTestId("delivery-gate-rollback-btn");
      expect(undoBtn).toBeInTheDocument();
      await user.click(undoBtn);

      const modal = screen.getByTestId("turn-rollback-dialog");
      expect(modal).toBeInTheDocument();
      expect(modal).toHaveTextContent(/Issue #10/i);
      expect(modal).toHaveTextContent(/Feature: Settings Page/i);

      const confirmBtn = screen.getByTestId("confirm-rollback-btn");
      await user.click(confirmBtn);

      expect(rollbackSpy).toHaveBeenCalledWith({
        repo: "cool-app",
        branch: "factory/settings",
        message_id: "msg-delivery-gate-1",
      });

      const toast = await screen.findByTestId("studio-toast");
      expect(toast).toHaveTextContent(/Rolled back turn for Issue #10/i);

      rollbackSpy.mockRestore();
    });
  });
