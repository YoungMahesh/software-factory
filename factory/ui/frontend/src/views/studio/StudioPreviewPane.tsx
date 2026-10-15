import React from "react";
import { LivePreview } from "../../components/LivePreview";
import { PreviewState, RollbackTarget } from "../../types";

export interface StudioPreviewPaneProps {
  previewState: PreviewState | null;
  branches: string[];
  onSelectBranch: (branch: string) => Promise<void>;
  isSwitchingBranch: boolean;
  activeJob: any;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview: () => void;
  refreshKey: number;
  branchRefreshKey: number;
  isLaunchingPreview: boolean;
  isSyncing: boolean;
  onSync: () => void;
  isExecutingTurn: boolean;
  latestRollbackInfo: { target: RollbackTarget | null; isMerged: boolean };
  onOpenRollback: (turnInfo?: RollbackTarget) => void;
  isRollingBack: boolean;
  isLatestTurnMerged: boolean;
}

export const StudioPreviewPane: React.FC<StudioPreviewPaneProps> = ({
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
  latestRollbackInfo,
  onOpenRollback,
  isRollingBack,
  isLatestTurnMerged,
}) => {
  return (
    <div className="flex-1 bg-slate-950 p-4 overflow-hidden">
      <LivePreview
        previewUrl={previewState?.preview_url || null}
        status={previewState?.status || "IDLE"}
        stage={previewState?.status === "PROVISIONING" ? previewState.stage : "IDLE"}
        branch={previewState?.branch || null}
        branches={branches}
        onSelectBranch={onSelectBranch}
        isSwitchingBranch={isSwitchingBranch}
        isConcurrencyLocked={Boolean(activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED"))}
        logs={previewState?.logs || []}
        errorMessage={previewState?.error_message || null}
        onLaunchPreview={onLaunchPreview}
        onStopPreview={onStopPreview}
        onRetryPreview={onRetryPreview || onLaunchPreview}
        onReconnectPreview={onReconnectPreview}
        refreshKey={(refreshKey || 0) + branchRefreshKey}
        isLaunching={isLaunchingPreview}
        isSyncing={isSyncing}
        onSync={onSync}
        isJobActive={isExecutingTurn}
        onRollbackLastTurn={latestRollbackInfo.target ? () => onOpenRollback() : undefined}
        isRollingBack={isRollingBack}
        isRollbackDisabled={isLatestTurnMerged}
        rollbackDisabledReason={isLatestTurnMerged ? "Cannot roll back turn for a merged pull request" : undefined}
      />
    </div>
  );
};
