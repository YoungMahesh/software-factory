import React, { useState, useEffect } from "react";
import {
  RotateCw,
  Terminal,
  ChevronDown,
} from "lucide-react";
import { ViewportMode, PreviewStatus, PreviewStage } from "../types";
import { TerminalLogViewer } from "./TerminalLogViewer";
import { LivePreviewToolbar } from "./live-preview/LivePreviewToolbar";
import { LivePreviewFrame } from "./live-preview/LivePreviewFrame";
import { LivePreviewOverlay } from "./live-preview/LivePreviewOverlay";

export interface LivePreviewProps {
  previewUrl?: string | null;
  status?: PreviewStatus;
  stage?: PreviewStage;
  branch?: string | null;
  branches?: string[];
  availableBranches?: string[];
  onSelectBranch?: (branch: string) => Promise<void> | void;
  onSwitchBranch?: (branch: string) => Promise<void> | void;
  isSwitchingBranch?: boolean;
  isConcurrencyLocked?: boolean;
  isJobActive?: boolean;
  lockTooltip?: string;
  logs?: string[];
  errorMessage?: string | null;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview?: () => void;
  onRefresh?: () => void;
  refreshKey?: number;
  isLaunching?: boolean;
  isSyncing?: boolean;
  onSync?: () => void;
  onRollbackLastTurn?: () => void;
  isRollingBack?: boolean;
  isRollbackDisabled?: boolean;
  rollbackDisabledReason?: string;
}

export const LivePreview: React.FC<LivePreviewProps> = ({
  previewUrl,
  status = "IDLE",
  stage = "IDLE",
  branch = null,
  branches = [],
  availableBranches: availableBranchesProp,
  onSelectBranch,
  onSwitchBranch,
  isSwitchingBranch = false,
  isConcurrencyLocked = false,
  isJobActive = false,
  lockTooltip,
  logs = [],
  errorMessage = null,
  onLaunchPreview,
  onStopPreview,
  onRetryPreview,
  onReconnectPreview,
  onRefresh,
  refreshKey,
  isLaunching = false,
  isSyncing = false,
  onSync,
  onRollbackLastTurn,
  isRollingBack = false,
  isRollbackDisabled = false,
  rollbackDisabledReason,
}) => {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [isLogsDrawerOpen, setIsLogsDrawerOpen] = useState<boolean>(false);

  // Auto-expand logs drawer on failure
  useEffect(() => {
    if (status === "FAILED") {
      setIsLogsDrawerOpen(true);
    }
  }, [status]);

  // Synchronize external refreshKey signal (e.g. from SSE preview_refresh)
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      setReloadKey((prev) => prev + 1);
    }
  }, [refreshKey]);

  const handleReload = () => {
    setReloadKey((prev) => prev + 1);
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleRetry = () => {
    if (onRetryPreview) {
      onRetryPreview();
    } else if (onLaunchPreview) {
      onLaunchPreview();
    }
  };

  const isLivePreviewActive = Boolean(
    previewUrl &&
    status !== "PROVISIONING" &&
    status !== "FAILED" &&
    status !== "STOPPED"
  );

  return (
    <div className="flex flex-col h-full bg-white rounded-[22px] border border-hairline overflow-hidden shadow-sm">
      {/* Top control bar */}
      <LivePreviewToolbar
        viewport={viewport}
        onViewportChange={setViewport}
        previewUrl={previewUrl}
        status={status}
        branch={branch}
        branches={branches}
        availableBranchesProp={availableBranchesProp}
        onSelectBranch={onSelectBranch}
        onSwitchBranch={onSwitchBranch}
        isSwitchingBranch={isSwitchingBranch}
        isConcurrencyLocked={isConcurrencyLocked}
        isJobActive={isJobActive}
        lockTooltip={lockTooltip}
        onReload={handleReload}
        onRefresh={onRefresh}
        isSyncing={isSyncing}
        onSync={onSync}
        onRollbackLastTurn={onRollbackLastTurn}
        isRollingBack={isRollingBack}
        isRollbackDisabled={isRollbackDisabled}
        rollbackDisabledReason={rollbackDisabledReason}
        isLogsDrawerOpen={isLogsDrawerOpen}
        onToggleLogsDrawer={() => setIsLogsDrawerOpen((prev) => !prev)}
        logsCount={logs.length}
        onStopPreview={onStopPreview}
      />

      {/* Frame Container */}
      <div
        id="preview-frame-wrapper"
        className="flex-1 flex flex-col items-center justify-center bg-soft-stone/30 p-4 overflow-auto min-h-0"
      >
        {isLivePreviewActive ? (
          <LivePreviewFrame
            previewUrl={previewUrl!}
            viewport={viewport}
            reloadKey={reloadKey}
          />
        ) : (
          <LivePreviewOverlay
            status={status}
            stage={stage}
            errorMessage={errorMessage}
            onRetry={handleRetry}
            onReconnectPreview={onReconnectPreview}
            onLaunchPreview={onLaunchPreview}
            isLaunching={isLaunching}
          />
        )}
      </div>

      {/* Collapsible Dev Server Logs Terminal Drawer */}
      {isLogsDrawerOpen && (
        <div
          data-testid="dev-server-logs-drawer"
          id="dev-server-logs-drawer"
          className="h-64 border-t border-hairline bg-primary flex flex-col shrink-0 overflow-hidden"
        >
          {/* Drawer Header */}
          <div className="flex items-center justify-between px-3.5 py-2 bg-primary border-b border-white/10 text-xs shrink-0 text-white">
            <div className="flex items-center space-x-2 text-slate-300">
              <Terminal className="w-3.5 h-3.5 text-coral" />
              <span className="font-semibold text-white text-xs">Dev Server Logs</span>
              <span id="dev-logs-line-count" className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white/10 text-slate-300">
                {logs.length} lines
              </span>
            </div>

            <div className="flex items-center space-x-2">
              {status === "FAILED" && (
                <button
                  data-testid="retry-preview-btn"
                  id="btn-retry-in-drawer"
                  type="button"
                  onClick={handleRetry}
                  className="flex items-center space-x-1 px-3 py-1 rounded-pill text-xs font-semibold bg-white hover:bg-soft-stone text-primary shadow-sm transition-colors cursor-pointer"
                >
                  <RotateCw className="w-3 h-3" />
                  <span>Retry</span>
                </button>
              )}
              <button
                id="btn-close-logs-drawer"
                type="button"
                onClick={() => setIsLogsDrawerOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-white transition-colors cursor-pointer"
                title="Close terminal drawer"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-hidden">
            <TerminalLogViewer logs={logs} />
          </div>
        </div>
      )}
    </div>
  );
};
