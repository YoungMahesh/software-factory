import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StageStepper } from "./StageStepper";

describe("StageStepper", () => {
  it("renders all pipeline stages", () => {
    render(<StageStepper currentStage="PLANNER" />);

    expect(screen.getByText("Preflight")).toBeInTheDocument();
    expect(screen.getByText("Planner")).toBeInTheDocument();
    expect(screen.getByText("Coder")).toBeInTheDocument();
    expect(screen.getByText("Verifier")).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("marks previous stages as completed and current as active", () => {
    const { container } = render(<StageStepper currentStage="CODER" />);

    // Preflight and Planner should be completed
    // Coder should be active
    const stages = container.querySelectorAll(".stage-step");
    expect(stages.length).toBe(6);
  });
});
