import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CommandCard } from "./CommandCard";

describe("CommandCard", () => {
  it("renders running state with spinner", () => {
    render(
      <CommandCard
        command="pnpm test"
        cwd="/workspace"
        stage="CODER"
        running={true}
      />
    );

    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("/workspace")).toBeInTheDocument();
    expect(screen.getByTestId("running-spinner")).toBeInTheDocument();
  });

  it("renders exit code 0 badge in green when successful", () => {
    render(
      <CommandCard
        command="pnpm build"
        exitCode={0}
        running={false}
        durationMs={450}
        output="Build complete."
      />
    );

    expect(screen.getByText("Exit code 0")).toBeInTheDocument();
    expect(screen.getByText("Build complete.")).toBeInTheDocument();
  });

  it("auto-expands and highlights stderr lines on non-zero exit code", () => {
    const errorOutput = "Running tests...\nAssertionError: expected 1 to be 2\nFAILED tests/test_math.py";
    render(
      <CommandCard
        command="pytest"
        exitCode={1}
        isError={true}
        running={false}
        output={errorOutput}
        stderr="AssertionError: expected 1 to be 2\nFAILED tests/test_math.py"
      />
    );

    expect(screen.getByText("Exit code 1")).toBeInTheDocument();
    const stderrLine = screen.getByText("FAILED tests/test_math.py");
    expect(stderrLine).toBeInTheDocument();
    expect(stderrLine.className).toMatch(/text-red-400|stderr/);
  });

  it("windows output to last 100 lines and allows toggling full output", () => {
    const lines = Array.from({ length: 150 }, (_, i) => `Log line ${i + 1}`);
    const fullOutput = lines.join("\n");

    render(
      <CommandCard
        command="npm install"
        exitCode={0}
        running={false}
        output={fullOutput}
      />
    );

    // Should indicate showing last 100 of 150 lines
    expect(screen.getByText(/Showing last 100 of 150 lines/i)).toBeInTheDocument();
    expect(screen.getByText(/\[View full output\]/i)).toBeInTheDocument();

    // First line should not be in windowed view
    expect(screen.queryByText("Log line 1")).not.toBeInTheDocument();
    // Line 150 should be visible
    expect(screen.getByText("Log line 150")).toBeInTheDocument();

    // Click view full output
    fireEvent.click(screen.getByText(/\[View full output\]/i));
    expect(screen.getByText("Log line 1")).toBeInTheDocument();
    expect(screen.getByText(/\[Show last 100 lines\]/i)).toBeInTheDocument();
  });

  it("allows collapsing and expanding output using toggle button", () => {
    render(
      <CommandCard
        command="pnpm test"
        exitCode={1}
        output="FAIL src/app.test.ts"
      />
    );

    expect(screen.getByText("FAIL src/app.test.ts")).toBeInTheDocument();
    const toggleBtn = screen.getByTestId("toggle-output-btn");

    // Collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByText("FAIL src/app.test.ts")).not.toBeInTheDocument();

    // Re-expand
    fireEvent.click(toggleBtn);
    expect(screen.getByText("FAIL src/app.test.ts")).toBeInTheDocument();
  });
});
