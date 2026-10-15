import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

      // Verify private checkbox is checked by default
      const privateCheckbox = screen.getByLabelText(/Private repository/i);
      expect(privateCheckbox).toBeInTheDocument();
      expect(privateCheckbox).toBeChecked();

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
          private: true,
        });
        expect(handleClose).toHaveBeenCalled();
      });
    });

    it("allows toggling repository visibility to public", async () => {
      const handleCreate = vi.fn().mockResolvedValue(undefined);
      const handleClose = vi.fn();
      render(<NewAppModal isOpen={true} onClose={handleClose} onCreate={handleCreate} />);

      const privateCheckbox = screen.getByLabelText(/Private repository/i);
      expect(privateCheckbox).toBeChecked();

      // Uncheck private checkbox
      fireEvent.click(privateCheckbox);
      expect(privateCheckbox).not.toBeChecked();

      fireEvent.change(screen.getByPlaceholderText(/e\.g\. inventory-tracker/i), {
        target: { value: "my-public-app" },
      });
      fireEvent.click(screen.getByRole("button", { name: /Create App/i }));

      await waitFor(() => {
        expect(handleCreate).toHaveBeenCalledWith({
          name: "my-public-app",
          description: undefined,
          private: false,
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

    it("renders dismiss control and triggers onDismiss callback", () => {
      const handleDismiss = vi.fn();
      render(
        <DisconnectedModal
          isOpen={true}
          branch="factory/feature-x"
          onReconnect={vi.fn()}
          onDismiss={handleDismiss}
        />
      );

      const dismissBtn = screen.getByTestId("dismiss-disconnected-btn");
      expect(dismissBtn).toBeInTheDocument();
      fireEvent.click(dismissBtn);
      expect(handleDismiss).toHaveBeenCalledTimes(1);
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
      expect(handleSend).toHaveBeenCalledWith("Multi-line text", true);
      expect(input).toHaveValue("");
    });

    it("renders 'Grill & Align (Recommended)' toggle defaulting to enabled and submits with grill=true", () => {
      const handleSend = vi.fn();
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={handleSend}
        />
      );

      const toggle = screen.getByTestId("grill-mode-toggle") as HTMLInputElement;
      expect(toggle).toBeInTheDocument();
      expect(toggle.checked).toBe(true);
      expect(screen.getByText(/Grill & Align/i)).toBeInTheDocument();
      expect(screen.getByText(/Recommended/i)).toBeInTheDocument();

      const input = screen.getByTestId("studio-prompt-input");
      fireEvent.change(input, { target: { value: "Build analytics" } });
      fireEvent.click(screen.getByRole("button", { name: /Send/i }));

      expect(handleSend).toHaveBeenCalledWith("Build analytics", true);
    });

    it("allows unchecking 'Grill & Align' to bypass grilling and submit with grill=false", () => {
      const handleSend = vi.fn();
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={handleSend}
        />
      );

      const toggle = screen.getByTestId("grill-mode-toggle") as HTMLInputElement;
      expect(toggle.checked).toBe(true);

      // Uncheck toggle
      fireEvent.click(toggle);
      expect(toggle.checked).toBe(false);

      const input = screen.getByTestId("studio-prompt-input");
      fireEvent.change(input, { target: { value: "Fix button color" } });
      fireEvent.click(screen.getByRole("button", { name: /Send/i }));

      expect(handleSend).toHaveBeenCalledWith("Fix button color", false);
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

    it("renders 'Clear Chat' button in toolbar and triggers onClearChat", () => {
      const handleClear = vi.fn();
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={vi.fn()}
          onClearChat={handleClear}
        />
      );

      const clearBtn = screen.getByRole("button", { name: /Clear Chat/i });
      expect(clearBtn).toBeInTheDocument();
      fireEvent.click(clearBtn);
      expect(handleClear).toHaveBeenCalledTimes(1);
    });

    it("disables 'Clear Chat' when isExecutingTurn is true or isClearingChat is true", () => {
      const { rerender } = render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={true}
          isDisconnected={false}
          onSendPrompt={vi.fn()}
          onClearChat={vi.fn()}
        />
      );

      expect(screen.getByRole("button", { name: /Clear Chat/i })).toBeDisabled();

      rerender(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          isClearingChat={true}
          onSendPrompt={vi.fn()}
          onClearChat={vi.fn()}
        />
      );

      expect(screen.getByRole("button", { name: /Clear Chat/i })).toBeDisabled();
    });

    it("displays visual confirmation when isChatCleared is true", () => {
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={vi.fn()}
          onClearChat={vi.fn()}
          isChatCleared={true}
        />
      );

      expect(screen.getByTestId("clear-chat-confirmation")).toBeInTheDocument();
      expect(screen.getByText(/Chat cleared/i)).toBeInTheDocument();
    });

    it("renders 'Undo Last Turn' button shortcut and triggers onRollbackLastTurn", async () => {
      const user = userEvent.setup();
      const handleRollback = vi.fn();
      render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          onSendPrompt={vi.fn()}
          onRollbackLastTurn={handleRollback}
        />
      );

      const undoBtn = screen.getByTestId("composer-rollback-btn");
      expect(undoBtn).toBeInTheDocument();
      expect(undoBtn).not.toBeDisabled();
      expect(undoBtn).toHaveTextContent(/Undo Last Turn/i);

      await user.click(undoBtn);
      expect(handleRollback).toHaveBeenCalledTimes(1);
    });

    it("disables 'Undo Last Turn' button and shows lock icon when isExecutingTurn is true or isRollingBack is true", () => {
      const { rerender } = render(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={true}
          isDisconnected={false}
          onSendPrompt={vi.fn()}
          onRollbackLastTurn={vi.fn()}
        />
      );

      expect(screen.getByTestId("composer-rollback-btn")).toBeDisabled();
      expect(screen.getByTestId("composer-rollback-lock-icon")).toBeInTheDocument();

      rerender(
        <PromptComposer
          selectedRepo="test-repo"
          isExecutingTurn={false}
          isDisconnected={false}
          isRollingBack={true}
          onSendPrompt={vi.fn()}
          onRollbackLastTurn={vi.fn()}
        />
      );

      expect(screen.getByTestId("composer-rollback-btn")).toBeDisabled();
    });
  });
});


