import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ToolChip } from "./ToolChip";

describe("ToolChip", () => {
  it("renders read tool chip with path and line count", () => {
    render(
      <ToolChip
        toolName="read"
        data={{ path: "src/app.tsx", lineCount: 42 }}
        stage="PLANNER"
      />
    );

    expect(screen.getByText(/Read src\/app\.tsx \(42 lines\)/i)).toBeInTheDocument();
  });

  it("renders write tool chip with bytes", () => {
    render(
      <ToolChip
        toolName="write"
        data={{ path: "src/config.json", bytes: 256 }}
        stage="CODER"
      />
    );

    expect(screen.getByText(/Write src\/config\.json \(256 B\)/i)).toBeInTheDocument();
  });

  it("calls onClick with toolCallId when clicked", () => {
    const handleClick = vi.fn();
    render(
      <ToolChip
        toolName="bash"
        toolCallId="c-123"
        data={{ command: "pnpm test" }}
        onClick={handleClick}
      />
    );

    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledWith("c-123");
  });
});
