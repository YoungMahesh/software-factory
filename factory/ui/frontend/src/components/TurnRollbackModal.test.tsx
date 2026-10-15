import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import { TurnRollbackModal } from "./TurnRollbackModal";

describe("TurnRollbackModal", () => {
  it("renders nothing when isOpen is false", () => {
    renderWithProviders(
      <TurnRollbackModal
        isOpen={false}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        repo="my-app"
        branch="factory/feature-1"
      />
    );
    expect(screen.queryByTestId("turn-rollback-dialog")).not.toBeInTheDocument();
  });

  it("renders accessible dialog with issue, commit, and branch details", () => {
    renderWithProviders(
      <TurnRollbackModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        repo="my-app"
        branch="factory/feature-1"
        commitSha="abc1234567"
        issueNumber={42}
        issueTitle="Add Dark Mode Toggle"
      />
    );

    expect(screen.getByTestId("turn-rollback-dialog")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Roll Back Turn/i)).toBeInTheDocument();
    expect(screen.getByText(/Issue #42/i)).toBeInTheDocument();
    expect(screen.getByText(/Add Dark Mode Toggle/i)).toBeInTheDocument();
    expect(screen.getByText("abc1234567")).toBeInTheDocument();
    expect(screen.getByText("factory/feature-1")).toBeInTheDocument();
  });

  it("renders issue title even when issue number is absent", () => {
    renderWithProviders(
      <TurnRollbackModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        repo="my-app"
        branch="factory/feature-1"
        commitSha="abc1234567"
        issueTitle="Visual Layout Fix"
      />
    );

    expect(screen.getByTestId("turn-rollback-dialog")).toBeInTheDocument();
    expect(screen.getByText(/Visual Layout Fix/i)).toBeInTheDocument();
  });

  it("triggers onConfirm when Confirm Rollback button is clicked", async () => {
    const user = userEvent.setup();
    const handleConfirm = vi.fn();
    renderWithProviders(
      <TurnRollbackModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={handleConfirm}
        repo="my-app"
        branch="factory/feature-1"
      />
    );

    const confirmBtn = screen.getByTestId("confirm-rollback-btn");
    await user.click(confirmBtn);
    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });

  it("triggers onClose when Cancel button is clicked", async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    renderWithProviders(
      <TurnRollbackModal
        isOpen={true}
        onClose={handleClose}
        onConfirm={vi.fn()}
        repo="my-app"
        branch="factory/feature-1"
      />
    );

    const cancelBtn = screen.getByTestId("cancel-rollback-btn");
    await user.click(cancelBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("disables buttons and shows spinner when isRollingBack is true", () => {
    renderWithProviders(
      <TurnRollbackModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        repo="my-app"
        branch="factory/feature-1"
        isRollingBack={true}
      />
    );

    expect(screen.getByTestId("confirm-rollback-btn")).toBeDisabled();
    expect(screen.getByTestId("cancel-rollback-btn")).toBeDisabled();
  });
});

