import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AttemptDividerCard, ReviewerRejectionCard } from "./SelfCorrectionCards";

describe("SelfCorrectionCards", () => {
  it("renders attempt divider with attempt numbers, reason and summary", () => {
    render(
      <AttemptDividerCard
        attempt={2}
        maxAttempts={3}
        reason="reviewer rejection"
        summary="Addressing reviewer feedback"
      />
    );

    expect(screen.getByText(/Self-Correction Loop: Attempt 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByText(/reviewer rejection/i)).toBeInTheDocument();
    expect(screen.getByText(/Addressing reviewer feedback/i)).toBeInTheDocument();
  });

  it("renders reviewer rejection card with summary and remediation", () => {
    render(
      <ReviewerRejectionCard
        summary="Missing test coverage on error paths"
        remediation="Add test cases in tests/test_api.py"
      />
    );

    expect(screen.getByText(/Reviewer Rejection/i)).toBeInTheDocument();
    expect(screen.getByText("Missing test coverage on error paths")).toBeInTheDocument();
    expect(screen.getByText("Add test cases in tests/test_api.py")).toBeInTheDocument();
  });
});
