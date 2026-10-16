import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "./Button";
import { Input } from "./Input";
import { Textarea } from "./Textarea";
import { Badge } from "./Badge";

describe("Cohere Editorial Design System Micro-UI Primitives", () => {
  describe("Button", () => {
    it("renders children and defaults to primary variant with near-black 32px pill geometry", () => {
      render(<Button>Click me</Button>);
      const btn = screen.getByRole("button", { name: /Click me/i });
      expect(btn).toBeInTheDocument();
      expect(btn.className).toContain("bg-primary");
      expect(btn.className).toContain("rounded-pill");
      expect(btn.className).toContain("text-white");
    });

    it("renders variants: pill-outline, secondary, danger, ghost", () => {
      const { rerender } = render(<Button variant="pill-outline">Outlined Pill</Button>);
      const pillBtn = screen.getByRole("button");
      expect(pillBtn.className).toContain("border-hairline");
      expect(pillBtn.className).toContain("rounded-pill");
      expect(pillBtn.className).toContain("bg-transparent");

      rerender(<Button variant="secondary">Secondary Link</Button>);
      const secondaryBtn = screen.getByRole("button");
      expect(secondaryBtn.className).toContain("underline");
      expect(secondaryBtn.className).toContain("bg-transparent");

      rerender(<Button variant="danger">Destructive Action</Button>);
      const dangerBtn = screen.getByRole("button");
      expect(dangerBtn.className).toContain("text-coral");
      expect(dangerBtn.className).toContain("border-coral");
      expect(dangerBtn.className).toContain("rounded-pill");

      rerender(<Button variant="ghost">Ghost Control</Button>);
      const ghostBtn = screen.getByRole("button");
      expect(ghostBtn.className).not.toContain("bg-primary");
      expect(ghostBtn.className).toContain("bg-transparent");
    });

    it("renders sizes: sm, md with pill geometry", () => {
      const { rerender } = render(<Button size="sm">Small</Button>);
      expect(screen.getByRole("button").className).toContain("px-3");
      expect(screen.getByRole("button").className).toContain("rounded-pill");

      rerender(<Button size="md">Medium</Button>);
      expect(screen.getByRole("button").className).toContain("px-4");
      expect(screen.getByRole("button").className).toContain("rounded-pill");
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
    it("renders input with crisp white background, hairline border, and text-ink", () => {
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
      expect(input.className).toContain("bg-white");
      expect(input.className).toContain("border-hairline");
      expect(input.className).toContain("text-ink");
      expect(input.className).toContain("focus:ring-form-focus");

      fireEvent.change(input, { target: { value: "new-repo" } });
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe("Textarea", () => {
    it("renders textarea with crisp white background, hairline border, and form focus", () => {
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
      expect(textarea.className).toContain("bg-white");
      expect(textarea.className).toContain("border-hairline");
      expect(textarea.className).toContain("text-ink");
      expect(textarea.className).toContain("focus:ring-form-focus");

      fireEvent.keyDown(textarea, { key: "Enter" });
      expect(handleKeyDown).toHaveBeenCalled();
    });
  });

  describe("Badge", () => {
    it("renders stage badge variant with uppercase font-mono styling and dark console surface", () => {
      render(<Badge variant="stage">CODER</Badge>);
      const badge = screen.getByText("CODER");
      expect(badge.className).toContain("font-mono");
      expect(badge.className).toContain("uppercase");
      expect(badge.className).toContain("bg-primary");
    });

    it("renders semantic chips: coral taxonomy, console, and pale green success", () => {
      const { rerender } = render(<Badge variant="coral">taxonomy-tag</Badge>);
      const coralBadge = screen.getByText("taxonomy-tag");
      expect(coralBadge.className).toContain("text-coral");

      rerender(<Badge variant="console">ACTIVE_SESSION</Badge>);
      const consoleBadge = screen.getByText("ACTIVE_SESSION");
      expect(consoleBadge.className).toContain("bg-primary");
      expect(consoleBadge.className).toContain("font-mono");

      rerender(<Badge variant="success">Passing</Badge>);
      const successBadge = screen.getByText("Passing");
      expect(successBadge.className).toContain("bg-pale-green");
      expect(successBadge.className).toContain("text-deep-green");

      rerender(<Badge variant="warning">Draft</Badge>);
      const warningBadge = screen.getByText("Draft");
      expect(warningBadge.className).toContain("bg-amber-100");
      expect(warningBadge.className).toContain("text-amber-900");

      rerender(<Badge variant="purple">Merged</Badge>);
      const purpleBadge = screen.getByText("Merged");
      expect(purpleBadge.className).toContain("bg-purple-50");
      expect(purpleBadge.className).toContain("text-purple-800");
    });
  });
});
