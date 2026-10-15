import { useMemo } from "react";
import { Issue, IssueMilestone } from "../../types";

export const isIssueResolved = (issue: Issue): boolean => {
  if (issue.state && issue.state.toLowerCase() === "closed") return true;
  if (issue.status && issue.status.toLowerCase() === "resolved") return true;
  if (issue.labels?.some((l) => l.toLowerCase() === "factory:resolved")) return true;
  return false;
};

export const getOpenBlockers = (issue: Issue, allIssues: Issue[]): string[] => {
  if (!issue.blocked_by || issue.blocked_by.length === 0) return [];
  return issue.blocked_by
    .map((b) => String(b).replace(/^#/, "").trim())
    .filter((blockerId) => {
      if (!blockerId || blockerId.toLowerCase() === "none") return false;
      const blockerIssue = allIssues.find((i) => String(i.number) === blockerId);
      if (blockerIssue) {
        return !isIssueResolved(blockerIssue);
      }
      return true;
    });
};

export interface UseDrawerIssuesParams {
  allIssues: Issue[];
  filterState: "open" | "closed" | "all";
  searchQuery: string;
}

export function useDrawerIssues({ allIssues, filterState, searchQuery }: UseDrawerIssuesParams) {
  const filteredIssues = useMemo(() => {
    return allIssues.filter((issue) => {
      const resolved = isIssueResolved(issue);
      if (filterState === "open" && resolved) return false;
      if (filterState === "closed" && !resolved) return false;

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

  return {
    filteredIssues,
    milestoneGroups,
    backlogIssues,
  };
}
