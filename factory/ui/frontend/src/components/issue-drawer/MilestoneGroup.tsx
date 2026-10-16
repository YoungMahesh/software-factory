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
      <div className="relative flex items-center justify-between p-3 rounded-xl bg-white border border-hairline shadow-2xs">
        <div className="flex items-center space-x-2.5">
          <Layers className="w-4 h-4 text-primary" />
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-ink font-sans">
                {milestone.title}{" "}
                {milestone.number && (
                  <span className="text-[10px] text-muted font-mono">
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
                      className={`text-[10px] px-2 py-0.5 rounded-pill ${badgeConfig.className}`}
                    >
                      {badgeConfig.label}
                    </Badge>
                    {associatedPR.html_url && (
                      <a
                        data-testid={`milestone-pr-link-${milestone.slug}`}
                        href={associatedPR.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted hover:text-ink transition-colors p-0.5"
                        title={`View Pull Request #${associatedPR.number} on GitHub`}
                      >
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                );
              })()}
            </div>
            <div className="text-[10px] text-muted font-mono">
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
            className="flex items-center space-x-1.5 px-3 py-1 rounded-pill bg-primary hover:bg-cohere-black text-white text-xs font-semibold transition-colors shadow-xs cursor-pointer"
            title="Run entire milestone batch"
          >
            <Zap className="w-3 h-3 fill-current" />
            <span>Run Milestone</span>
          </button>

          {/* Confirmation Popover */}
          {isPopoverOpen && (
            <div
              data-testid="milestone-batch-popover"
              className="absolute right-0 top-full mt-2 w-72 p-3.5 bg-white border border-hairline rounded-xl shadow-2xl z-20 space-y-3 animate-in fade-in zoom-in-95 duration-150 text-ink"
            >
              <div className="text-xs font-semibold text-ink font-sans">
                Confirm Milestone Batch
              </div>
              <div className="text-[11px] text-muted space-y-1">
                <div>
                  Target branch:{" "}
                  <span className="font-mono text-primary font-semibold">
                    factory/{milestone.slug}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-ink bg-soft-stone p-2 rounded-lg border border-hairline">
                  <div>• {totalCount} total</div>
                  <div className="text-deep-green">• {readyCount} ready</div>
                  <div className="text-coral">• {blockedCount} blocked</div>
                  {claimedCount > 0 && <div className="text-ink">• {claimedCount} claimed</div>}
                  <div className="text-primary">• {resolvedCount} resolved</div>
                </div>
              </div>
              <div className="flex items-center justify-end space-x-2 pt-1 border-t border-hairline">
                <button
                  data-testid="cancel-batch-btn"
                  type="button"
                  onClick={onClosePopover}
                  className="px-3 py-1 rounded-pill text-xs text-muted hover:text-ink hover:bg-soft-stone transition-colors cursor-pointer"
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
                  className="px-3 py-1 rounded-pill text-xs bg-primary hover:bg-cohere-black text-white font-semibold shadow-xs transition-colors cursor-pointer"
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
