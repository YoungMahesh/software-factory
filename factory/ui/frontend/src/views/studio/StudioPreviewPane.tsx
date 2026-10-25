import React, { useState } from "react";
import { Play, FolderTree, GitCompare } from "lucide-react";
import { LivePreview } from "../../components/LivePreview";
import { InStudioCodeViewer } from "../../components/code-viewer";
import { PreMergeDiffViewer } from "../../components/diff-viewer";
import { CanvasViewMode, PreviewState } from "../../types";

export interface StudioPreviewPaneProps {
  repo?: string;
  viewMode?: CanvasViewMode;
  onViewModeChange?: (mode: CanvasViewMode) => void;
  previewState: PreviewState | null;
  branches: string[];
  onSelectBranch: (branch: string) => Promise<void> | void;
  isSwitchingBranch: boolean;
  activeJob: any;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview?: () => void;
  refreshKey: number;
  branchRefreshKey: number;
  isLaunchingPreview: boolean;
  isSyncing: boolean;
  onSync: () => void;
  isExecutingTurn: boolean;
}

export const StudioPreviewPane: React.FC<StudioPreviewPaneProps> = ({
  repo,
  viewMode: propViewMode,
  onViewModeChange,
  previewState,
  branches,
  onSelectBranch,
  isSwitchingBranch,
  activeJob,
  onLaunchPreview,
  onStopPreview,
  onRetryPreview,
  onReconnectPreview,
  refreshKey,
  branchRefreshKey,
  isLaunchingPreview,
  isSyncing,
  onSync,
  isExecutingTurn,
}) => {
  const [internalViewMode, setInternalViewMode] = useState<CanvasViewMode>("preview");
  const currentViewMode = propViewMode !== undefined ? propViewMode : internalViewMode;

  const handleSelectMode = (mode: CanvasViewMode) => {
    setInternalViewMode(mode);
    if (onViewModeChange) {
      onViewModeChange(mode);
    }
  };

  const activeBranch = previewState?.branch || (branches.length > 0 ? branches[0] : "main");

  return (
    <div className="flex-1 bg-soft-stone/40 p-4 overflow-hidden flex flex-col gap-3">
      {/* Top Canvas View Mode Switcher Header */}
      <div className="flex items-center justify-between shrink-0">
        <div
          data-testid="canvas-view-mode-switcher"
          className="inline-flex items-center p-1 rounded-pill bg-white/90 border border-hairline shadow-2xs backdrop-blur-xs space-x-1"
        >
          <button
            data-testid="canvas-view-mode-preview"
            type="button"
            onClick={() => handleSelectMode("preview")}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              currentViewMode === "preview"
                ? "bg-primary text-white shadow-xs"
                : "text-slate-600 hover:text-ink hover:bg-soft-stone/50"
            }`}
          >
            <Play className="w-3.5 h-3.5" />
            <span>Live Preview</span>
          </button>

          <button
            data-testid="canvas-view-mode-files"
            type="button"
            onClick={() => handleSelectMode("files")}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              currentViewMode === "files"
                ? "bg-primary text-white shadow-xs"
                : "text-slate-600 hover:text-ink hover:bg-soft-stone/50"
            }`}
          >
            <FolderTree className="w-3.5 h-3.5" />
            <span>Files &amp; Code</span>
          </button>

          <button
            data-testid="canvas-view-mode-diff"
            type="button"
            onClick={() => handleSelectMode("diff")}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              currentViewMode === "diff"
                ? "bg-primary text-white shadow-xs"
                : "text-slate-600 hover:text-ink hover:bg-soft-stone/50"
            }`}
          >
            <GitCompare className="w-3.5 h-3.5" />
            <span>Git Diff</span>
          </button>
        </div>

        {/* Repository & Branch Indicator (visible in Files or Diff mode) */}
        {repo && currentViewMode !== "preview" && (
          <div className="text-[11px] font-mono text-slate-500 hidden sm:flex items-center space-x-2">
            <span className="font-semibold text-slate-700">{repo}</span>
            <span>•</span>
            <span className="text-slate-500">{activeBranch}</span>
          </div>
        )}
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {currentViewMode === "preview" ? (
          <LivePreview
            previewUrl={
              (previewState as any)?.preview_url ||
              (previewState as any)?.url ||
              activeJob?.preview_url ||
              null
            }
            status={previewState?.status || (activeJob?.dev ? "SERVING" : "IDLE")}
            stage={(previewState as any)?.stage}
            branch={previewState?.branch}
            branches={branches}
            availableBranches={branches}
            onSelectBranch={onSelectBranch}
            onSwitchBranch={onSelectBranch}
            isSwitchingBranch={isSwitchingBranch}
            isConcurrencyLocked={isExecutingTurn}
            isJobActive={isExecutingTurn}
            lockTooltip={
              isExecutingTurn
                ? "Branch switching is locked while an assembly line job is actively running."
                : undefined
            }
            logs={previewState?.logs || []}
            errorMessage={previewState?.error_message}
            onLaunchPreview={onLaunchPreview}
            onStopPreview={onStopPreview}
            onRetryPreview={onRetryPreview}
            onReconnectPreview={onReconnectPreview}
            refreshKey={(refreshKey || 0) + branchRefreshKey}
            isLaunching={isLaunchingPreview}
            isSyncing={isSyncing}
            onSync={onSync}
          />
        ) : currentViewMode === "files" ? (
          <InStudioCodeViewer repo={repo || ""} branch={activeBranch} />
        ) : (
          <PreMergeDiffViewer repo={repo || ""} branch={activeBranch} />
        )}
      </div>
    </div>
  );
};
