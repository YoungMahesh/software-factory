import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "./Button";
import { Input } from "./Input";
import { Textarea } from "./Textarea";
import { Badge } from "./Badge";

describe("Micro-UI Primitives", () => {
  describe("Button", () => {
    it("renders children and defaults to primary variant and md size", () => {
      render(<Button>Click me</Button>);
      const btn = screen.getByRole("button", { name: /Click me/i });
      expect(btn).toBeInTheDocument();
      expect(btn.className).toContain("bg-indigo-600");
    });

    it("renders variants: secondary, danger, ghost", () => {
      const { rerender } = render(<Button variant="secondary">Secondary</Button>);
      expect(screen.getByRole("button")).toHaveClass("bg-slate-800");

      rerender(<Button variant="danger">Danger</Button>);
      expect(screen.getByRole("button")).toHaveClass("bg-rose-600");

      rerender(<Button variant="ghost">Ghost</Button>);
      expect(screen.getByRole("button")).not.toHaveClass("bg-indigo-600");
      expect(screen.getByRole("button")).not.toHaveClass("bg-rose-600");
    });

    it("renders sizes: sm, md", () => {
      const { rerender } = render(<Button size="sm">Small</Button>);
      expect(screen.getByRole("button").className).toContain("px-2.5");

      rerender(<Button size="md">Medium</Button>);
      expect(screen.getByRole("button").className).toContain("px-4");
    });

    it("displays spinner and disables button when isLoading is true", () => {
      const handleClick = vi.fn();
      render(
        <Button isLoading onClick={handleClick}>
          Submitting
        </Button>
      );
      const btn = screen.getByRole("button");
      expect(btn).toBeDisabled();
      expect(btn.querySelector(".animate-spin")).toBeInTheDocument();

      fireEvent.click(btn);
      expect(handleClick).not.toHaveBeenCalled();
    });

    it("handles disabled prop properly", () => {
      render(<Button disabled>Disabled</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toBeDisabled();
      expect(btn.className).toContain("disabled:opacity");
    });
  });

  describe("Input", () => {
    it("renders input with standard styling and forwards input attributes", () => {
      const handleChange = vi.fn();
      render(
        <Input
          placeholder="Enter repo name..."
          value="test-repo"
          onChange={handleChange}
        />
      );
      const input = screen.getByPlaceholderText("Enter repo name...");
      expect(input).toHaveValue("test-repo");
      expect(input.className).toContain("bg-slate-950");
      expect(input.className).toContain("border-slate-800");

      fireEvent.change(input, { target: { value: "new-repo" } });
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe("Textarea", () => {
    it("renders textarea with standardized styling and forwards props", () => {
      const handleKeyDown = vi.fn();
      render(
        <Textarea
          placeholder="Describe changes..."
          rows={3}
          onKeyDown={handleKeyDown}
        />
      );
      const textarea = screen.getByPlaceholderText("Describe changes...");
      expect(textarea).toBeInTheDocument();
      expect(textarea.className).toContain("bg-slate-950");
      expect(textarea.className).toContain("rounded-");

      fireEvent.keyDown(textarea, { key: "Enter" });
      expect(handleKeyDown).toHaveBeenCalled();
    });
  });

  describe("Badge", () => {
    it("renders stage badge variant with uppercase font-mono styling", () => {
      render(<Badge variant="stage">CODER</Badge>);
      const badge = screen.getByText("CODER");
      expect(badge.className).toContain("font-mono");
      expect(badge.className).toContain("bg-indigo-950");
      expect(badge.className).toContain("text-indigo-300");
    });

    it("renders status pill variants", () => {
      const { rerender } = render(<Badge variant="success">Active</Badge>);
      expect(screen.getByText("Active").className).toContain("text-emerald-");

      rerender(<Badge variant="danger">Failed</Badge>);
      expect(screen.getByText("Failed").className).toContain("text-rose-");

      rerender(<Badge variant="warning">Disconnected</Badge>);
      expect(screen.getByText("Disconnected").className).toContain("text-amber-");
    });
  });
});
