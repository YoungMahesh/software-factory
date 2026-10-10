import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PreviewProgressStepper } from "./PreviewProgressStepper";

describe("PreviewProgressStepper", () => {
  it("renders all 3 preview startup stages", () => {
    render(<PreviewProgressStepper currentStage="PROVISIONING" status="PROVISIONING" />);

    expect(screen.getByText("Provisioning sandbox")).toBeInTheDocument();
    expect(screen.getByText("Installing dependencies")).toBeInTheDocument();
    expect(screen.getByText("Starting dev server")).toBeInTheDocument();
  });

  it("marks completed and active stages correctly for INSTALLING_DEPS", () => {
    const { container } = render(
      <PreviewProgressStepper currentStage="INSTALLING_DEPS" status="PROVISIONING" />
    );

    // Step 1: Provisioning should be completed
    const step1 = screen.getByTestId("preview-step-provisioning");
    expect(step1).toHaveAttribute("data-state", "completed");

    // Step 2: Installing dependencies should be active
    const step2 = screen.getByTestId("preview-step-installing_deps");
    expect(step2).toHaveAttribute("data-state", "active");

    // Step 3: Starting dev server should be pending
    const step3 = screen.getByTestId("preview-step-starting_dev");
    expect(step3).toHaveAttribute("data-state", "pending");
  });

  it("marks all stages completed when SERVING", () => {
    render(<PreviewProgressStepper currentStage="SERVING" status="SERVING" />);

    expect(screen.getByTestId("preview-step-provisioning")).toHaveAttribute("data-state", "completed");
    expect(screen.getByTestId("preview-step-installing_deps")).toHaveAttribute("data-state", "completed");
    expect(screen.getByTestId("preview-step-starting_dev")).toHaveAttribute("data-state", "completed");
  });

  it("marks failed step with error state when status is FAILED", () => {
    render(
      <PreviewProgressStepper
        currentStage="INSTALLING_DEPS"
        status="FAILED"
        errorMessage="Command 'pnpm install' exited with code 1"
      />
    );

    const step2 = screen.getByTestId("preview-step-installing_deps");
    expect(step2).toHaveAttribute("data-state", "failed");
    expect(screen.getByText("Command 'pnpm install' exited with code 1")).toBeInTheDocument();
  });
});
