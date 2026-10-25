import React from "react";
import {
  Box,
  Plus,
  Lock,
  GitPullRequest,
  Play,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { PullRequest, PreviewState } from "../../types";
import { StudioPRPopover } from "./StudioPRPopover";

export interface StudioHeaderProps {
  repos: Array<{ name: string; is_tanstack_compatible?: boolean; private?: boolean }>;
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  onOpenNewAppModal: () => void;
  openIssuesCount: number;
  onOpenIssues: () => void;
  activePR?: PullRequest;
  renderPRControlBadge: () => React.ReactNode;
  isPRPopoverOpen: boolean;
  onTogglePRPopover: () => void;
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
  previewState: PreviewState | null;
  isServing: boolean;
  isProvisioning: boolean;
  isLaunchingPreview: boolean;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
}

export const StudioHeader: React.FC<StudioHeaderProps> = ({
  repos,
  selectedRepo,
  onSelectRepo,
  onOpenNewAppModal,
  openIssuesCount,
  onOpenIssues,
  activePR,
  renderPRControlBadge,
  isPRPopoverOpen,
  onTogglePRPopover,
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
  isServing,
  isProvisioning,
  isLaunchingPreview,
  onLaunchPreview,
  onStopPreview,
}) => {
  return (
    <div className="flex items-center justify-between px-6 py-2.5 bg-soft-stone border-b border-hairline shrink-0">
      <div className="flex items-center space-x-3">
        <Box className="w-4 h-4 text-ink" />
        <span className="text-xs font-semibold text-ink font-sans">Current App:</span>
        <select
          id="studio-select-repo"
          value={selectedRepo}
          onChange={(e) => onSelectRepo(e.target.value)}
          className="bg-white border border-hairline rounded-pill px-3 py-1.5 text-xs text-ink font-medium focus:outline-none focus:ring-1 focus:ring-form-focus shadow-2xs"
        >
          <option value="">Select a repository...</option>
          {repos.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name} {r.is_tanstack_compatible ? "✦" : ""}{r.private ? " 🔒" : ""}
            </option>
          ))}
        </select>

        {repos.find((r) => r.name === selectedRepo)?.private && (
          <span
            data-testid="studio-repo-private-badge"
            className="flex items-center text-[10px] font-medium px-2.5 py-0.5 rounded-pill bg-white text-muted border border-hairline space-x-1 shadow-2xs"
            title="Private repository"
          >
            <Lock className="w-3 h-3 text-muted" />
            <span>Private</span>
          </span>
        )}

        <Button
          id="btn-studio-new-app"
          type="button"
          variant="primary"
          size="sm"
          onClick={onOpenNewAppModal}
          icon={<Plus className="w-3.5 h-3.5" />}
        >
          New App
        </Button>

        {selectedRepo && (
          <div className="flex items-center space-x-2">
            <Button
              id="btn-studio-issues"
              data-testid="studio-issues-btn"
              type="button"
              variant="pill-outline"
              size="sm"
              onClick={onOpenIssues}
              icon={<GitPullRequest className="w-3.5 h-3.5 text-ink" />}
              title="View GitHub Issues"
              className="relative bg-white"
            >
              <span>Issues</span>
              <span
                data-testid="studio-issues-badge"
                className="ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-coral/10 text-coral border border-coral/30"
              >
                {openIssuesCount}
              </span>
            </Button>

            {/* Feature Pull Request Status Button & Popover */}
            {activePR && (
              <div className="relative">
                <Button
                  id="btn-studio-pr-status"
                  data-testid="studio-pr-control-btn"
                  type="button"
                  variant="pill-outline"
                  size="sm"
                  onClick={onTogglePRPopover}
                  icon={<GitPullRequest className="w-3.5 h-3.5 text-ink" />}
                  title={`Feature Pull Request #${activePR.number} status`}
                  className="relative bg-white"
                >
                  <span>PR #{activePR.number}</span>
                  {renderPRControlBadge()}
                </Button>

                {isPRPopoverOpen && (
                  <StudioPRPopover
                    activePR={activePR}
                    renderPRControlBadge={renderPRControlBadge}
                    isConfirmingMerge={isConfirmingMerge}
                    onSetIsConfirmingMerge={onSetIsConfirmingMerge}
                    onPopoverMerge={onPopoverMerge}
                    isMerging={isMerging}
                    popoverMergeError={popoverMergeError}
                    prIsDraft={prIsDraft}
                    prHasConflict={prHasConflict}
                    prIsMerged={prIsMerged}
                    prIsClosed={prIsClosed}
                    isExecutingTurn={isExecutingTurn}
                  />
                )}
              </div>
            )}

            <Button
              id="btn-studio-preview-app"
              data-testid="preview-app-btn"
              type="button"
              variant="pill-outline"
              size="sm"
              onClick={() => {
                if (isServing && onStopPreview) {
                  onStopPreview();
                } else if (onLaunchPreview) {
                  onLaunchPreview();
                }
              }}
              disabled={isLaunchingPreview || isProvisioning}
              isLoading={isLaunchingPreview || isProvisioning}
              icon={
                isServing ? (
                  <span className="w-2 h-2 rounded-full bg-deep-green animate-pulse mr-0.5" />
                ) : (
                  <Play className="w-3.5 h-3.5 text-ink fill-current" />
                )
              }
              title={
                isServing
                  ? "Preview active (click to stop)"
                  : "Launch Unified Studio Sandbox"
              }
              className={
                isServing
                  ? "bg-pale-green border-deep-green/30 text-deep-green hover:bg-pale-green/80"
                  : isProvisioning || isLaunchingPreview
                  ? "bg-soft-stone text-muted cursor-wait"
                  : "bg-white"
              }
            >
              Preview App
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
