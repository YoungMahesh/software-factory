import React from "react";
import { LivePreview } from "../../components/LivePreview";
import { PreviewState, RollbackTarget } from "../../types";

export interface StudioPreviewPaneProps {
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
    <div className="flex-1 bg-soft-stone/40 p-4 overflow-hidden">
      <LivePreview
        previewUrl={(previewState as any)?.preview_url || (previewState as any)?.url || activeJob?.preview_url || null}
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
        onRollbackLastTurn={latestRollbackInfo.target ? () => onOpenRollback() : undefined}
        isRollingBack={isRollingBack}
        isRollbackDisabled={isLatestTurnMerged}
        rollbackDisabledReason={
          isLatestTurnMerged
            ? "Cannot roll back turn for a merged pull request"
            : undefined
        }
      />
    </div>
  );
};
