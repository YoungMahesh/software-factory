import React from "react";
import { Layers, Zap, ExternalLink } from "lucide-react";
import { Issue, IssueMilestone, PullRequest } from "../../types";
import { Badge } from "../ui/Badge";
import { getPullRequestStatus, getPullRequestBadgeConfig } from "../../utils";

export interface MilestoneGroupProps {
  milestone: IssueMilestone;
  allMilestoneIssues: Issue[];
  pullRequests: PullRequest[];
  isPopoverOpen: boolean;
  onTogglePopover: () => void;
  onClosePopover: () => void;
  onRunMilestone: (
    milestone: { number?: number; title: string; slug: string },
    issues: Issue[]
  ) => void;
  isIssueResolved: (issue: Issue) => boolean;
  getOpenBlockers: (issue: Issue) => string[];
  children: React.ReactNode;
}

export const MilestoneGroup: React.FC<MilestoneGroupProps> = ({
  milestone,
  allMilestoneIssues,
  pullRequests,
  isPopoverOpen,
  onTogglePopover,
  onClosePopover,
  onRunMilestone,
  isIssueResolved,
  getOpenBlockers,
  children,
}) => {
  const totalCount = allMilestoneIssues.length;
  const resolvedCount = allMilestoneIssues.filter(isIssueResolved).length;
  const blockedCount = allMilestoneIssues.filter(
    (i) => !isIssueResolved(i) && getOpenBlockers(i).length > 0
  ).length;
  const claimedCount = allMilestoneIssues.filter(
    (i) => !isIssueResolved(i) && (i.labels?.includes("factory:claimed") || i.status === "claimed")
  ).length;
  const readyCount = allMilestoneIssues.filter(
    (i) =>
      !isIssueResolved(i) &&
      getOpenBlockers(i).length === 0 &&
      !(i.labels?.includes("factory:claimed") || i.status === "claimed")
  ).length;

  const associatedPR = pullRequests.find((p) => {
    if (milestone.slug && p.head_branch === `factory/${milestone.slug}`) return true;
    if (milestone.slug && p.head_branch.endsWith(`/${milestone.slug}`)) return true;
    if (milestone.title && p.title.toLowerCase().includes(milestone.title.toLowerCase())) return true;
    return false;
  });

  return (
    <div
      key={milestone.slug || milestone.title}
      data-testid={`milestone-group-${milestone.slug}`}
      className="space-y-3"
    >
      {/* Milestone Header */}
      <div className="relative flex items-center justify-between p-3 rounded-lg bg-slate-900/90 border border-slate-800">
        <div className="flex items-center space-x-2.5">
          <Layers className="w-4 h-4 text-indigo-400" />
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-200">
                {milestone.title}{" "}
                {milestone.number && (
                  <span className="text-[10px] text-slate-400 font-mono">
                    (#{milestone.number})
                  </span>
                )}
              </span>

              {associatedPR && (() => {
                const prStatus = getPullRequestStatus(associatedPR);
                const badgeConfig = getPullRequestBadgeConfig(prStatus);
                return (
                  <div className="flex items-center space-x-1.5 ml-2">
                    <Badge
                      data-testid={`milestone-pr-badge-${milestone.slug}`}
                      variant={badgeConfig.variant}
                      className={`text-[10px] px-1.5 py-0.2 ${badgeConfig.className}`}
                    >
                      {badgeConfig.label}
                    </Badge>
                    {associatedPR.html_url && (
                      <a
                        data-testid={`milestone-pr-link-${milestone.slug}`}
                        href={associatedPR.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-400 hover:text-indigo-300 transition-colors p-0.5"
                        title={`View Pull Request #${associatedPR.number} on GitHub`}
                      >
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                );
              })()}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {resolvedCount} / {totalCount} closed • {readyCount} ready
            </div>
          </div>
        </div>

        {/* Run Milestone Button */}
        <div className="relative">
          <button
            data-testid={`run-milestone-${milestone.slug}`}
            type="button"
            onClick={onTogglePopover}
            className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-xs"
            title="Run entire milestone batch"
          >
            <Zap className="w-3 h-3 fill-current" />
            <span>Run Milestone</span>
          </button>

          {/* Confirmation Popover */}
          {isPopoverOpen && (
            <div
              data-testid="milestone-batch-popover"
              className="absolute right-0 top-full mt-2 w-72 p-3.5 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl z-20 space-y-3 animate-in fade-in zoom-in-95 duration-150"
            >
              <div className="text-xs font-semibold text-slate-200">
                Confirm Milestone Batch
              </div>
              <div className="text-[11px] text-slate-400 space-y-1">
                <div>
                  Target branch:{" "}
                  <span className="font-mono text-indigo-300 font-semibold">
                    factory/{milestone.slug}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-slate-300 bg-slate-950 p-2 rounded border border-slate-800">
                  <div>• {totalCount} total</div>
                  <div className="text-emerald-400">• {readyCount} ready</div>
                  <div className="text-amber-400">• {blockedCount} blocked</div>
                  {claimedCount > 0 && <div className="text-amber-300">• {claimedCount} claimed</div>}
                  <div className="text-purple-400">• {resolvedCount} resolved</div>
                </div>
              </div>
              <div className="flex items-center justify-end space-x-2 pt-1 border-t border-slate-800">
                <button
                  data-testid="cancel-batch-btn"
                  type="button"
                  onClick={onClosePopover}
                  className="px-2.5 py-1 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  data-testid="confirm-batch-btn"
                  type="button"
                  onClick={() =>
                    onRunMilestone(
                      {
                        number: milestone.number,
                        title: milestone.title,
                        slug: milestone.slug || "milestone",
                      },
                      allMilestoneIssues
                    )
                  }
                  className="px-2.5 py-1 rounded text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
                >
                  Confirm Batch
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Milestone Issues List */}
      <div className="space-y-2 pl-1">{children}</div>
    </div>
  );
};
