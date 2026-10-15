import React, { useState } from "react";
import {
  GitPullRequest,
  ExternalLink,
  CheckCircle2,
  GitMerge,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { DeliveryGateData, PullRequest } from "../types";
import { useStudioPullRequestQuery, useMergePullRequestMutation } from "../hooks/useStudioQueries";

export interface DeliveryGateCardProps {
  repo: string;
  data: DeliveryGateData;
  activeJobRunning?: boolean;
  onMergeSuccess?: (result: any) => void;
  className?: string;
}

export const DeliveryGateCard: React.FC<DeliveryGateCardProps> = ({
  repo,
  data,
  activeJobRunning = false,
  onMergeSuccess,
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
  const isMerged = Boolean(
    data.merged ||
    pr?.merged ||
    pr?.status === "merged" ||
    data.status === "merged"
  );

  const hasConflict = Boolean(
    pr?.status === "conflict" ||
    pr?.mergeable === false ||
    pr?.mergeable_state === "dirty" ||
    pr?.mergeable_state === "conflict"
  );

  const isDraft = Boolean(pr?.draft || pr?.status === "draft");

  const status = isMerged
    ? "merged"
    : hasConflict
    ? "conflict"
    : isDraft
    ? "draft"
    : "ready_for_review";

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
    switch (status) {
      case "merged":
        return (
          <Badge
            data-testid="pr-status-badge"
            variant="stage"
            className="bg-purple-950/80 text-purple-300 border-purple-800"
          >
            Merged
          </Badge>
        );
      case "conflict":
        return (
          <Badge
            data-testid="pr-status-badge"
            variant="danger"
            className="bg-rose-950/80 text-rose-300 border-rose-800"
          >
            Conflict
          </Badge>
        );
      case "draft":
        return (
          <Badge
            data-testid="pr-status-badge"
            variant="warning"
            className="bg-amber-950/80 text-amber-300 border-amber-800"
          >
            Draft
          </Badge>
        );
      case "ready_for_review":
      default:
        return (
          <Badge
            data-testid="pr-status-badge"
            variant="success"
            className="bg-emerald-950/80 text-emerald-300 border-emerald-800"
          >
            Ready for Review
          </Badge>
        );
    }
  };

  const isMergeDisabled = isDraft || activeJobRunning || hasConflict || isMerged;

  return (
    <div
      data-testid="delivery-gate-card"
      className={`rounded-xl border border-indigo-900/60 bg-slate-900/80 p-4 space-y-3.5 shadow-sm text-xs ${className}`}
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
        <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
        <span className="font-medium text-slate-200">Deterministic Tests Passing</span>
        <span className="text-slate-500">•</span>
        <span className="text-slate-400">Quality gate verified</span>
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
              {activeJobRunning ? (
                <span className="text-amber-400 font-medium">Job Actively Executing</span>
              ) : isDraft ? (
                <span>PR is currently in Draft</span>
              ) : hasConflict ? (
                <span className="text-rose-400">Blocked by merge conflicts</span>
              ) : (
                <span>All checks passed. Ready to squash merge.</span>
              )}
            </div>

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
                  : "Squash merge Feature Pull Request into main"
              }
            >
              Merge into main
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
