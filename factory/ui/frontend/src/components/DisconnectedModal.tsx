import React from "react";
import { AlertTriangle, GitBranch, RotateCw } from "lucide-react";
import { Button } from "./ui/Button";

export interface DisconnectedModalProps {
  isOpen: boolean;
  branch?: string | null;
  onReconnect: () => void;
  onDismiss?: () => void;
  isReconnecting?: boolean;
}

export const DisconnectedModal: React.FC<DisconnectedModalProps> = ({
  isOpen,
  branch,
  onReconnect,
  onDismiss,
  isReconnecting = false,
}) => {
  if (!isOpen) return null;

  return (
    <div
      id="modal-sandbox-disconnected"
      data-testid="sandbox-disconnected-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="disconnected-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
    >
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
        <div className="flex items-center space-x-3 text-amber-400">
          <AlertTriangle className="w-6 h-6 shrink-0" />
          <h3
            id="disconnected-dialog-title"
            data-testid="sandbox-disconnected-title"
            className="text-base font-semibold text-slate-100"
          >
            Sandbox Disconnected
          </h3>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          The Unified Studio Sandbox reached its 30-minute idle timeout or entered a stopped state.
          Your chat conversation history has been preserved. Reconnect to rehydrate the environment tracked to the active remote branch and resume live preview.
        </p>
        {branch && (
          <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-mono">
            <GitBranch className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span>
              Active branch: <strong className="text-indigo-300">{branch}</strong>
            </span>
          </div>
        )}
        <div className="flex items-center justify-end space-x-3 pt-2">
          {onDismiss && (
            <Button
              id="btn-dismiss-disconnected"
              data-testid="dismiss-disconnected-btn"
              type="button"
              variant="ghost"
              size="sm"
              onClick={onDismiss}
            >
              Dismiss
            </Button>
          )}
          <Button
            id="btn-reconnect-environment"
            data-testid="reconnect-environment-btn"
            type="button"
            variant="primary"
            size="md"
            onClick={onReconnect}
            isLoading={isReconnecting}
            icon={<RotateCw className="w-3.5 h-3.5" />}
            className="shadow-md shadow-indigo-600/20 hover:scale-[1.02]"
          >
            Reconnect Environment
          </Button>
        </div>
      </div>
    </div>
  );
};
