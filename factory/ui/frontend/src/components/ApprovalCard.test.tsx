import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ApprovalCard } from "./ApprovalCard";
import { GrillTurnResult } from "../types";

const mockTurn: GrillTurnResult = {
  type: "ready_for_approval",
  round: 2,
  questions: [],
  summary: "Finalized implementation plan for dark mode toggle.",
  plan: "### Implementation Plan\n1. Add ThemeProvider\n2. Add ThemeToggle component",
  draft_adr: {
    title: "0002: Dark Mode Toggle",
    filename: "docs/adr/0002-dark-mode-toggle.md",
    content: "# 0002: Dark Mode Toggle\n\n**Status**: Accepted\n\nAdopt client-side theme switcher.",
  },
};

describe("ApprovalCard", () => {
  it("renders finalized plan summary and draft ADR details", () => {
    const handleApprove = vi.fn();
    render(<ApprovalCard turn={mockTurn} onApprove={handleApprove} />);

    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText("Plan Ready for Approval")).toBeInTheDocument();
    expect(screen.getByTestId("approval-badge")).toHaveTextContent(/Ready for Approval/i);
    expect(screen.getByTestId("plan-summary")).toHaveTextContent("Finalized implementation plan for dark mode toggle.");
    expect(screen.getByTestId("plan-details")).toHaveTextContent(/### Implementation Plan/i);
    expect(screen.getByText("docs/adr/0002-dark-mode-toggle.md")).toBeInTheDocument();
    expect(screen.getByText(/0002: Dark Mode Toggle/)).toBeInTheDocument();
  });

  it("toggles draft ADR markdown preview on click", () => {
    const handleApprove = vi.fn();
    render(<ApprovalCard turn={mockTurn} onApprove={handleApprove} />);

    // Initially collapsed
    expect(screen.queryByTestId("adr-content")).not.toBeInTheDocument();

    // Click toggle to expand
    fireEvent.click(screen.getByTestId("toggle-adr-content"));
    expect(screen.getByTestId("adr-content")).toBeInTheDocument();
    expect(screen.getByTestId("adr-content")).toHaveTextContent("Adopt client-side theme switcher.");

    // Click toggle to collapse
    fireEvent.click(screen.getByTestId("toggle-adr-content"));
    expect(screen.queryByTestId("adr-content")).not.toBeInTheDocument();
  });

  it("triggers onApprove callback with turn when 'Approve Plan & Build' is clicked", () => {
    const handleApprove = vi.fn();
    render(<ApprovalCard turn={mockTurn} onApprove={handleApprove} />);

    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    expect(approveBtn).toHaveTextContent("Approve Plan & Build");

    fireEvent.click(approveBtn);
    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith(mockTurn);
  });

  it("disables approve button when isApproving is true", () => {
    const handleApprove = vi.fn();
    render(<ApprovalCard turn={mockTurn} onApprove={handleApprove} isApproving={true} />);

    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    expect(approveBtn).toBeDisabled();
  });

  it("renders implementation plan cleanly without draft ADR preview block when draft_adr is null", () => {
    const handleApprove = vi.fn();
    const turnWithoutAdr: GrillTurnResult = {
      type: "ready_for_approval",
      round: 2,
      questions: [],
      summary: "Deletion scope confirmed and layout reflow requirements settled.",
      plan: "### Implementation Plan: Remove Social Links\n1. Prune social links from Footer.tsx\n2. Reflow footer spacing",
      draft_adr: null,
    };

    render(<ApprovalCard turn={turnWithoutAdr} onApprove={handleApprove} />);

    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByTestId("plan-summary")).toHaveTextContent("Deletion scope confirmed and layout reflow requirements settled.");
    expect(screen.getByTestId("plan-details")).toHaveTextContent(/Remove Social Links/i);
    expect(screen.queryByTestId("draft-adr-preview")).not.toBeInTheDocument();
    expect(screen.queryByTestId("toggle-adr-content")).not.toBeInTheDocument();

    const approveBtn = screen.getByTestId("approve-plan-build-btn");
    fireEvent.click(approveBtn);
    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith(turnWithoutAdr);
  });
});
