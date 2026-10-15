import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  X,
  RefreshCw,
  GitPullRequest,
  AlertCircle,
  Layers,
} from "lucide-react";
import { Issue, PullRequest } from "../types";
import { useStudioIssuesQuery, useStudioPullRequestQuery, studioQueryKeys } from "../hooks/useStudioQueries";
import { useQueryClient } from "@tanstack/react-query";
import { useStudio } from "../context/StudioContext";
import { IssueCard } from "./issue-drawer/IssueCard";
import { MilestoneGroup } from "./issue-drawer/MilestoneGroup";
import { IssueFilterBar } from "./issue-drawer/IssueFilterBar";
import { useDrawerIssues, isIssueResolved, getOpenBlockers } from "./issue-drawer/useDrawerIssues";

export interface IssueDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  repo: string;
  issues?: Issue[];
  onGrillAndAlign?: (issue: Issue) => void;
  onInstantDispatch?: (params: { issue: Issue; repo: string }) => Promise<void> | void;
  onRunMilestone?: (params: {
    milestone: { number?: number; title: string; slug: string };
    repo: string;
    issues: Issue[];
  }) => Promise<void> | void;
  onRefresh?: () => void;
}

export const IssueDrawer: React.FC<IssueDrawerProps> = ({
  isOpen,
  onClose,
  repo,
  issues: overrideIssues,
  onGrillAndAlign: propGrillAndAlign,
  onInstantDispatch: propInstantDispatch,
  onRunMilestone: propRunMilestone,
  onRefresh: propRefresh,
}) => {
  const queryClient = useQueryClient();
  const studioContext = useStudio();
  const issuesQuery = useStudioIssuesQuery(repo, "all");
  const prQuery = useStudioPullRequestQuery(repo);

  const pullRequests: PullRequest[] = useMemo(() => {
    return prQuery.data?.pulls || [];
  }, [prQuery.data?.pulls]);

  const [filterState, setFilterState] = useState<"open" | "closed" | "all">("open");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activePopoverMilestone, setActivePopoverMilestone] = useState<string | null>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (activePopoverMilestone) {
          setActivePopoverMilestone(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, activePopoverMilestone, onClose]);

  const allIssues: Issue[] = useMemo(() => {
    return overrideIssues || issuesQuery.data?.issues || [];
  }, [overrideIssues, issuesQuery.data?.issues]);

  const { filteredIssues, milestoneGroups, backlogIssues } = useDrawerIssues({
    allIssues,
    filterState,
    searchQuery,
  });

  const handleRefresh = async () => {
    if (propRefresh) {
      propRefresh();
    }
    if (repo) {
      await queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(repo) });
      await queryClient.invalidateQueries({ queryKey: studioQueryKeys.pullRequests(repo) });
    }
  };

  const getBlockersForIssue = useCallback(
    (issue: Issue) => getOpenBlockers(issue, allIssues),
    [allIssues]
  );

  // Handle Grill & Align action
  const handleGrillAndAlign = (issue: Issue) => {
    if (propGrillAndAlign) {
      propGrillAndAlign(issue);
    } else if (studioContext?.onSendPrompt) {
      const fullSpec =
        issue.body && issue.body.trim()
          ? `Issue #${issue.number}: ${issue.title}\n\n${issue.body.trim()}`
          : `Issue #${issue.number}: ${issue.title}`;
      studioContext.onSendPrompt(fullSpec, true);
    }
    onClose();
  };

  // Handle Instant Dispatch action
  const handleInstantDispatch = async (issue: Issue) => {
    if (propInstantDispatch) {
      await propInstantDispatch({ issue, repo });
    } else if (studioContext?.onInstantDispatch) {
      await studioContext.onInstantDispatch({
        repo,
        issue_number: issue.number,
        milestone_slug: issue.milestone?.slug,
      });
    }
  };

  // Handle Run Milestone batch dispatch
  const handleRunMilestone = async (
    milestone: { number?: number; title: string; slug: string },
    milestoneIssues: Issue[]
  ) => {
    if (propRunMilestone) {
      await propRunMilestone({ milestone, repo, issues: milestoneIssues });
    } else if (studioContext?.onInstantDispatch) {
      await studioContext.onInstantDispatch({
        repo,
        milestone_slug: milestone.slug,
        milestone_title: milestone.title,
      });
    }
    setActivePopoverMilestone(null);
  };

  if (!isOpen) return null;

  return (
    <div
      id="studio-issue-drawer"
      data-testid="studio-issue-drawer"
      className="fixed inset-y-0 right-0 z-50 flex max-w-full pl-10"
      aria-labelledby="issue-drawer-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        data-testid="issue-drawer-backdrop"
        onClick={onClose}
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity duration-300 -z-10"
      />

      {/* Slide-over panel */}
      <div className="w-screen max-w-2xl bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/70 shrink-0">
          <div className="flex items-center space-x-3">
            <div className="p-1.5 rounded-md bg-indigo-950/80 border border-indigo-800 text-indigo-400">
              <GitPullRequest className="w-4 h-4" />
            </div>
            <div>
              <h2 id="issue-drawer-title" className="text-sm font-semibold text-slate-100 flex items-center space-x-2">
                <span>GitHub Issues</span>
                <span className="text-xs font-mono font-normal text-slate-400 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                  {repo}
                </span>
              </h2>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              id="btn-refresh-issues"
              data-testid="refresh-issues-btn"
              type="button"
              onClick={handleRefresh}
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors focus:outline-none"
              title="Refresh issues from GitHub"
            >
              <RefreshCw className={`w-4 h-4 ${issuesQuery.isFetching ? "animate-spin text-indigo-400" : ""}`} />
            </button>
            <button
              id="btn-close-issue-drawer"
              data-testid="close-issue-drawer-btn"
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors focus:outline-none"
              title="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Filter & Search Toolbar */}
        <IssueFilterBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          filterState={filterState}
          onFilterChange={setFilterState}
        />

        {/* Drawer Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6 bg-slate-950/80">
          {issuesQuery.isError ? (
            <div
              data-testid="issues-error-state"
              className="flex flex-col items-center justify-center py-12 px-4 text-center space-y-3 bg-red-950/20 border border-red-900/40 rounded-lg"
            >
              <AlertCircle className="w-8 h-8 text-red-400" />
              <div className="space-y-1">
                <h3 className="text-xs font-semibold text-red-200">Failed to load GitHub issues</h3>
                <p className="text-[11px] text-slate-400">
                  {issuesQuery.error instanceof Error
                    ? issuesQuery.error.message
                    : "The GitHub API request failed. Verify repository permissions or network connection."}
                </p>
              </div>
              <button
                type="button"
                onClick={handleRefresh}
                className="px-3 py-1.5 rounded text-xs bg-red-900/60 hover:bg-red-800 text-red-200 border border-red-700/60 transition-colors"
              >
                Retry Request
              </button>
            </div>
          ) : issuesQuery.isLoading && allIssues.length === 0 ? (
            <div data-testid="issues-loading-skeleton" className="space-y-4 py-4 animate-pulse">
              <div className="h-12 bg-slate-850 bg-slate-800/60 rounded-lg" />
              <div className="h-24 bg-slate-850 bg-slate-800/40 rounded-lg" />
              <div className="h-24 bg-slate-850 bg-slate-800/40 rounded-lg" />
            </div>
          ) : filteredIssues.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-500 space-y-2">
              <GitPullRequest className="w-8 h-8 text-slate-600" />
              <span className="text-xs font-mono">No issues match the current filter.</span>
            </div>
          ) : (
            <>
              {/* Milestone Groups */}
              {milestoneGroups.map(({ milestone, issues }) => {
                const milestoneAllIssues = allIssues.filter(
                  (i) => i.milestone?.slug === milestone.slug || i.milestone?.title === milestone.title
                );
                return (
                  <MilestoneGroup
                    key={milestone.slug || milestone.title}
                    milestone={milestone}
                    allMilestoneIssues={milestoneAllIssues}
                    pullRequests={pullRequests}
                    isPopoverOpen={activePopoverMilestone === milestone.slug}
                    onTogglePopover={() =>
                      setActivePopoverMilestone(
                        activePopoverMilestone === milestone.slug ? null : milestone.slug || null
                      )
                    }
                    onClosePopover={() => setActivePopoverMilestone(null)}
                    onRunMilestone={handleRunMilestone}
                    isIssueResolved={isIssueResolved}
                    getOpenBlockers={getBlockersForIssue}
                  >
                    {issues.map((issue) => (
                      <IssueCard
                        key={issue.number}
                        issue={issue}
                        isResolved={isIssueResolved(issue)}
                        openBlockers={getBlockersForIssue(issue)}
                        onGrillAndAlign={handleGrillAndAlign}
                        onInstantDispatch={handleInstantDispatch}
                      />
                    ))}
                  </MilestoneGroup>
                );
              })}

              {/* Backlog / Unassigned Issues */}
              {backlogIssues.length > 0 && (
                <div data-testid="milestone-group-backlog" className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-slate-800/80">
                    <div className="flex items-center space-x-2">
                      <Layers className="w-4 h-4 text-slate-400" />
                      <span className="text-xs font-semibold text-slate-300">
                        Backlog / Unassigned
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">
                      {backlogIssues.length} tickets
                    </span>
                  </div>

                  <div className="space-y-2 pl-1">
                    {backlogIssues.map((issue) => (
                      <IssueCard
                        key={issue.number}
                        issue={issue}
                        isResolved={isIssueResolved(issue)}
                        openBlockers={getBlockersForIssue(issue)}
                        onGrillAndAlign={handleGrillAndAlign}
                        onInstantDispatch={handleInstantDispatch}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
