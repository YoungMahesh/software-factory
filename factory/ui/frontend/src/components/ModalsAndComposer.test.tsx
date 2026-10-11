import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { NewAppModal } from "./NewAppModal";
import { DisconnectedModal } from "./DisconnectedModal";
import { PromptComposer } from "./PromptComposer";

describe("Decoupled Modals and PromptComposer", () => {
  describe("NewAppModal", () => {
    it("renders nothing when isOpen is false", () => {
      render(<NewAppModal isOpen={false} onClose={vi.fn()} onCreate={vi.fn()} />);
      expect(screen.queryByText(/Create New App/i)).not.toBeInTheDocument();
    });

    it("validates empty name and triggers onCreate with parameters", async () => {
      const handleCreate = vi.fn().mockResolvedValue(undefined);
      const handleClose = vi.fn();
      render(<NewAppModal isOpen={true} onClose={handleClose} onCreate={handleCreate} />);

      expect(screen.getByText(/Create New App/i)).toBeInTheDocument();

      // Submit with empty name
      fireEvent.click(screen.getByRole("button", { name: /Create App/i }));
      expect(screen.getByText("App name is required.")).toBeInTheDocument();
      expect(handleCreate).not.toHaveBeenCalled();

      // Fill name and submit
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. inventory-tracker/i), {
        target: { value: "my-new-app" },
      });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. Inventory management dashboard/i), {
        target: { value: "Nice description" },
      });
      fireEvent.click(screen.getByRole("button", { name: /Create App/i }));

      await waitFor(() => {
        expect(handleCreate).toHaveBeenCalledWith({
          name: "my-new-app",
          description: "Nice description",
        });
        expect(handleClose).toHaveBeenCalled();
      });
    });

    it("displays error message if onCreate throws", async () => {
      const handleCreate = vi.fn().mockRejectedValue(new Error("Repo already exists"));
      render(<NewAppModal isOpen={true} onClose={vi.fn()} onCreate={handleCreate} />);

      fireEvent.change(screen.getByPlaceholderText(/e\.g\. inventory-tracker/i), {
        target: { value: "existing-app" },
      });
      fireEvent.click(screen.getByRole("button", { name: /Create App/i }));

      await waitFor(() => {
        expect(screen.getByText("Repo already exists")).toBeInTheDocument();
      });
    });
  });

  describe("DisconnectedModal", () => {
    it("renders dialog with active branch and calls onReconnect", () => {
      const handleReconnect = vi.fn();
      render(
        <DisconnectedModal
          isOpen={true}
          branch="factory/feature-x"
          onReconnect={handleReconnect}
        />
      );

      const dialog = screen.getByTestId("sandbox-disconnected-dialog");
      expect(dialog).toBeInTheDocument();
      expect(screen.getByText("factory/feature-x")).toBeInTheDocument();

      const btn = screen.getByTestId("reconnect-environment-btn");
      fireEvent.click(btn);
      expect(handleReconnect).toHaveBeenCalledTimes(1);
    });
  });

  describe("PromptComposer", () => {
    it("handles Enter to send, clears input, and ignores Shift+Enter", () => {
      const handleSend = vi.fn();
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={handleSend}
        />
      );

      const input = screen.getByTestId("studio-prompt-input");

      // Shift+Enter does not submit
      fireEvent.change(input, { target: { value: "Multi-line text" } });
      fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
      expect(handleSend).not.toHaveBeenCalled();

      // Enter submits
      fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
      expect(handleSend).toHaveBeenCalledWith("Multi-line text");
      expect(input).toHaveValue("");
    });

    it("locks input and shows in-flight indicator when isExecutingTurn is true", () => {
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={true}
          isDisconnected={false}
          activeStage="CODER"
          onSendPrompt={vi.fn()}
        />
      );

      expect(screen.getByTestId("in-flight-indicator")).toHaveTextContent("CODER");
      expect(screen.getByTestId("studio-prompt-input")).toBeDisabled();
      expect(screen.getByRole("button", { name: /Send/i })).toBeDisabled();
    });

    it("locks input when isDisconnected is true", () => {
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={true}
          onSendPrompt={vi.fn()}
        />
      );

      expect(screen.getByTestId("studio-prompt-input")).toBeDisabled();
      expect(screen.getByPlaceholderText(/Sandbox disconnected/i)).toBeInTheDocument();
    });
  });
});
