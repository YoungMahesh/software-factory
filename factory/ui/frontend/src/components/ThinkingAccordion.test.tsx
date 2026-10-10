import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ThinkingAccordion } from "./ThinkingAccordion";

describe("ThinkingAccordion", () => {
  it("renders active thinking state with pulsating indicator", () => {
    render(
      <ThinkingAccordion
        stage="PLANNER"
        text="Analyzing repository structure..."
        durationMs={120}
        done={false}
      />
    );

    expect(screen.getByText("Analyzing repository structure...")).toBeInTheDocument();
    expect(screen.getByText(/Thinking/i)).toBeInTheDocument();
  });

  it("renders finished duration badge when done", () => {
    render(
      <ThinkingAccordion
        stage="PLANNER"
        text="Plan synthesized successfully."
        durationMs={4200}
        done={true}
      />
    );

    expect(screen.getByText(/Reasoning finished in 4.2s/i)).toBeInTheDocument();
  });

  it("toggles collapse and expand when header is clicked", () => {
    render(
      <ThinkingAccordion
        stage="PLANNER"
        text="Step 1 details here"
        durationMs={2000}
        done={true}
        defaultExpanded={false}
      />
    );

    const toggleBtn = screen.getByRole("button");
    // Initially collapsed
    expect(screen.queryByText("Step 1 details here")).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(toggleBtn);
    expect(screen.getByText("Step 1 details here")).toBeInTheDocument();

    // Click to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByText("Step 1 details here")).not.toBeInTheDocument();
  });
});
