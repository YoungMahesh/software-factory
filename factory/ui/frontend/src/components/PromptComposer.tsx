import React, { useState } from "react";
import { Send, Loader2, Trash2, Check, RotateCcw, Lock } from "lucide-react";
import { Button } from "./ui/Button";
import { Textarea } from "./ui/Textarea";

export interface PromptComposerProps {
  selectedRepo: string;
  isExecutingTurn: boolean;
  isDisconnected: boolean;
  activeStage?: string;
  onSendPrompt: (prompt: string, grill?: boolean) => void;
  defaultGrillMode?: boolean;
  onClearChat?: () => void;
  isClearingChat?: boolean;
  isChatCleared?: boolean;
  onRollbackLastTurn?: () => void;
  isRollingBack?: boolean;
  isRollbackDisabled?: boolean;
  rollbackDisabledReason?: string;
}

export const PromptComposer: React.FC<PromptComposerProps> = ({
  selectedRepo,
  isExecutingTurn,
  isDisconnected,
  activeStage,
  onSendPrompt,
  defaultGrillMode = true,
  onClearChat,
  isClearingChat = false,
  isChatCleared = false,
  onRollbackLastTurn,
  isRollingBack = false,
  isRollbackDisabled = false,
  rollbackDisabledReason,
}) => {
  const [prompt, setPrompt] = useState<string>("");
  const [grillMode, setGrillMode] = useState<boolean>(defaultGrillMode);

  const isInputLocked = !selectedRepo || isExecutingTurn || isDisconnected;

  const submitPrompt = () => {
    if (!prompt.trim() || isInputLocked) return;
    onSendPrompt(prompt.trim(), grillMode);
    setPrompt("");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitPrompt();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitPrompt();
    }
  };

  const placeholder = isDisconnected
    ? "Sandbox disconnected. Click 'Reconnect Environment' to resume chatting."
    : isExecutingTurn
    ? "Assembly line turn in progress..."
    : "Describe what you want to build... (Enter to send)";

  return (
    <div className="p-3.5 bg-soft-stone border-t border-hairline space-y-2">
      {isExecutingTurn && (
        <div
          data-testid="in-flight-indicator"
          id="studio-in-flight-indicator"
          className="flex items-center space-x-2 px-3.5 py-1.5 rounded-pill bg-primary border border-white/20 text-xs text-white font-medium animate-pulse shadow-sm"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin text-white shrink-0" />
          <span>
            Assembly line turn in progress ({activeStage || "DISPATCHING"})...
          </span>
        </div>
      )}

      <form id="studio-prompt-form" onSubmit={handleSubmit} className="space-y-2">
        <div className="relative">
          <Textarea
            id="studio-prompt-input"
            data-testid="studio-prompt-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isInputLocked}
            rows={3}
            className="shadow-2xs"
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="text-[10px] text-muted">
              Target: <span className="font-mono text-ink font-semibold">{selectedRepo || "none"}</span>
            </span>

            <label
              htmlFor="studio-grill-toggle"
              className="inline-flex items-center space-x-1.5 cursor-pointer text-xs select-none px-2.5 py-1 rounded-pill bg-white border border-hairline hover:bg-soft-stone/70 transition-colors shadow-2xs"
            >
              <input
                type="checkbox"
                id="studio-grill-toggle"
                data-testid="grill-mode-toggle"
                checked={grillMode}
                onChange={(e) => setGrillMode(e.target.checked)}
                disabled={isInputLocked}
                className="w-3.5 h-3.5 rounded border-hairline bg-white text-primary focus:ring-form-focus focus:ring-offset-0 cursor-pointer"
              />
              <span className="font-medium text-[11px] text-ink">
                Grill &amp; Align <span className="text-[10px] text-coral font-normal">(Recommended)</span>
              </span>
            </label>

            {onClearChat && (
              <Button
                id="btn-studio-clear-chat"
                data-testid="clear-chat-btn"
                type="button"
                variant="ghost"
                size="sm"
                onClick={onClearChat}
                disabled={!selectedRepo || isExecutingTurn || isClearingChat}
                isLoading={isClearingChat}
                icon={<Trash2 className="w-3.5 h-3.5 text-muted" />}
                className="text-xs text-muted hover:text-coral px-2 py-1"
                title="Clear chat history for this repository"
              >
                Clear Chat
              </Button>
            )}

            {onRollbackLastTurn && (
              <Button
                id="btn-composer-rollback"
                data-testid="composer-rollback-btn"
                type="button"
                variant="ghost"
                size="sm"
                onClick={onRollbackLastTurn}
                disabled={isInputLocked || isRollingBack || isRollbackDisabled}
                isLoading={isRollingBack}
                icon={
                  isInputLocked || isRollbackDisabled ? (
                    <Lock className="w-3.5 h-3.5 text-muted" data-testid="composer-rollback-lock-icon" />
                  ) : (
                    <RotateCcw className="w-3.5 h-3.5 text-muted" />
                  )
                }
                className="text-xs text-muted hover:text-ink px-2 py-1"
                title={
                  isExecutingTurn
                    ? "Cannot roll back turn while job is active"
                    : rollbackDisabledReason || "Roll back last turn on active branch"
                }
              >
                Roll Back Last Turn
              </Button>
            )}

            {isChatCleared && (
              <span
                data-testid="clear-chat-confirmation"
                className="inline-flex items-center space-x-1 text-[11px] text-deep-green font-medium bg-pale-green border border-deep-green/20 px-2.5 py-0.5 rounded-pill"
              >
                <Check className="w-3 h-3 text-deep-green shrink-0" />
                <span>Chat cleared</span>
              </span>
            )}
          </div>

          <Button
            id="btn-studio-send"
            type="submit"
            variant="primary"
            size="md"
            disabled={!prompt.trim() || isInputLocked}
            isLoading={isExecutingTurn}
            icon={<Send className="w-3.5 h-3.5" />}
          >
            Send
          </Button>
        </div>
      </form>
    </div>
  );
};
