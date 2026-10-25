import React, { useState, useEffect, useMemo } from "react";
import * as api from "../api";
import { useQueryClient } from "@tanstack/react-query";
import { useStudio } from "../context/StudioContext";
import {
  useStudioIssuesQuery,
  useStudioPullRequestQuery,
  useMergePullRequestMutation,
  useRollbackTurnMutation,
  studioQueryKeys,
} from "../hooks/useStudioQueries";
import { Badge } from "../components/ui/Badge";
import { getPullRequestStatus, getPullRequestBadgeConfig } from "../utils";
import { PullRequest, PreviewState, RollbackTarget } from "../types";
import {
  StudioHeader,
  StudioChatPane,
  StudioPreviewPane,
  StudioModals,
  getLatestRollbackTarget,
} from "./studio";

export interface StudioViewProps {
  className?: string;
}

export const StudioView: React.FC<StudioViewProps> = ({ className = "" }) => {
  const {
    repos,
    selectedRepo,
    onSelectRepo,
    onCreateRepo,
    activeJob,
    messages,
    onSendPrompt,
    onRetryTurn,
    onApprovePlan,
    isApproving = false,
    onOpenDrawer,
    isSending = false,
    previewState = null,
    onLaunchPreview,
    onStopPreview,
    onRetryPreview,
    onReconnectPreview,
    refreshKey,
    isLaunchingPreview = false,
    onClearChat,
    isClearingChat = false,
    isChatCleared = false,
    onOpenIssueDrawer,
    onCloseIssueDrawer,
    isIssueDrawerOpen: propIssueDrawerOpen,
    onMergeSuccess,
    branches = [],
    onSelectBranch,
    isSwitchingBranch = false,
  } = useStudio();

  const queryClient = useQueryClient();
  const [isNewAppModalOpen, setIsNewAppModalOpen] = useState<boolean>(false);
  const [isDismissedDisconnected, setIsDismissedDisconnected] = useState<boolean>(false);
  const [isLocalIssueDrawerOpen, setIsLocalIssueDrawerOpen] = useState<boolean>(false);
  const [branchRefreshKey, setBranchRefreshKey] = useState<number>(0);
  const [branchSwitchError, setBranchSwitchError] = useState<string | null>(null);

  const [isPRPopoverOpen, setIsPRPopoverOpen] = useState<boolean>(false);
  const [isConfirmingMerge, setIsConfirmingMerge] = useState<boolean>(false);
  const [popoverMergeError, setPopoverMergeError] = useState<string | null>(null);

  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState<boolean>(false);
  const [targetRollbackTurn, setTargetRollbackTurn] = useState<RollbackTarget | null>(null);
  const [rollbackError, setRollbackError] = useState<string | null>(null);

  const rollbackMutation = useRollbackTurnMutation();
  const isRollingBack = rollbackMutation.isPending;

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => {
        setToast(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const prQuery = useStudioPullRequestQuery(selectedRepo);
  const mergeMutation = useMergePullRequestMutation();

  useEffect(() => {
    setIsPRPopoverOpen(false);
    setIsConfirmingMerge(false);
    setPopoverMergeError(null);
    setIsRollbackModalOpen(false);
    setTargetRollbackTurn(null);
    setRollbackError(null);
  }, [selectedRepo]);

  const pullRequests: PullRequest[] = prQuery.data?.pulls || [];

  const activePR: PullRequest | undefined = (() => {
    if (!pullRequests.length) return undefined;
    if (activeJob?.feature) {
      const match = pullRequests.find(
        (p) =>
          p.head_branch === `factory/${activeJob.feature}` ||
          p.head_branch.endsWith(`/${activeJob.feature}`)
      );
      if (match) return match;
    }
    const openFactoryPR = pullRequests.find(
      (p) => (p.state === "open" || !p.merged) && p.head_branch.startsWith("factory/")
    );
    if (openFactoryPR) return openFactoryPR;
    const openPR = pullRequests.find((p) => p.state === "open" || !p.merged);
    if (openPR) return openPR;
    return pullRequests[0];
  })();

  const prStatus = getPullRequestStatus(activePR);
  const prIsMerged = prStatus === "merged";
  const prHasConflict = prStatus === "conflict";
  const prIsDraft = prStatus === "draft";
  const prIsClosed = prStatus === "closed";

  const isIssueDrawerOpen =
    propIssueDrawerOpen !== undefined ? propIssueDrawerOpen : isLocalIssueDrawerOpen;

  const issuesQuery = useStudioIssuesQuery(selectedRepo);

  // Invalidate branches query cache on repository switch
  useEffect(() => {
    if (selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [selectedRepo, queryClient]);

  // Invalidate branches query cache on job completion
  useEffect(() => {
    if (activeJob?.status === "SUCCESS" && selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [activeJob?.status, selectedRepo, queryClient]);

  const openIssuesCount = (issuesQuery.data?.issues || []).filter((i) => {
    const isClosed = i.state && i.state.toLowerCase() === "closed";
    const isResolved =
      i.status?.toLowerCase() === "resolved" ||
      i.labels?.some((l) => l.toLowerCase() === "factory:resolved");
    return !isClosed && !isResolved;
  }).length;

  const handleOpenIssues = () => {
    if (selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(selectedRepo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
    setIsLocalIssueDrawerOpen(true);
    if (onOpenIssueDrawer) {
      onOpenIssueDrawer();
    }
  };

  const handleCloseIssues = () => {
    if (selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
    setIsLocalIssueDrawerOpen(false);
    if (onCloseIssueDrawer) {
      onCloseIssueDrawer();
    }
  };

  const handlePopoverMerge = async () => {
    if (!activePR || !selectedRepo) return;
    setPopoverMergeError(null);
    try {
      const res = await mergeMutation.mutateAsync({
        repo: selectedRepo,
        pullNumber: activePR.number,
        params: {
          commit_title: `${activePR.title} (#${activePR.number})`,
        },
      });

      queryClient.setQueryData<PreviewState | null>(
        studioQueryKeys.preview(selectedRepo),
        (prev) => {
          if (!prev || prev.status === "IDLE") return prev ?? null;
          return { ...prev, branch: "main" };
        }
      );

      if (onMergeSuccess) {
        onMergeSuccess(res);
      }
      setIsConfirmingMerge(false);
      setIsPRPopoverOpen(false);
    } catch (err: any) {
      setPopoverMergeError(err.message || "Failed to merge pull request");
    }
  };

  const handleMergeSuccess = (res?: any) => {
    queryClient.setQueryData<PreviewState | null>(
      studioQueryKeys.preview(selectedRepo),
      (prev) => {
        if (!prev || prev.status === "IDLE") return prev ?? null;
        return { ...prev, branch: "main" };
      }
    );
    if (onMergeSuccess) {
      onMergeSuccess(res);
    }
  };

  const handleSelectBranch = async (targetBranch: string) => {
    setBranchSwitchError(null);
    if (onSelectBranch) {
      try {
        await onSelectBranch(targetBranch);
        setBranchRefreshKey((prev) => prev + 1);
      } catch (err: any) {
        setBranchSwitchError(err?.message || "Failed to switch preview branch");
        throw err;
      }
    }
  };

  useEffect(() => {
    if (previewState?.status !== "STOPPED") {
      setIsDismissedDisconnected(false);
    }
  }, [previewState?.status, selectedRepo]);

  const isDisconnected = previewState?.status === "STOPPED";
  const isExecutingTurn = Boolean(
    isSending || (activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED"))
  );
  const isServing = previewState?.status === "SERVING";
  const isProvisioning = previewState?.status === "PROVISIONING";

  const handleReconnect = () => {
    if (onReconnectPreview) {
      onReconnectPreview();
    } else if (onLaunchPreview) {
      onLaunchPreview();
    }
  };

  const renderPRControlBadge = () => {
    const config = getPullRequestBadgeConfig(prStatus);
    const testIdStatus = prStatus === "ready_for_review" ? "ready" : prStatus;
    return (
      <Badge
        data-testid={`studio-pr-badge-${testIdStatus}`}
        variant={config.variant}
        className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold ${config.className}`}
      >
        {config.label}
      </Badge>
    );
  };

  const handleSync = async () => {
    if (!selectedRepo || isSyncing || isExecutingTurn) return;
    setIsSyncing(true);
    try {
      const targetBranch = previewState?.branch || undefined;
      const res = await api.syncPreview(selectedRepo, targetBranch);
      const commitStr = res.commit ? ` [${res.commit}]` : "";
      setToast({
        type: "success",
        message: `Preview synchronized with ${res.branch}${commitStr}`,
      });
    } catch (err: any) {
      setToast({
        type: "error",
        message: `${err.message || "Failed to synchronize preview"}. Check Dev Server Logs for details.`,
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const latestRollbackInfo = useMemo(
    () => getLatestRollbackTarget(messages, previewState?.branch, pullRequests),
    [messages, previewState?.branch, pullRequests]
  );
  const latestRollbackableMessageId = latestRollbackInfo.target?.messageId || null;
  const isLatestTurnMerged = latestRollbackInfo.isMerged;

  const handleOpenRollback = (turnInfo?: RollbackTarget) => {
    setRollbackError(null);
    if (turnInfo) {
      setTargetRollbackTurn(turnInfo);
    } else if (latestRollbackInfo.target) {
      setTargetRollbackTurn(latestRollbackInfo.target);
    } else {
      return;
    }
    setIsRollbackModalOpen(true);
  };

  const handleConfirmRollback = async () => {
    if (!selectedRepo) return;
    setRollbackError(null);
    try {
      const res = await rollbackMutation.mutateAsync({
        repo: selectedRepo,
        message_id: targetRollbackTurn?.messageId,
        branch: targetRollbackTurn?.branch || previewState?.branch || undefined,
      });
      setIsRollbackModalOpen(false);
      setToast({
        type: "success",
        message: res.message || `Rolled back turn on ${res.branch}.`,
      });
    } catch (err: any) {
      const msg = err.message || "Failed to roll back turn.";
      setRollbackError(msg);
      setToast({
        type: "error",
        message: msg,
      });
    }
  };

  return (
    <div id="studio-view" className={`flex flex-col h-[calc(100vh-4.25rem)] overflow-hidden ${className}`}>
      <StudioHeader
        repos={repos}
        selectedRepo={selectedRepo}
        onSelectRepo={onSelectRepo}
        onOpenNewAppModal={() => setIsNewAppModalOpen(true)}
        openIssuesCount={openIssuesCount}
        onOpenIssues={handleOpenIssues}
        activePR={activePR}
        renderPRControlBadge={renderPRControlBadge}
        isPRPopoverOpen={isPRPopoverOpen}
        onTogglePRPopover={() => {
          setIsPRPopoverOpen((prev) => !prev);
          setIsConfirmingMerge(false);
          setPopoverMergeError(null);
        }}
        isConfirmingMerge={isConfirmingMerge}
        onSetIsConfirmingMerge={setIsConfirmingMerge}
        onPopoverMerge={handlePopoverMerge}
        isMerging={mergeMutation.isPending}
        popoverMergeError={popoverMergeError}
        prIsDraft={prIsDraft}
        prHasConflict={prHasConflict}
        prIsMerged={prIsMerged}
        prIsClosed={prIsClosed}
        isExecutingTurn={isExecutingTurn}
        previewState={previewState}
        isServing={isServing}
        isProvisioning={isProvisioning}
        isLaunchingPreview={isLaunchingPreview}
        onLaunchPreview={onLaunchPreview}
        onStopPreview={onStopPreview}
      />

      {/* Main Split Layout: Chat Conversation Left, Live Preview Right */}
      <div className="flex-1 flex overflow-hidden">
        <StudioChatPane
          messages={messages}
          isChatCleared={isChatCleared}
          selectedRepo={selectedRepo}
          isExecutingTurn={isExecutingTurn}
          isDisconnected={isDisconnected}
          activeJob={activeJob}
          previewState={previewState}
          latestRollbackableMessageId={latestRollbackableMessageId}
          latestRollbackInfo={latestRollbackInfo}
          isRollingBack={isRollingBack}
          isLatestTurnMerged={isLatestTurnMerged}
          onSendPrompt={onSendPrompt}
          onClearChat={onClearChat}
          isClearingChat={isClearingChat}
          onRetryTurn={onRetryTurn}
          onApprovePlan={onApprovePlan}
          isApproving={isApproving}
          onOpenDrawer={onOpenDrawer}
          onMergeSuccess={handleMergeSuccess}
          onOpenRollback={handleOpenRollback}
        />

        <StudioPreviewPane
          repo={selectedRepo}
          previewState={previewState}
          branches={branches}
          onSelectBranch={handleSelectBranch}
          isSwitchingBranch={isSwitchingBranch}
          activeJob={activeJob}
          onLaunchPreview={onLaunchPreview}
          onStopPreview={onStopPreview}
          onRetryPreview={onRetryPreview}
          onReconnectPreview={handleReconnect}
          refreshKey={refreshKey || 0}
          branchRefreshKey={branchRefreshKey}
          isLaunchingPreview={isLaunchingPreview}
          isSyncing={isSyncing}
          onSync={handleSync}
          isExecutingTurn={isExecutingTurn}
        />
      </div>

      <StudioModals
        isNewAppModalOpen={isNewAppModalOpen}
        onCloseNewAppModal={() => setIsNewAppModalOpen(false)}
        onCreateRepo={onCreateRepo}
        isRollbackModalOpen={isRollbackModalOpen}
        onCloseRollbackModal={() => {
          if (!isRollingBack) {
            setIsRollbackModalOpen(false);
            setRollbackError(null);
          }
        }}
        onConfirmRollback={handleConfirmRollback}
        isRollingBack={isRollingBack}
        selectedRepo={selectedRepo}
        targetRollbackTurn={targetRollbackTurn}
        previewBranch={previewState?.branch || null}
        rollbackError={rollbackError}
        isDisconnected={isDisconnected}
        isDismissedDisconnected={isDismissedDisconnected}
        onReconnect={handleReconnect}
        onDismissDisconnected={() => setIsDismissedDisconnected(true)}
        isLaunchingPreview={isLaunchingPreview}
        isIssueDrawerOpen={isIssueDrawerOpen}
        onCloseIssues={handleCloseIssues}
        branchSwitchError={branchSwitchError}
        onDismissBranchSwitchError={() => setBranchSwitchError(null)}
        toast={toast}
        onDismissToast={() => setToast(null)}
      />
    </div>
  );
};
