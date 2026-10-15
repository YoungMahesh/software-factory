import React, { useState } from "react";
import {
  GitPullRequest,
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
import { DeliveryGateData, PullRequest } from "../types";
import { useStudioPullRequestQuery, useMergePullRequestMutation } from "../hooks/useStudioQueries";
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
  const [mergeError, setMergeError] = useState<string | null>(null);

  const prQuery = useStudioPullRequestQuery(repo);
  const mergeMutation = useMergePullRequestMutation();

  // Find live PR from query cache if available for reactive updates
  const pullNumber = data.pull_number || data.pull_request?.number;
  const livePR: PullRequest | undefined = prQuery.data?.pulls?.find(
    (p) => p.number === pullNumber
  );

  const pr: PullRequest | undefined = livePR || data.pull_request;

  // Determine current status
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

  // Resolved issues list
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
    if (!pullNumber) return;
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

  const isMergeDisabled = isDraft || activeJobRunning || hasConflict || isMerged || isClosed || isReverted || isRollingBack;

  return (
    <div
      data-testid="delivery-gate-card"
      className={`rounded-xl border ${
        isReverted
          ? "border-slate-800 bg-slate-900/40 opacity-75"
          : "border-indigo-900/60 bg-slate-900/80"
      } p-4 space-y-3.5 shadow-sm text-xs ${className}`}
    >
      {/* Header: Title & Badges */}
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <GitPullRequest className="w-4 h-4 text-indigo-400 shrink-0" />
            <span className="font-semibold text-slate-100 text-sm">
              {pr?.title || `Feature Pull Request #${pullNumber}`}
            </span>
            {pullNumber && (
              <span className="text-slate-400 font-mono text-xs">#{pullNumber}</span>
            )}
          </div>
          {pr?.head_branch && (
            <div className="text-[11px] font-mono text-slate-400 pl-6">
              {pr.head_branch} <span className="text-slate-500">➔</span> main
            </div>
          )}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          {isReverted && (
            <Badge
              data-testid="turn-reverted-badge"
              variant="neutral"
              className="bg-slate-800 text-slate-400 border-slate-700"
            >
              Reverted
            </Badge>
          )}
          {getStatusBadge()}
          {pr?.html_url && (
            <a
              data-testid="delivery-gate-gh-link"
              href={pr.html_url}
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
                className="flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                <span>{issue}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Verifier Test Verdict */}
      <div
        data-testid="delivery-gate-verifier-verdict"
        className="flex items-center space-x-2 p-2 rounded bg-slate-950/70 border border-slate-800/80 text-[11px] text-slate-300"
      >
        {isTestPassed ? (
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
        )}
        <span className="font-medium text-slate-200">{testVerdictTitle}</span>
        <span className="text-slate-500">•</span>
        <span className="text-slate-400">
          {isTestPassed ? "Quality gate verified" : "Quality gate failed"}
        </span>
      </div>

      {/* Conflict Warning */}
      {hasConflict && (
        <div
          data-testid="delivery-gate-conflict-warning"
          className="flex items-start space-x-2 p-2.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs"
        >
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-rose-200">Merge Conflict Detected</div>
            <div className="text-[11px] text-rose-300/90">
              Conflicts must be resolved on GitHub before merging into main.
            </div>
            {pr?.html_url && (
              <a
                href={pr.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1 text-[11px] font-medium text-rose-300 underline hover:text-white"
              >
                <span>Resolve conflicts on GitHub</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>
      )}

      {/* Error Banner */}
      {mergeError && (
        <div className="p-2.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs">
          {mergeError}
        </div>
      )}

      {/* In-Studio Merge Control Action Area */}
      <div className="pt-1 border-t border-slate-800/80">
        {isMerged ? (
          <div className="flex items-center justify-between">
            <div
              data-testid="delivery-gate-merged-banner"
              className="flex items-center space-x-2 py-1.5 px-3 rounded bg-purple-950/40 border border-purple-900/50 text-purple-300 font-medium"
            >
              <GitMerge className="w-4 h-4 text-purple-400 shrink-0" />
              <span>Merged into main</span>
              {pr?.base_branch && (
                <span className="text-slate-400 text-[11px] font-mono">
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
                title="Cannot undo turn for a merged pull request"
              >
                Undo Turn
              </Button>
            )}
          </div>
        ) : isConfirming ? (
          <div className="p-3 rounded-lg bg-slate-950 border border-indigo-900/70 space-y-2.5">
            <div className="text-slate-200 font-medium text-xs">
              Squash merge Feature Pull Request #{pullNumber} into main?
            </div>
            <div className="text-[11px] text-slate-400">
              This will create a squash commit on <span className="font-mono text-slate-300">main</span>, delete the remote feature branch, and update the Live Preview.
            </div>
            <div className="flex items-center space-x-2 pt-1">
              <Button
                data-testid="btn-delivery-gate-confirm-merge"
                type="button"
                variant="primary"
                size="sm"
                onClick={handleConfirmMerge}
                isLoading={mergeMutation.isPending}
                disabled={mergeMutation.isPending}
                icon={<GitMerge className="w-3.5 h-3.5" />}
              >
                Confirm Squash Merge
              </Button>
              <Button
                data-testid="btn-delivery-gate-cancel-merge"
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setIsConfirming(false)}
                disabled={mergeMutation.isPending}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="text-[11px] text-slate-400">
              {isReverted ? (
                <span className="text-slate-400 font-medium">Turn has been reverted</span>
              ) : activeJobRunning ? (
                <span className="text-amber-400 font-medium">Job Actively Executing</span>
              ) : isDraft ? (
                <span>PR is currently in Draft</span>
              ) : hasConflict ? (
                <span className="text-rose-400">Blocked by merge conflicts</span>
              ) : isClosed ? (
                <span className="text-slate-400">PR is closed</span>
              ) : (
                <span>All checks passed. Ready to squash merge.</span>
              )}
            </div>

            <div className="flex items-center space-x-2">
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
                      <Lock className="w-3.5 h-3.5" data-testid="delivery-gate-lock-icon" />
                    ) : (
                      <RotateCcw className="w-3.5 h-3.5" />
                    )
                  }
                  title={
                    activeJobRunning
                      ? "Cannot undo turn while job is running"
                      : isMerged
                      ? "Cannot undo turn for a merged pull request"
                      : isReverted
                      ? "This turn has already been reverted"
                      : "Roll back this turn"
                  }
                >
                  Undo Turn
                </Button>
              )}
              <Button
                data-testid="btn-delivery-gate-merge"
                type="button"
                variant="primary"
                size="sm"
                disabled={isMergeDisabled}
                onClick={() => setIsConfirming(true)}
                icon={<GitMerge className="w-3.5 h-3.5" />}
                title={
                  activeJobRunning
                    ? "Cannot merge while job is running"
                    : isDraft
                    ? "Cannot merge while PR is in Draft"
                    : hasConflict
                    ? "Cannot merge due to conflicts"
                    : isClosed
                    ? "Cannot merge a closed pull request"
                    : isReverted
                    ? "Cannot merge a reverted turn"
                    : "Squash merge Feature Pull Request into main"
                }
              >
                Merge into main
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
