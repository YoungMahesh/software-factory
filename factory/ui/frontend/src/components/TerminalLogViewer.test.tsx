import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TerminalLogViewer } from "./TerminalLogViewer";

describe("TerminalLogViewer", () => {
  it("renders lines with line count", () => {
    const logs = ["Line 1\n", "Line 2\n", "Line 3\n"];
    render(<TerminalLogViewer logs={logs} />);

    expect(screen.getByText("3 lines")).toBeInTheDocument();
    expect(screen.getByText("Line 1")).toBeInTheDocument();
    expect(screen.getByText("Line 2")).toBeInTheDocument();
    expect(screen.getByText("Line 3")).toBeInTheDocument();
  });

  it("copies logs when copy button is clicked", () => {
    const logs = ["Hello world\n"];
    render(<TerminalLogViewer logs={logs} />);

    const copyBtn = screen.getByRole("button", { name: /Copy/i });
    fireEvent.click(copyBtn);
    expect(screen.getByText(/Copied/i)).toBeInTheDocument();
  });

  it("handles clear logs callback", () => {
    const handleClear = vi.fn();
    render(<TerminalLogViewer logs={["Line 1\n"]} onClear={handleClear} />);

    const clearBtn = screen.getByRole("button", { name: /Clear/i });
    fireEvent.click(clearBtn);
    expect(handleClear).toHaveBeenCalled();
  });
});
