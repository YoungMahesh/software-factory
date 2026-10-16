import React, { useState, useMemo } from "react";
import {
  Monitor,
  Tablet,
  Smartphone,
  RotateCw,
  ExternalLink,
  Globe,
  Square,
  Loader2,
  Terminal,
  RefreshCw,
  Lock,
  RotateCcw,
} from "lucide-react";
import { ViewportMode, PreviewStatus } from "../../types";
import { LivePreviewBranchSelector } from "./LivePreviewBranchSelector";

export interface LivePreviewToolbarProps {
  viewport: ViewportMode;
  onViewportChange: (viewport: ViewportMode) => void;
  previewUrl?: string | null;
  status?: PreviewStatus;
  branch?: string | null;
  branches?: string[];
  availableBranchesProp?: string[];
  onSelectBranch?: (branch: string) => Promise<void> | void;
  onSwitchBranch?: (branch: string) => Promise<void> | void;
  isSwitchingBranch?: boolean;
  isConcurrencyLocked?: boolean;
  isJobActive?: boolean;
  lockTooltip?: string;
  onReload: () => void;
  onRefresh?: () => void;
  isSyncing?: boolean;
  onSync?: () => void;
  onRollbackLastTurn?: () => void;
  isRollingBack?: boolean;
  isRollbackDisabled?: boolean;
  rollbackDisabledReason?: string;
  isLogsDrawerOpen: boolean;
  onToggleLogsDrawer: () => void;
  logsCount: number;
  onStopPreview?: () => void;
}

export const LivePreviewToolbar: React.FC<LivePreviewToolbarProps> = ({
  viewport,
  onViewportChange,
  previewUrl,
  status = "IDLE",
  branch = null,
  branches = [],
  availableBranchesProp,
  onSelectBranch,
  onSwitchBranch,
  isSwitchingBranch = false,
  isConcurrencyLocked = false,
  isJobActive = false,
  lockTooltip,
  onReload,
  isSyncing = false,
  onSync,
  onRollbackLastTurn,
  isRollingBack = false,
  isRollbackDisabled = false,
  rollbackDisabledReason,
  isLogsDrawerOpen,
  onToggleLogsDrawer,
  logsCount,
  onStopPreview,
}) => {
  const [isLocalSwitching, setIsLocalSwitching] = useState<boolean>(false);

  const switchBranchFn = onSwitchBranch || onSelectBranch;
  const isLocked = Boolean(isJobActive || isConcurrencyLocked);
  const candidateBranches =
    availableBranchesProp && availableBranchesProp.length > 0
      ? availableBranchesProp
      : branches;
  const currentBranch =
    branch || (candidateBranches.length > 0 ? candidateBranches[0] : null);
  const isSwitching = isSwitchingBranch || isLocalSwitching;
  const isInteractive = Boolean(
    switchBranchFn ||
      candidateBranches.length > 0 ||
      isSwitching ||
      isLocked
  );

  // Build sorted branch list: active branch first, then main, then others alphabetically
  const availableBranches = useMemo(() => {
    const list = Array.from(
      new Set(
        candidateBranches.length > 0
          ? candidateBranches
          : currentBranch
          ? [currentBranch]
          : []
      )
    );
    return list.sort((a, b) => {
      if (a === currentBranch) return -1;
      if (b === currentBranch) return 1;
      if (a === "main") return -1;
      if (b === "main") return 1;
      return a.localeCompare(b);
    });
  }, [candidateBranches, currentBranch]);

  const handleBranchSelect = async (targetBranch: string) => {
    if (targetBranch === currentBranch && !isSwitching) return;
    setIsLocalSwitching(true);
    try {
      if (switchBranchFn) {
        await switchBranchFn(targetBranch);
      }
      onReload();
    } finally {
      setIsLocalSwitching(false);
    }
  };

  return (
    <div className="flex items-center justify-between px-4 py-2.5 bg-primary border-b border-white/10 text-slate-200 shrink-0">
      {/* Responsive viewport controls */}
      <div className="flex items-center space-x-1 bg-cohere-black/60 p-1 rounded-pill border border-white/10">
        <button
          data-testid="viewport-desktop"
          id="btn-viewport-desktop"
          type="button"
          onClick={() => onViewportChange("desktop")}
          className={`p-1.5 rounded-pill text-xs transition-colors cursor-pointer ${
            viewport === "desktop"
              ? "bg-white text-primary shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
          title="Desktop view"
        >
          <Monitor className="w-3.5 h-3.5" />
        </button>
        <button
          data-testid="viewport-tablet"
          id="btn-viewport-tablet"
          type="button"
          onClick={() => onViewportChange("tablet")}
          className={`p-1.5 rounded-pill text-xs transition-colors cursor-pointer ${
            viewport === "tablet"
              ? "bg-white text-primary shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
          title="Tablet view (768px)"
        >
          <Tablet className="w-3.5 h-3.5" />
        </button>
        <button
          data-testid="viewport-mobile"
          id="btn-viewport-mobile"
          type="button"
          onClick={() => onViewportChange("mobile")}
          className={`p-1.5 rounded-pill text-xs transition-colors cursor-pointer ${
            viewport === "mobile"
              ? "bg-white text-primary shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
          title="Mobile view (375px)"
        >
          <Smartphone className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Active Branch Selector & Sync / Rollback Actions */}
      <div className="flex items-center space-x-1.5 shrink-0">
        <LivePreviewBranchSelector
          currentBranch={currentBranch}
          availableBranches={availableBranches}
          isInteractive={isInteractive}
          isLocked={isLocked}
          isSwitching={isSwitching}
          lockTooltip={lockTooltip}
          onSelectBranch={handleBranchSelect}
        />

        {/* Trunk Synchronization Action Button */}
        {onSync && (
          <button
            data-testid="sync-preview-btn"
            id="btn-preview-sync"
            type="button"
            onClick={onSync}
            disabled={isSyncing || isLocked || !onSync}
            className={`p-1.5 rounded-pill border text-xs transition-colors flex items-center justify-center shrink-0 cursor-pointer ${
              isLocked
                ? "bg-cohere-black/40 border-white/10 text-muted cursor-not-allowed"
                : isSyncing
                ? "bg-white/10 border-white/30 text-white cursor-wait"
                : "bg-transparent border-white/20 text-slate-300 hover:text-white hover:bg-white/10"
            } disabled:opacity-50`}
            title={
              isLocked
                ? "Cannot synchronize while an assembly line job is active"
                : isSyncing
                ? "Synchronizing with remote..."
                : "Pull latest from remote"
            }
            aria-label={
              isLocked
                ? "Cannot synchronize while an assembly line job is active"
                : isSyncing
                ? "Synchronizing with remote..."
                : "Pull latest from remote"
            }
          >
            {isLocked ? (
              <Lock className="w-3 h-3 text-amber-500/80" data-testid="sync-lock-icon" />
            ) : isSyncing ? (
              <Loader2 className="w-3 h-3 animate-spin text-white" data-testid="sync-loading-spinner" />
            ) : (
              <RefreshCw className="w-3 h-3 text-white" data-testid="sync-icon" />
            )}
          </button>
        )}

        {/* Undo Last Turn Action Button */}
        {onRollbackLastTurn && (
          <button
            data-testid="preview-rollback-btn"
            id="btn-preview-rollback"
            type="button"
            onClick={onRollbackLastTurn}
            disabled={isLocked || isRollingBack || isSyncing || isSwitching || isRollbackDisabled}
            className={`p-1.5 rounded-pill border text-xs transition-colors flex items-center justify-center shrink-0 cursor-pointer ${
              isLocked || isSyncing || isSwitching || isRollbackDisabled
                ? "bg-cohere-black/40 border-white/10 text-muted cursor-not-allowed"
                : isRollingBack
                ? "bg-white/10 border-white/30 text-white cursor-wait"
                : "bg-transparent border-white/20 text-slate-300 hover:text-white hover:bg-white/10"
            } disabled:opacity-50`}
            title={
              isLocked
                ? "Cannot roll back turn while job is active"
                : rollbackDisabledReason ||
                  (isRollingBack ? "Rolling back last turn..." : "Roll Back Last Turn")
            }
            aria-label="Roll Back Last Turn"
          >
            {isRollingBack ? (
              <Loader2 className="w-3 h-3 animate-spin text-white" data-testid="rollback-loading-spinner" />
            ) : isLocked || isRollbackDisabled ? (
              <Lock className="w-3 h-3 text-muted" data-testid="rollback-lock-icon" />
            ) : (
              <RotateCcw className="w-3 h-3 text-coral" data-testid="rollback-icon" />
            )}
          </button>
        )}
      </div>

      {/* URL Address Bar */}
      <div className="flex-1 max-w-md mx-3">
        <div className="flex items-center px-3.5 py-1 bg-cohere-black/60 rounded-pill border border-white/10 text-xs font-mono text-slate-300 truncate">
          <Globe className="w-3 h-3 text-muted mr-2 shrink-0" />
          <span id="preview-url-display" className="truncate text-[11px] text-slate-300">
            {previewUrl ||
              (status === "PROVISIONING"
                ? "Provisioning sandbox tunnel..."
                : status === "FAILED"
                ? "Startup failed"
                : "Waiting for live preview...")}
          </span>
        </div>
      </div>

      {/* Actions: Dev Logs Toggle, Reload, External, & Stop */}
      <div className="flex items-center space-x-1.5">
        {/* Dev Server Logs Drawer Toggle */}
        <button
          data-testid="toggle-dev-logs-btn"
          id="btn-toggle-dev-logs"
          type="button"
          onClick={onToggleLogsDrawer}
          className={`p-1.5 rounded-pill text-xs transition-colors flex items-center space-x-1 cursor-pointer ${
            isLogsDrawerOpen
              ? "bg-white text-primary shadow-sm"
              : "text-slate-400 hover:text-white hover:bg-white/10"
          }`}
          title="Toggle Dev Server Logs Drawer"
        >
          <Terminal className="w-3.5 h-3.5" />
          {logsCount > 0 && (
            <span className="text-[10px] font-mono opacity-80">{logsCount}</span>
          )}
        </button>

        <button
          data-testid="reload-preview-btn"
          id="btn-preview-reload"
          type="button"
          onClick={onReload}
          disabled={!previewUrl}
          className="flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs text-slate-300 hover:text-white hover:bg-white/10 disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer"
          title="Refresh preview"
          aria-label="Refresh"
        >
          <RotateCw className="w-3.5 h-3.5" />
          <span data-testid="refresh-preview-btn" className="font-medium">Refresh</span>
        </button>

        {previewUrl && (
          <a
            id="preview-open-link"
            href={previewUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 rounded-pill text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            title="Open in new window"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}

        {onStopPreview && (status === "SERVING" || status === "PROVISIONING") && (
          <button
            data-testid="stop-preview-btn"
            id="btn-preview-stop"
            type="button"
            onClick={onStopPreview}
            className="flex items-center space-x-1 px-3 py-1 rounded-pill text-xs font-semibold bg-transparent border border-coral text-coral hover:bg-coral/10 shadow-sm transition-colors cursor-pointer"
            title="Stop preview sandbox"
          >
            <Square className="w-3 h-3 fill-current" />
            <span>Stop</span>
          </button>
        )}
      </div>
    </div>
  );
};
