import React from "react";
import { GitMerge, ExternalLink, AlertTriangle } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { PullRequest } from "../../types";

export interface StudioPRPopoverProps {
  activePR: PullRequest;
  renderPRControlBadge: () => React.ReactNode;
  isConfirmingMerge: boolean;
  onSetIsConfirmingMerge: (confirming: boolean) => void;
  onPopoverMerge: () => void;
  isMerging: boolean;
  popoverMergeError: string | null;
  prIsDraft: boolean;
  prHasConflict: boolean;
  prIsMerged: boolean;
  prIsClosed: boolean;
  isExecutingTurn: boolean;
}

export const StudioPRPopover: React.FC<StudioPRPopoverProps> = ({
  activePR,
  renderPRControlBadge,
  isConfirmingMerge,
  onSetIsConfirmingMerge,
  onPopoverMerge,
  isMerging,
  popoverMergeError,
  prIsDraft,
  prHasConflict,
  prIsMerged,
  prIsClosed,
  isExecutingTurn,
}) => {
  return (
    <div
      data-testid="studio-pr-popover"
      className="absolute left-0 top-full mt-2 w-80 p-3.5 bg-white border border-hairline rounded-xl shadow-xl z-30 space-y-3 animate-in fade-in zoom-in-95 duration-150"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center space-x-1.5">
            <span className="text-xs font-semibold text-ink truncate">
              {activePR.title}
            </span>
            <span className="text-[11px] font-mono text-muted shrink-0">
              #{activePR.number}
            </span>
          </div>
          <div className="text-[11px] font-mono text-muted">
            {activePR.head_branch} <span className="text-muted">➔</span> main
          </div>
        </div>
        <div className="flex items-center space-x-1 shrink-0">
          {renderPRControlBadge()}
          {activePR.html_url && (
            <a
              data-testid="studio-pr-gh-link"
              href={activePR.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted hover:text-ink transition-colors p-1"
              title="View Pull Request on GitHub"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </div>

      {prHasConflict && (
        <div
          data-testid="studio-popover-conflict-warning"
          className="p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs space-y-1.5"
        >
          <div className="font-semibold text-coral flex items-center space-x-1">
            <AlertTriangle className="w-3.5 h-3.5 text-coral shrink-0" />
            <span>Merge Conflict</span>
          </div>
          <div className="text-[11px] text-coral/90">
            Resolve conflicts on GitHub before merging.
          </div>
          {activePR.html_url && (
            <a
              data-testid="studio-popover-conflict-link"
              href={activePR.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1 text-[11px] font-medium text-coral underline hover:text-ink"
            >
              <span>Resolve conflicts on GitHub</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      )}

      {popoverMergeError && (
        <div className="p-2 rounded-lg bg-coral/10 border border-coral/30 text-coral text-[11px]">
          {popoverMergeError}
        </div>
      )}

      <div className="pt-2 border-t border-hairline">
        {prIsMerged ? (
          <div className="flex items-center space-x-2 py-1 px-2.5 rounded-pill bg-pale-green text-deep-green border border-deep-green/20 text-xs font-medium">
            <GitMerge className="w-3.5 h-3.5 text-deep-green shrink-0" />
            <span>Merged into main</span>
          </div>
        ) : isConfirmingMerge ? (
          <div className="space-y-2">
            <div className="text-[11px] text-ink font-medium">
              Squash merge PR #{activePR.number} into main?
            </div>
            <div className="flex items-center space-x-2">
              <Button
                data-testid="btn-studio-popover-confirm-merge"
                type="button"
                variant="primary"
                size="sm"
                onClick={onPopoverMerge}
                isLoading={isMerging}
                disabled={isMerging}
                icon={<GitMerge className="w-3 h-3" />}
              >
                Confirm Squash Merge
              </Button>
              <Button
                data-testid="btn-studio-popover-cancel-merge"
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onSetIsConfirmingMerge(false)}
                disabled={isMerging}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted">
              {isExecutingTurn ? (
                <span className="text-amber-600">Job running</span>
              ) : prIsDraft ? (
                <span>Draft status</span>
              ) : prHasConflict ? (
                <span className="text-coral">Conflict</span>
              ) : prIsClosed ? (
                <span className="text-muted">Closed</span>
              ) : (
                <span>Ready to merge</span>
              )}
            </span>

            <Button
              data-testid="btn-studio-popover-merge"
              type="button"
              variant="primary"
              size="sm"
              disabled={prIsDraft || isExecutingTurn || prHasConflict || prIsMerged || prIsClosed}
              onClick={() => onSetIsConfirmingMerge(true)}
              icon={<GitMerge className="w-3 h-3" />}
              title={
                isExecutingTurn
                  ? "Cannot merge while assembly line job is executing"
                  : prIsDraft
                  ? "Cannot merge PR in Draft status"
                  : prHasConflict
                  ? "Cannot merge due to conflicts"
                  : prIsClosed
                  ? "Cannot merge a closed pull request"
                  : "Squash merge into main"
              }
            >
              Merge into main
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
