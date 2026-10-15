import React, { useState, useEffect, useMemo } from "react";
import {
  X,
  Search,
  RefreshCw,
  GitPullRequest,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Layers,
  Zap,
  MessageSquareQuote,
  Lock,
} from "lucide-react";
import { Issue, IssueMilestone, PullRequest } from "../types";
import { useStudioIssuesQuery, useStudioPullRequestQuery, studioQueryKeys } from "../hooks/useStudioQueries";
import { useQueryClient } from "@tanstack/react-query";
import { useStudio } from "../context/StudioContext";
import { Badge } from "./ui/Badge";
import { getPullRequestStatus, getPullRequestBadgeConfig } from "../utils";

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
  const [expandedIssues, setExpandedIssues] = useState<Record<string | number, boolean>>({});
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

  const handleRefresh = async () => {
    if (propRefresh) {
      propRefresh();
    }
    if (repo) {
      await queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(repo) });
      await queryClient.invalidateQueries({ queryKey: studioQueryKeys.pullRequests(repo) });
    }
  };

  // Helper to determine if an issue is resolved
  const isIssueResolved = (issue: Issue): boolean => {
    if (issue.state && issue.state.toLowerCase() === "closed") return true;
    if (issue.status && issue.status.toLowerCase() === "resolved") return true;
    if (issue.labels?.some((l) => l.toLowerCase() === "factory:resolved")) return true;
    return false;
  };

  // Helper to get open blockers for an issue
  const getOpenBlockers = (issue: Issue): string[] => {
    if (!issue.blocked_by || issue.blocked_by.length === 0) return [];
    return issue.blocked_by
      .map((b) => String(b).replace(/^#/, "").trim())
      .filter((blockerId) => {
        if (!blockerId || blockerId.toLowerCase() === "none") return false;
        const blockerIssue = allIssues.find((i) => String(i.number) === blockerId);
        if (blockerIssue) {
          return !isIssueResolved(blockerIssue);
        }
        // If not found in current issue list, assume unresolved blocker
        return true;
      });
  };

  // Handle Grill & Align action
  const handleGrillAndAlign = (issue: Issue) => {
    if (propGrillAndAlign) {
      propGrillAndAlign(issue);
    } else if (studioContext?.onSendPrompt) {
      const fullSpec = issue.body && issue.body.trim()
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

  // Filter issues based on state and search query
  const filteredIssues = useMemo(() => {
    return allIssues.filter((issue) => {
      // 1. State filter
      const resolved = isIssueResolved(issue);
      if (filterState === "open" && resolved) return false;
      if (filterState === "closed" && !resolved) return false;

      // 2. Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const cleanQueryNum = query.replace(/^#/, "");
        const numMatch = String(issue.number) === cleanQueryNum || `#${issue.number}` === query;
        const titleMatch = issue.title.toLowerCase().includes(query);
        const labelMatch = (issue.labels || []).some((l) => l.toLowerCase().includes(query));
        if (!numMatch && !titleMatch && !labelMatch) {
          return false;
        }
      }

      return true;
    });
  }, [allIssues, filterState, searchQuery]);

  // Group filtered issues by Milestone
  const { milestoneGroups, backlogIssues } = useMemo(() => {
    const groups: Map<string, { milestone: IssueMilestone; issues: Issue[] }> = new Map();
    const backlog: Issue[] = [];

    allIssues.forEach((issue) => {
      if (issue.milestone && (issue.milestone.title || issue.milestone.slug)) {
        const slug =
          issue.milestone.slug ||
          (issue.milestone.title ? issue.milestone.title.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "milestone");
        if (!groups.has(slug)) {
          groups.set(slug, {
            milestone: {
              ...issue.milestone,
              slug,
            },
            issues: [],
          });
        }
      }
    });

    filteredIssues.forEach((issue) => {
      if (issue.milestone && (issue.milestone.title || issue.milestone.slug)) {
        const slug =
          issue.milestone.slug ||
          (issue.milestone.title ? issue.milestone.title.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "milestone");
        const group = groups.get(slug);
        if (group) {
          group.issues.push(issue);
        }
      } else {
        backlog.push(issue);
      }
    });

    return {
      milestoneGroups: Array.from(groups.values()).filter((g) => g.issues.length > 0),
      backlogIssues: backlog,
    };
  }, [allIssues, filteredIssues]);

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
        <div className="p-4 bg-slate-950/40 border-b border-slate-800/80 space-y-3 shrink-0">
          <div className="flex items-center space-x-2">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                data-testid="issue-search-input"
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by #number, title, or label..."
                className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
              />
            </div>

            {/* Filter Toggle Buttons */}
            <div className="flex items-center bg-slate-900 p-0.5 rounded-md border border-slate-800 text-xs shrink-0">
              <button
                data-testid="filter-open"
                type="button"
                onClick={() => setFilterState("open")}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  filterState === "open"
                    ? "bg-indigo-600 text-white shadow-xs"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Open
              </button>
              <button
                data-testid="filter-closed"
                type="button"
                onClick={() => setFilterState("closed")}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  filterState === "closed"
                    ? "bg-indigo-600 text-white shadow-xs"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Closed
              </button>
              <button
                data-testid="filter-all"
                type="button"
                onClick={() => setFilterState("all")}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  filterState === "all"
                    ? "bg-indigo-600 text-white shadow-xs"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                All
              </button>
            </div>
          </div>
        </div>

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
                const totalCount = milestoneAllIssues.length;
                const resolvedCount = milestoneAllIssues.filter(isIssueResolved).length;
                const blockedCount = milestoneAllIssues.filter((i) => !isIssueResolved(i) && getOpenBlockers(i).length > 0).length;
                const claimedCount = milestoneAllIssues.filter((i) => !isIssueResolved(i) && (i.labels?.includes("factory:claimed") || i.status === "claimed")).length;
                const readyCount = milestoneAllIssues.filter(
                  (i) => !isIssueResolved(i) && getOpenBlockers(i).length === 0 && !(i.labels?.includes("factory:claimed") || i.status === "claimed")
                ).length;

                const isPopoverOpen = activePopoverMilestone === milestone.slug;

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
                          onClick={() =>
                            setActivePopoverMilestone(isPopoverOpen ? null : milestone.slug || null)
                          }
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
                                onClick={() => setActivePopoverMilestone(null)}
                                className="px-2.5 py-1 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                              >
                                Cancel
                              </button>
                              <button
                                data-testid="confirm-batch-btn"
                                type="button"
                                onClick={() =>
                                  handleRunMilestone(
                                    {
                                      number: milestone.number,
                                      title: milestone.title,
                                      slug: milestone.slug || "milestone",
                                    },
                                    milestoneAllIssues
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
                    <div className="space-y-2 pl-1">
                      {issues.map((issue) => renderIssueCard(issue))}
                    </div>
                  </div>
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
                    {backlogIssues.map((issue) => renderIssueCard(issue))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );

  // Render individual Issue Card
  function renderIssueCard(issue: Issue) {
    const isExpanded = Boolean(expandedIssues[issue.number]);
    const resolved = isIssueResolved(issue);
    const openBlockers = getOpenBlockers(issue);
    const isBlocked = openBlockers.length > 0;
    const isClaimed =
      issue.labels?.includes("factory:claimed") || issue.status === "claimed";

    let disableInstantReason = "";
    if (isBlocked) {
      disableInstantReason = `Blocked by open issue(s): #${openBlockers.join(", #")}`;
    } else if (isClaimed) {
      disableInstantReason = "Issue is currently claimed by an active job (factory:claimed)";
    } else if (resolved) {
      disableInstantReason = "Issue is already resolved";
    }

    const isInstantDisabled = isBlocked || isClaimed || resolved;

    return (
      <div
        key={issue.number}
        data-testid={`issue-card-${issue.number}`}
        className="p-3.5 rounded-lg bg-slate-900 border border-slate-800/90 hover:border-slate-700/80 transition-colors space-y-2.5"
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start space-x-2">
            <span className="text-xs font-mono font-bold text-indigo-400 shrink-0 mt-0.5">
              #{issue.number}
            </span>
            <span className="text-xs font-semibold text-slate-200 leading-snug">
              {issue.title}
            </span>
          </div>

          {issue.html_url && (
            <a
              href={issue.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-500 hover:text-slate-300 p-0.5 transition-colors shrink-0"
              title="View on GitHub"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>

        {/* Labels & Status Row */}
        <div className="flex flex-wrap items-center gap-1.5">
          {/* Lifecycle Status Pills */}
          {(issue.labels || []).map((label) => {
            const lowerLabel = label.toLowerCase();
            let pillStyle = "bg-slate-800 text-slate-400 border-slate-700";

            if (lowerLabel === "factory:ready") {
              pillStyle = "bg-emerald-950/80 text-emerald-300 border-emerald-800";
            } else if (lowerLabel === "factory:claimed") {
              pillStyle = "bg-amber-950/80 text-amber-300 border-amber-800";
            } else if (lowerLabel === "factory:resolved") {
              pillStyle = "bg-purple-950/80 text-purple-300 border-purple-800";
            } else if (lowerLabel === "factory:ready-for-human") {
              pillStyle = "bg-red-950/80 text-red-300 border-red-800";
            }

            return (
              <span
                key={label}
                data-testid={`status-pill-${label}`}
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${pillStyle}`}
              >
                {label}
              </span>
            );
          })}
        </div>

        {/* Blocker alert if blocked */}
        {isBlocked && (
          <div
            data-testid={`blocked-alert-${issue.number}`}
            className="flex items-center space-x-1.5 p-2 rounded bg-amber-950/40 border border-amber-800/60 text-[11px] text-amber-300 font-mono"
          >
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>Blocked by open issue(s): #{openBlockers.join(", #")}</span>
          </div>
        )}

        {/* Body preview (expandable) */}
        {issue.body && (
          <div className="text-[11px] text-slate-400">
            <button
              type="button"
              onClick={() =>
                setExpandedIssues((prev) => ({ ...prev, [issue.number]: !prev[issue.number] }))
              }
              className="flex items-center space-x-1 text-slate-500 hover:text-slate-300 text-[10px] font-mono mb-1"
            >
              {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <span>{isExpanded ? "Hide Details" : "Show Details"}</span>
            </button>
            {isExpanded && (
              <div
                data-testid={`issue-body-${issue.number}`}
                className="p-2.5 rounded bg-slate-950/70 border border-slate-800/80 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-slate-300 max-h-48 overflow-y-auto"
              >
                {issue.body}
              </div>
            )}
          </div>
        )}

        {/* Action Buttons Row */}
        <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800/70">
          {/* Grill & Align button (always enabled) */}
          <button
            data-testid={`grill-align-btn-${issue.number}`}
            type="button"
            onClick={() => handleGrillAndAlign(issue)}
            className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors border border-slate-700"
            title="Interview requirements with Grilling Assistant before changing code"
          >
            <MessageSquareQuote className="w-3.5 h-3.5 text-indigo-400" />
            <span>Grill & Align</span>
          </button>

          {/* Instant Dispatch button (disabled if blocked or claimed) */}
          <button
            data-testid={`instant-dispatch-btn-${issue.number}`}
            type="button"
            onClick={() => handleInstantDispatch(issue)}
            disabled={isInstantDisabled}
            title={disableInstantReason || "Bypass Grilling Assistant and dispatch assembly line directly"}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              isInstantDisabled
                ? "bg-slate-800/50 text-slate-500 border border-slate-800 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs"
            }`}
          >
            {isInstantDisabled ? (
              <Lock className="w-3 h-3 text-slate-500" />
            ) : (
              <Zap className="w-3 h-3 fill-current" />
            )}
            <span>Instant Dispatch</span>
          </button>
        </div>
      </div>
    );
  }
};
