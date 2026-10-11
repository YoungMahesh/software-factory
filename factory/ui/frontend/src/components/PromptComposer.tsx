import React, { useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "./ui/Button";
import { Textarea } from "./ui/Textarea";

export interface PromptComposerProps {
  selectedRepo: string;
  isExecutingTurn: boolean;
  isDisconnected: boolean;
  activeStage?: string;
  onSendPrompt: (prompt: string) => void;
}

export const PromptComposer: React.FC<PromptComposerProps> = ({
  selectedRepo,
  isExecutingTurn,
  isDisconnected,
  activeStage,
  onSendPrompt,
}) => {
  const [prompt, setPrompt] = useState<string>("");

  const isInputLocked = !selectedRepo || isExecutingTurn || isDisconnected;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isInputLocked) return;
    onSendPrompt(prompt.trim());
    setPrompt("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!prompt.trim() || isInputLocked) return;
      onSendPrompt(prompt.trim());
      setPrompt("");
    }
  };

  const placeholder = isDisconnected
    ? "Sandbox disconnected. Click 'Reconnect Environment' to resume chatting."
    : isExecutingTurn
    ? "Assembly line turn in progress..."
    : "Describe what you want to build... (Enter to send)";

  return (
    <div className="p-3.5 bg-slate-900/80 border-t border-slate-800 space-y-2">
      {isExecutingTurn && (
        <div
          data-testid="in-flight-indicator"
          id="studio-in-flight-indicator"
          className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-indigo-950/70 border border-indigo-800/80 text-xs text-indigo-300 font-medium animate-pulse"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
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
          />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[10px] text-slate-500">
            Target: <span className="font-mono text-indigo-300">{selectedRepo || "none"}</span>
          </span>

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
