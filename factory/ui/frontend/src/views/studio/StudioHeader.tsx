import React from "react";
import {
  Box,
  Plus,
  Lock,
  GitPullRequest,
  Play,
  Square,
  Activity,
  Terminal,
  XCircle,
  GitMerge,
  ExternalLink,
  AlertTriangle,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { PullRequest, PreviewState } from "../../types";

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
  activeJob: any;
  onOpenDrawer?: (toolCallId?: string) => void;
  onSwitchToConsole?: () => void;
  onCancelJob: (jobId: string) => void;
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
  activeJob,
  onOpenDrawer,
  onSwitchToConsole,
  onCancelJob,
}) => {
  return (
    <div className="flex items-center justify-between px-6 py-2.5 bg-slate-900 border-b border-slate-800 shrink-0">
      <div className="flex items-center space-x-3">
        <Box className="w-4 h-4 text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Current App:</span>
        <select
          id="studio-select-repo"
          value={selectedRepo}
          onChange={(e) => onSelectRepo(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500"
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
            className="flex items-center text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 space-x-1"
            title="Private repository"
          >
            <Lock className="w-3 h-3 text-slate-400" />
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
              variant="secondary"
              size="sm"
              onClick={onOpenIssues}
              icon={<GitPullRequest className="w-3.5 h-3.5 text-indigo-400" />}
              title="View GitHub Issues"
              className="relative"
            >
              <span>Issues</span>
              <span
                data-testid="studio-issues-badge"
                className="ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-indigo-950 text-indigo-300 border border-indigo-800"
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
                  variant="secondary"
                  size="sm"
                  onClick={onTogglePRPopover}
                  icon={<GitPullRequest className="w-3.5 h-3.5 text-indigo-400" />}
                  title={`Feature Pull Request #${activePR.number} status`}
                  className="relative"
                >
                  <span>PR #{activePR.number}</span>
                  {renderPRControlBadge()}
                </Button>

                {isPRPopoverOpen && (
                  <div
                    data-testid="studio-pr-popover"
                    className="absolute left-0 top-full mt-2 w-80 p-3.5 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-30 space-y-3 animate-in fade-in zoom-in-95 duration-150"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center space-x-1.5">
                          <span className="text-xs font-semibold text-slate-100 truncate">
                            {activePR.title}
                          </span>
                          <span className="text-[11px] font-mono text-slate-400 shrink-0">
                            #{activePR.number}
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          {activePR.head_branch} <span className="text-slate-500">➔</span> main
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
                            className="text-slate-400 hover:text-indigo-300 transition-colors p-1"
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
                        className="p-2.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs space-y-1.5"
                      >
                        <div className="font-semibold text-rose-200 flex items-center space-x-1">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                          <span>Merge Conflict</span>
                        </div>
                        <div className="text-[11px] text-rose-300/90">
                          Resolve conflicts on GitHub before merging.
                        </div>
                        {activePR.html_url && (
                          <a
                            data-testid="studio-popover-conflict-link"
                            href={activePR.html_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center space-x-1 text-[11px] font-medium text-rose-300 underline hover:text-white"
                          >
                            <span>Resolve conflicts on GitHub</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                    )}

                    {popoverMergeError && (
                      <div className="p-2 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-[11px]">
                        {popoverMergeError}
                      </div>
                    )}

                    <div className="pt-2 border-t border-slate-800">
                      {prIsMerged ? (
                        <div className="flex items-center space-x-2 py-1 px-2.5 rounded bg-purple-950/40 border border-purple-900/50 text-purple-300 text-xs font-medium">
                          <GitMerge className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                          <span>Merged into main</span>
                        </div>
                      ) : isConfirmingMerge ? (
                        <div className="space-y-2">
                          <div className="text-[11px] text-slate-300 font-medium">
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
                          <span className="text-[11px] text-slate-400">
                            {isExecutingTurn ? (
                              <span className="text-amber-400">Job running</span>
                            ) : prIsDraft ? (
                              <span>Draft status</span>
                            ) : prHasConflict ? (
                              <span className="text-rose-400">Conflict</span>
                            ) : prIsClosed ? (
                              <span className="text-slate-400">Closed</span>
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
                )}
              </div>
            )}

            <Button
              id="btn-studio-preview-app"
              data-testid="preview-app-btn"
              type="button"
              variant="secondary"
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
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-0.5" />
                ) : (
                  <Play className="w-3.5 h-3.5 text-indigo-400 fill-current" />
                )
              }
              title={
                isServing
                  ? "Preview active (click to stop)"
                  : "Launch Unified Studio Sandbox"
              }
              className={
                isServing
                  ? "bg-emerald-950/80 border-emerald-800 text-emerald-300 hover:bg-emerald-900/80"
                  : isProvisioning || isLaunchingPreview
                  ? "bg-slate-800 text-slate-400 cursor-wait"
                  : ""
              }
            >
              Preview App
            </Button>

            {(isServing || isProvisioning) && onStopPreview && (
              <Button
                id="btn-studio-preview-stop"
                data-testid="studio-stop-preview-btn"
                type="button"
                variant="danger"
                size="sm"
                onClick={onStopPreview}
                icon={<Square className="w-3 h-3 fill-current" />}
                title="Stop preview sandbox"
              >
                Stop
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Floating / Top Status Badge for Active Job */}
      {activeJob && (
        <div
          id="studio-floating-status-badge"
          className="flex items-center space-x-2 bg-slate-950 px-3 py-1.5 rounded-full border border-indigo-900/60 shadow-md text-xs"
        >
          <Badge id="studio-badge-stage-text" variant="stage">
            {activeJob.stage}
          </Badge>
          <span id="studio-badge-job-detail" className="font-mono text-slate-300 text-[11px] truncate max-w-[150px]">
            {activeJob.id}
          </span>

          {onOpenDrawer && (
            <Button
              id="btn-studio-activity"
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onOpenDrawer()}
              icon={<Activity className="w-3 h-3" />}
              className="px-2 py-0.5 text-[11px] text-indigo-300 hover:text-white bg-indigo-900/40 hover:bg-indigo-800"
              title="Open Agent Activity Drawer"
            >
              Activity
            </Button>
          )}

          <Button
            id="btn-inspect-logs"
            type="button"
            variant="secondary"
            size="sm"
            onClick={onSwitchToConsole}
            icon={<Terminal className="w-3 h-3" />}
            className="px-2 py-0.5 text-[11px] text-slate-400 hover:text-slate-200"
            title="Inspect terminal logs in Console"
          >
            Logs
          </Button>

          {activeJob.status === "RUNNING" && (
            <Button
              id="btn-studio-cancel"
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onCancelJob(activeJob.id)}
              icon={<XCircle className="w-3.5 h-3.5" />}
              className="p-1 text-red-400 hover:text-red-200 hover:bg-red-950"
              title="Cancel running assembly line"
            />
          )}
        </div>
      )}
    </div>
  );
};
