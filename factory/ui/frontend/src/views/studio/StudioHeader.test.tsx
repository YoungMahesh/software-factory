import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StudioHeader, StudioHeaderProps } from "./StudioHeader";

describe("StudioHeader", () => {
  const defaultProps: StudioHeaderProps = {
    repos: [{ name: "my-app", is_tanstack_compatible: true }],
    selectedRepo: "my-app",
    onSelectRepo: vi.fn(),
    onOpenNewAppModal: vi.fn(),
    openIssuesCount: 3,
    onOpenIssues: vi.fn(),
    renderPRControlBadge: () => null,
    isPRPopoverOpen: false,
    onTogglePRPopover: vi.fn(),
    isConfirmingMerge: false,
    onSetIsConfirmingMerge: vi.fn(),
    onPopoverMerge: vi.fn(),
    isMerging: false,
    popoverMergeError: null,
    prIsDraft: false,
    prHasConflict: false,
    prIsMerged: false,
    prIsClosed: false,
    isExecutingTurn: false,
    previewState: null,
    isServing: false,
    isProvisioning: false,
    isLaunchingPreview: false,
  };

  it("renders repository dropdown, New App button, Issues button, and Preview App controls cleanly", () => {
    render(<StudioHeader {...defaultProps} />);

    expect(screen.getByText("Current App:")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New App/i })).toBeInTheDocument();
    expect(screen.getByTestId("studio-issues-btn")).toBeInTheDocument();
    expect(screen.getByTestId("studio-issues-badge")).toHaveTextContent("3");
    expect(screen.getByTestId("preview-app-btn")).toBeInTheDocument();
  });

  it("does not render floating job status badge, duplicate activity button, inspect logs button, or cancel button", () => {
    const { container } = render(<StudioHeader {...defaultProps} />);

    expect(container.querySelector("#studio-floating-status-badge")).toBeNull();
    expect(container.querySelector("#btn-studio-activity")).toBeNull();
    expect(container.querySelector("#btn-inspect-logs")).toBeNull();
    expect(container.querySelector("#btn-studio-cancel")).toBeNull();
    expect(screen.queryByTitle(/Open Agent Activity Drawer/i)).toBeNull();
    expect(screen.queryByTitle(/Inspect terminal logs in Console/i)).toBeNull();
  });
});
