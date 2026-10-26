import React, { useState } from "react";
import {
  ExternalLink,
  CheckCircle2,
  GitMerge,
  AlertTriangle,
  ShieldCheck,
  RotateCcw,
  Lock,
} from "lucide-react";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { VisualQABadge } from "./VisualQABadge";
import { VisualQAThumbnail } from "./VisualQAThumbnail";
import { VisualQAModal } from "./VisualQAModal";
import { DeliveryGateHeader } from "./DeliveryGateHeader";
import { DeliveryGateConfirmation } from "./DeliveryGateConfirmation";
import { DeliveryGateData, PullRequest, VisualQaTelemetry } from "../types";
import {
  useStudioPullRequestQuery,
  useMergePullRequestMutation,
  useMarkPullRequestReadyMutation,
  useVisualQaQuery,
} from "../hooks/useStudioQueries";
import { getPullRequestStatus, getPullRequestBadgeConfig } from "../utils";

export interface DeliveryGateCardProps {
  repo: string;
  data: DeliveryGateData & { reverted?: boolean; [key: string]: any };
  activeJobRunning?: boolean;
  onMergeSuccess?: (result: any) => void;
  onRollbackTurn?: (data?: DeliveryGateData) => void;
  isRollingBack?: boolean;
  isReverted?: boolean;
  className?: string;
}

export const DeliveryGateCard: React.FC<DeliveryGateCardProps> = ({
  repo,
  data,
  activeJobRunning = false,
  onMergeSuccess,
  onRollbackTurn,
  isRollingBack = false,
  isReverted: isRevertedProp,
  className = "",
}) => {
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [isVqaModalOpen, setIsVqaModalOpen] = useState<boolean>(false);
  const [selectedViewport, setSelectedViewport] = useState<"desktop" | "mobile">("desktop");
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [markReadyError, setMarkReadyError] = useState<string | null>(null);

  const prQuery = useStudioPullRequestQuery(repo);
  const mergeMutation = useMergePullRequestMutation();
  const markReadyMutation = useMarkPullRequestReadyMutation();

  const pullNumber =
    data.pull_number ||
    data.pull_request?.number ||
    data.pull_request_number ||
    data.pullRequestNumber;
  const livePR: PullRequest | undefined = prQuery.data?.pulls?.find(
    (p) => p.number === pullNumber
  );

  const pr: PullRequest | undefined = livePR || data.pull_request;
  const branchName = pr?.head_branch || data.branch;

  const visualQaQuery = useVisualQaQuery(repo, branchName, data.visual_qa);
  const visualQa: VisualQaTelemetry | undefined = visualQaQuery.data ?? data.visual_qa;

  const status = getPullRequestStatus(pr, data);
  const isMerged = status === "merged";
  const hasConflict = status === "conflict";
  const isDraft = status === "draft";
  const isClosed = status === "closed";
  const isReverted = Boolean(isRevertedProp || data.reverted);

  const isTestPassed =
    !data.test_verdict ||
    data.test_verdict.toLowerCase().includes("pass") ||
    data.test_verdict.toLowerCase().includes("success");

  const testVerdictTitle = data.test_verdict
    ? data.test_verdict === "deterministic_tests_passed" || data.test_verdict === "passed"
      ? "Deterministic Tests Passing"
      : data.test_verdict.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "Deterministic Tests Passing";

  const hasVisualQaFailure = Boolean(
    visualQa &&
      (visualQa.passed === false ||
        visualQa.status === "failed" ||
        (visualQa.errors && visualQa.errors.length > 0) ||
        visualQa.cleanCanvas === false)
  );

  const resolvedIssues: string[] = (() => {
    if (data.resolved_issues && data.resolved_issues.length > 0) {
      return data.resolved_issues.map((i) => String(i));
    }
    if (pr?.body) {
      const matches = pr.body.match(/Fixes\s+(#\d+)/gi);
      if (matches) {
        return matches.map((m) => m.replace(/Fixes\s+/i, ""));
      }
    }
    return [];
  })();

  const handleConfirmMerge = async () => {
    if (!pullNumber) {
      setMergeError("Cannot merge: Pull request number could not be resolved.");
      return;
    }
    setMergeError(null);
    try {
      const res = await mergeMutation.mutateAsync({
        repo,
        pullNumber,
        params: {
          commit_title: data.commit_title || (pr ? `${pr.title} (#${pullNumber})` : undefined),
          commit_message: data.commit_message,
        },
      });
      setIsConfirming(false);
      if (onMergeSuccess) {
        onMergeSuccess(res);
      }
    } catch (err: any) {
      setMergeError(err.message || "Failed to squash merge pull request.");
    }
  };

  const handleMarkReadyForReview = async () => {
    if (!pullNumber) {
      setMarkReadyError("Cannot mark ready for review: Pull request number could not be resolved.");
      return;
    }
    setMarkReadyError(null);
    try {
      await markReadyMutation.mutateAsync({ repo, pullNumber });
    } catch (err: any) {
      setMarkReadyError(err.message || "Failed to mark pull request ready for review.");
    }
  };

  const getStatusBadge = () => {
    const config = getPullRequestBadgeConfig(status);
    return (
      <Badge
        data-testid="pr-status-badge"
        variant={config.variant}
        className={config.className}
      >
        {config.label}
      </Badge>
    );
  };

  const isMergeDisabled =
    !pullNumber ||
    isDraft ||
    activeJobRunning ||
    hasConflict ||
    hasVisualQaFailure ||
    isMerged ||
    isClosed ||
    isReverted ||
    isRollingBack;

  return (
    <div
      data-testid="delivery-gate-card"
      className={`rounded-xl border ${
        isReverted
          ? "border-white/10 bg-primary/80 opacity-75 text-slate-300"
          : "border-white/20 bg-primary text-white"
      } p-4 space-y-3.5 shadow-sm text-xs ${className}`}
    >
      {/* Header: Title & Badges */}
      <DeliveryGateHeader
        pr={pr}
        pullNumber={pullNumber}
        isReverted={isReverted}
        statusBadge={getStatusBadge()}
      />

      {/* Resolved Work Items Checklist */}
      {resolvedIssues.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Resolved Work Items
          </div>
          <div className="flex flex-wrap gap-2">
            {resolvedIssues.map((issue, idx) => (
              <span
                key={idx}
                className="flex items-center space-x-1 px-2.5 py-0.5 rounded-pill bg-cohere-black/70 border border-white/10 text-[11px] text-slate-200 font-mono"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                <span>{issue}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Verifier Test Verdict & Visual QA Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2 rounded-lg bg-cohere-black/70 border border-white/10 text-[11px] text-slate-300">
        <div
          data-testid="delivery-gate-verifier-verdict"
          className="flex items-center space-x-2"
        >
          {isTestPassed ? (
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-coral shrink-0" />
          )}
          <span className="font-medium text-slate-200">{testVerdictTitle}</span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400">
            {isTestPassed ? "Quality gate verified" : "Quality gate failed"}
          </span>
        </div>

        <VisualQABadge
          telemetry={visualQa}
          isLoading={visualQaQuery.isLoading && !visualQa}
        />
      </div>

      {/* Screenshot Thumbnail with Desktop & Mobile Indicators */}
      <VisualQAThumbnail
        telemetry={visualQa}
        onInspect={(vp) => {
          setSelectedViewport(vp || "desktop");
          setIsVqaModalOpen(true);
        }}
      />

      {/* Visual QA Warning Telemetry Details if failed */}
      {hasVisualQaFailure && (
        <div
          data-testid="visual-qa-error-telemetry"
          className="p-3 rounded-lg bg-coral/10 border border-coral/30 space-y-1.5 text-xs text-coral"
        >
          <div className="flex items-center space-x-2 font-semibold text-coral">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Visual Verification Failed — Merge Blocked</span>
          </div>
          <div className="text-[11px] text-coral/90">
            Fatal browser console errors or Clean Canvas violations detected during headless verification.
          </div>
          {visualQa?.errors && visualQa.errors.length > 0 && (
            <ul className="list-disc pl-5 font-mono text-[11px] text-coral/90 space-y-0.5 max-h-32 overflow-y-auto">
              {visualQa.errors.map((err, idx) => (
                <li key={idx}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Conflict Warning */}
      {hasConflict && (
        <div
          data-testid="delivery-gate-conflict-warning"
          className="flex items-start space-x-2 p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs"
        >
          <AlertTriangle className="w-4 h-4 text-coral shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-coral">Merge Conflict Detected</div>
            <div className="text-[11px] text-coral/90">
              Conflicts must be resolved on GitHub before merging into main.
            </div>
            {pr?.html_url && (
              <a
                href={pr.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1 text-[11px] font-medium text-coral underline hover:text-white"
              >
                <span>Resolve conflicts on GitHub</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>
      )}

      {/* Error Banners */}
      {mergeError && (
        <div className="p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs">
          {mergeError}
        </div>
      )}
      {markReadyError && (
        <div className="p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs">
          {markReadyError}
        </div>
      )}

      {/* In-Studio Merge Control Action Area */}
      <div className="pt-1 border-t border-white/10">
        {isMerged ? (
          <div className="flex items-center justify-between">
            <div
              data-testid="delivery-gate-merged-banner"
              className="flex items-center space-x-2 py-1.5 px-3 rounded-pill bg-pale-green text-deep-green border border-deep-green/20 font-medium text-xs"
            >
              <GitMerge className="w-4 h-4 text-deep-green shrink-0" />
              <span>Merged into main</span>
              {pr?.base_branch && (
                <span className="text-deep-green/70 text-[11px] font-mono">
                  ({pr.base_branch})
                </span>
              )}
            </div>
            {onRollbackTurn && (
              <Button
                data-testid="delivery-gate-rollback-btn"
                type="button"
                variant="secondary"
                size="sm"
                disabled={true}
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                title="Cannot roll back turn for a merged pull request"
                className="text-slate-400"
              >
                Roll Back Turn
              </Button>
            )}
          </div>
        ) : isConfirming ? (
          <DeliveryGateConfirmation
            pullNumber={pullNumber}
            isLoading={mergeMutation.isPending}
            onConfirm={handleConfirmMerge}
            onCancel={() => setIsConfirming(false)}
          />
        ) : (
          <div className="flex items-center justify-between">
            <div className="text-[11px] text-slate-400">
              {isReverted ? (
                <span className="text-slate-400 font-medium">Turn has been reverted</span>
              ) : activeJobRunning ? (
                <span className="text-amber-400 font-medium">Job Actively Executing</span>
              ) : !pullNumber ? (
                <span className="text-coral">Pull Request number not found</span>
              ) : isDraft ? (
                <span>PR is currently in Draft</span>
              ) : hasConflict ? (
                <span className="text-coral">Blocked by merge conflicts</span>
              ) : hasVisualQaFailure ? (
                <span className="text-coral">Blocked by Visual QA failures</span>
              ) : isClosed ? (
                <span className="text-slate-400">PR is closed</span>
              ) : (
                <span>All checks passed. Ready to squash merge.</span>
              )}
            </div>

            <div className="flex items-center space-x-2">
              {isDraft && !isMerged && !isClosed && !isReverted && (
                <Button
                  data-testid="btn-delivery-gate-mark-ready"
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={!pullNumber || activeJobRunning || markReadyMutation.isPending}
                  isLoading={markReadyMutation.isPending}
                  onClick={handleMarkReadyForReview}
                  icon={<CheckCircle2 className="w-3.5 h-3.5 text-pale-green" />}
                  title="Mark this Pull Request as Ready for Review on GitHub"
                  className="text-slate-200"
                >
                  Mark Ready for Review
                </Button>
              )}
              {onRollbackTurn && (
                <Button
                  data-testid="delivery-gate-rollback-btn"
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={activeJobRunning || isMerged || isClosed || isReverted || isRollingBack}
                  isLoading={isRollingBack}
                  onClick={() => onRollbackTurn(data)}
                  icon={
                    activeJobRunning ? (
                      <Lock className="w-3.5 h-3.5 text-slate-500" data-testid="delivery-gate-lock-icon" />
                    ) : (
                      <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
                    )
                  }
                  title={
                    activeJobRunning
                      ? "Cannot roll back turn while job is running"
                      : isMerged
                      ? "Cannot roll back turn for a merged pull request"
                      : isReverted
                      ? "This turn has already been reverted"
                      : "Roll back this turn"
                  }
                  className="text-slate-300"
                >
                  Roll Back Turn
                </Button>
              )}
              <Button
                data-testid="btn-delivery-gate-merge"
                type="button"
                variant="inverted"
                size="sm"
                disabled={isMergeDisabled}
                onClick={() => setIsConfirming(true)}
                icon={<GitMerge className="w-3.5 h-3.5" />}
                title={
                  !pullNumber
                    ? "Cannot merge: Pull request number could not be resolved"
                    : activeJobRunning
                    ? "Cannot merge while job is running"
                    : isDraft
                    ? "Cannot merge while PR is in Draft"
                    : hasConflict
                    ? "Cannot merge due to conflicts"
                    : hasVisualQaFailure
                    ? "Cannot merge: Visual QA verification failed"
                    : isClosed
                    ? "Cannot merge a closed pull request"
                    : isReverted
                    ? "Cannot merge a reverted turn"
                    : "Squash merge Feature Pull Request into main"
                }
                className="font-medium"
              >
                Merge into main
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Expandable High-Resolution Visual QA Modal */}
      <VisualQAModal
        isOpen={isVqaModalOpen}
        onClose={() => setIsVqaModalOpen(false)}
        repo={repo}
        telemetry={visualQa}
        initialViewport={selectedViewport}
      />
    </div>
  );
};
