import React from "react";
import { RotateCcw, X, GitBranch, GitCommit, AlertTriangle, FileCode } from "lucide-react";
import { Button } from "./ui/Button";

export interface TurnRollbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
  isRollingBack?: boolean;
  repo: string;
  branch?: string | null;
  commitSha?: string | null;
  issueNumber?: number | string | null;
  issueTitle?: string | null;
  errorMessage?: string | null;
}

export const TurnRollbackModal: React.FC<TurnRollbackModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  isRollingBack = false,
  repo,
  branch,
  commitSha,
  issueNumber,
  issueTitle,
  errorMessage,
}) => {
  if (!isOpen) return null;

  const displayBranch = branch || "active branch";
  const displayCommit = commitSha ? commitSha.slice(0, 10) : "latest commit";
  const cleanIssueNumber =
    issueNumber !== undefined && issueNumber !== null
      ? String(issueNumber).replace(/^#/, "")
      : null;

  return (
    <div
      id="modal-turn-rollback"
      data-testid="turn-rollback-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rollback-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
    >
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-1 border-b border-slate-800">
          <div className="flex items-center space-x-2.5 text-indigo-400">
            <RotateCcw className="w-5 h-5 shrink-0" />
            <h3
              id="rollback-dialog-title"
              data-testid="rollback-dialog-title"
              className="text-sm font-semibold text-slate-100"
            >
              Roll Back Turn
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isRollingBack}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1 rounded-md"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Description */}
        <p className="text-xs text-slate-300 leading-relaxed">
          Are you sure you want to roll back this turn? This will execute a forward <code className="bg-slate-950 px-1.5 py-0.5 rounded text-indigo-300 border border-slate-800 font-mono text-[11px]">git revert</code> inside the Unified Studio Sandbox, push the revert commit to remote, update dev server dependencies, and reopen the associated work item.
        </p>

        {/* Target Details Grid */}
        <div className="space-y-2 p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-xs font-mono">
          {/* Repo */}
          <div className="flex items-center space-x-2 text-slate-400">
            <span className="text-slate-500 font-sans">Repository:</span>
            <span className="text-indigo-300">{repo}</span>
          </div>

          {/* Issue Info */}
          {(cleanIssueNumber || issueTitle) && (
            <div className="flex items-center space-x-2 text-slate-300">
              <FileCode className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              {cleanIssueNumber && (
                <span className="font-semibold text-indigo-300">Issue #{cleanIssueNumber}</span>
              )}
              {cleanIssueNumber && issueTitle && (
                <span className="text-slate-500">•</span>
              )}
              {issueTitle && (
                <span className="truncate text-slate-200 font-sans">{issueTitle}</span>
              )}
            </div>
          )}

          {/* Commit SHA */}
          <div className="flex items-center space-x-2 text-slate-400">
            <GitCommit className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span className="text-slate-500 font-sans">Target Commit:</span>
            <span className="text-slate-200">{displayCommit}</span>
          </div>

          {/* Branch */}
          <div className="flex items-center space-x-2 text-slate-400">
            <GitBranch className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span className="text-slate-500 font-sans">Branch:</span>
            <span className="text-indigo-300">{displayBranch}</span>
          </div>
        </div>

        {/* Error message banner */}
        {errorMessage && (
          <div
            data-testid="rollback-dialog-error"
            className="flex items-start space-x-2 p-2.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs"
          >
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span className="leading-relaxed">{errorMessage}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center justify-end space-x-2.5 pt-2">
          <Button
            data-testid="cancel-rollback-btn"
            id="btn-cancel-rollback"
            type="button"
            variant="secondary"
            size="sm"
            onClick={onClose}
            disabled={isRollingBack}
          >
            Cancel
          </Button>
          <Button
            data-testid="confirm-rollback-btn"
            id="btn-confirm-rollback"
            type="button"
            variant="primary"
            size="sm"
            onClick={onConfirm}
            isLoading={isRollingBack}
            disabled={isRollingBack}
            icon={<RotateCcw className="w-3.5 h-3.5" />}
          >
            Confirm Rollback
          </Button>
        </div>
      </div>
    </div>
  );
};
