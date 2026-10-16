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
      className="fixed inset-0 z-50 flex items-center justify-center bg-cohere-black/50 backdrop-blur-2xs p-4"
    >
      <div className="w-full max-w-md bg-white border border-hairline rounded-[22px] p-6 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-hairline">
          <div className="flex items-center space-x-2.5 text-coral">
            <RotateCcw className="w-5 h-5 shrink-0" />
            <h3
              id="rollback-dialog-title"
              data-testid="rollback-dialog-title"
              className="text-sm font-semibold text-ink font-sans"
            >
              Roll Back Turn
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isRollingBack}
            className="text-muted hover:text-ink transition-colors p-1 rounded-pill hover:bg-soft-stone cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Description */}
        <p className="text-xs text-ink leading-relaxed">
          Are you sure you want to roll back this turn? This will execute a forward <code className="bg-soft-stone px-1.5 py-0.5 rounded-pill text-ink border border-hairline font-mono text-[11px]">git revert</code> inside the Unified Studio Sandbox, push the revert commit to remote, update dev server dependencies, and reopen the associated work item.
        </p>

        {/* Target Details Grid */}
        <div className="space-y-2 p-3.5 rounded-xl bg-soft-stone border border-hairline text-xs font-mono">
          {/* Repo */}
          <div className="flex items-center space-x-2 text-muted">
            <span className="text-muted font-sans">Repository:</span>
            <span className="text-primary font-semibold">{repo}</span>
          </div>

          {/* Issue Info */}
          {(cleanIssueNumber || issueTitle) && (
            <div className="flex items-center space-x-2 text-ink">
              <FileCode className="w-3.5 h-3.5 text-primary shrink-0" />
              {cleanIssueNumber && (
                <span className="font-semibold text-primary">Issue #{cleanIssueNumber}</span>
              )}
              {cleanIssueNumber && issueTitle && (
                <span className="text-muted">•</span>
              )}
              {issueTitle && (
                <span className="truncate text-ink font-sans">{issueTitle}</span>
              )}
            </div>
          )}

          {/* Commit SHA */}
          <div className="flex items-center space-x-2 text-muted">
            <GitCommit className="w-3.5 h-3.5 text-primary shrink-0" />
            <span className="text-muted font-sans">Target Commit:</span>
            <span className="text-ink font-semibold">{displayCommit}</span>
          </div>

          {/* Branch */}
          <div className="flex items-center space-x-2 text-muted">
            <GitBranch className="w-3.5 h-3.5 text-primary shrink-0" />
            <span className="text-muted font-sans">Branch:</span>
            <span className="text-primary font-semibold">{displayBranch}</span>
          </div>
        </div>

        {/* Error message banner */}
        {errorMessage && (
          <div
            data-testid="rollback-dialog-error"
            className="flex items-start space-x-2 p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs"
          >
            <AlertTriangle className="w-4 h-4 text-coral shrink-0 mt-0.5" />
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
            variant="danger"
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
