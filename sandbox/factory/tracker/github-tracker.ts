import {
  type Ticket,
  type TicketStatus,
  type PreflightCheckResult,
  findContextFile,
  getFrontierTickets,
} from "../preflight.ts";
import {
  GitHubClient,
  type GitHubIssue,
  type GitHubMilestone,
  type GitHubPullRequest,
} from "../github.ts";
import type {
  IssueTracker,
  ClaimTicketOptions,
  ResolveTicketOptions,
  EscalateTicketOptions,
  DeliveryGateInitOptions,
  DeliveryGateInitResult,
  DeliveryGateUpdateOptions,
  DeliveryGateFinalizeOptions,
  DeliveryGateFinalizeResult,
} from "./types.ts";

export interface GitHubIssueTrackerOptions {
  client?: GitHubClient;
  token?: string;
  owner?: string;
  repo?: string;
}

export function extractIssueNumber(issueId?: string, featureSlug?: string): number | null {
  if (issueId) {
    const cleanId = issueId.trim().replace(/^#/, "");
    if (/^\d+$/.test(cleanId)) {
      return parseInt(cleanId, 10);
    }
  }
  if (featureSlug) {
    const match = featureSlug.trim().match(/^issue-(\d+)$/i);
    if (match) {
      return parseInt(match[1], 10);
    }
  }
  return null;
}

export const FACTORY_LABELS = {
  READY: "factory:ready",
  CLAIMED: "factory:claimed",
  RESOLVED: "factory:resolved",
  READY_FOR_HUMAN: "factory:ready-for-human",
} as const;

/**
 * Parses blocker issue numbers from issue markdown body ('Blocked by: #<id>' or 'Blocked by: None').
 */
export function parseGitHubBlockedBy(body?: string | null): string[] {
  if (!body) return [];
  const match = body.match(/(?:^|\n)\s*\*{0,2}Blocked\s+by\*{0,2}\s*:\s*\*{0,2}\s*([^\n\r]+)/i);
  if (!match) return [];

  const raw = match[1].trim().replace(/^[`*_]+|[`*_]+$/g, "").replace(/[\.;]+$/, "").trim();
  if (!raw || /^none(?:\s*\(.*?\))?[\.\s]*$/i.test(raw)) {
    return [];
  }

  const tokens = raw.split(",").map((t) => t.trim().replace(/^[`*_]+|[`*_]+$/g, "").replace(/[\.;]+$/, "").trim());
  const blockerIds: string[] = [];

  for (const token of tokens) {
    if (/^none(?:\s*\(.*?\))?[\.\s]*$/i.test(token)) continue;
    const numMatch = token.match(/#?(\d+)/);
    if (numMatch) {
      blockerIds.push(numMatch[1]);
    } else if (token) {
      blockerIds.push(token);
    }
  }

  return blockerIds;
}

/**
 * Maps GitHub issue state and labels to assembly line TicketStatus.
 */
export function mapGitHubIssueStatus(issue: GitHubIssue): TicketStatus {
  if (issue.state === "closed") {
    return "resolved";
  }

  const labelNames = (issue.labels || []).map((l) =>
    typeof l === "string" ? l.toLowerCase() : l.name.toLowerCase()
  );

  if (labelNames.includes(FACTORY_LABELS.RESOLVED)) {
    return "resolved";
  }
  if (labelNames.includes(FACTORY_LABELS.READY_FOR_HUMAN)) {
    return "ready-for-human";
  }
  if (labelNames.includes(FACTORY_LABELS.CLAIMED)) {
    return "claimed";
  }
  if (labelNames.includes(FACTORY_LABELS.READY)) {
    return "ready-for-agent";
  }

  return "ready-for-agent";
}

/**
 * Converts a GitHub issue to an assembly line Ticket object.
 */
export function gitHubIssueToTicket(issue: GitHubIssue): Ticket {
  const id = String(issue.number);
  const number = issue.number;
  const title = issue.title.trim();
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const status = mapGitHubIssueStatus(issue);
  const blockedBy = parseGitHubBlockedBy(issue.body);

  return {
    id,
    number,
    slug,
    title,
    status,
    blockedBy,
    filePath: issue.html_url ?? `https://github.com/issue/${issue.number}`,
  };
}

export class GitHubIssueTracker implements IssueTracker {
  public readonly id = "github" as const;
  public readonly client: GitHubClient;
  public activePullRequest: GitHubPullRequest | null = null;
  private cachedMilestones: Map<string, GitHubMilestone | null> = new Map();

  constructor(options: GitHubIssueTrackerOptions = {}) {
    this.client = options.client ?? new GitHubClient(options);
  }

  private async resolveMilestone(featureSlug: string): Promise<GitHubMilestone | null> {
    if (this.cachedMilestones.has(featureSlug)) {
      return this.cachedMilestones.get(featureSlug)!;
    }
    const milestone = await this.client.getMilestone(featureSlug);
    this.cachedMilestones.set(featureSlug, milestone);
    return milestone;
  }

  public async validatePreflight(
    workspaceDir: string,
    featureSlug: string,
    issueId?: string
  ): Promise<PreflightCheckResult> {
    const errors: string[] = [];

    // 1. Validate domain documentation (CONTEXT.md or GLOSSARY.md)
    const contextFile = findContextFile(workspaceDir);
    if (!contextFile) {
      errors.push(
        "Missing domain context documentation: 'CONTEXT.md' or 'GLOSSARY.md' not found at repository root or in domain paths. Please define the domain glossary in CONTEXT.md or GLOSSARY.md."
      );
    }

    // 2. Validate token presence
    if (!this.client.token) {
      errors.push("Missing GitHub token: GH_TOKEN or GITHUB_TOKEN environment variable is required.");
    }

    // 3. Validate remote issue (single-issue mode) or remote milestone (Autonomous Feature Batch)
    const issueNum = extractIssueNumber(issueId, featureSlug);
    if (issueNum !== null) {
      try {
        const issue = await this.client.getIssue(issueNum);
        if (issue.state === "closed") {
          errors.push(
            `Issue #${issueNum} is closed. Please reopen issue #${issueNum} or target an open issue.`
          );
        }
      } catch (err: any) {
        errors.push(
          `Failed to query GitHub issue #${issueNum} in ${this.client.owner}/${this.client.repo}: ${err?.message ?? String(err)}`
        );
      }
    } else {
      try {
        const milestone = await this.resolveMilestone(featureSlug);
        if (!milestone) {
          errors.push(
            `Milestone "${featureSlug}" not found in repository ${this.client.owner}/${this.client.repo}. Please ensure the GitHub Milestone exists and is open.`
          );
        } else if (milestone.state !== "open") {
          errors.push(
            `Milestone "${featureSlug}" is closed. Please reopen milestone "${featureSlug}" or target an open milestone.`
          );
        } else {
          const issues = await this.client.listIssuesForMilestone(milestone.number);
          if (issues.length === 0) {
            errors.push(
              `Milestone "${featureSlug}" has no issues assigned. Please create at least one GitHub Issue in milestone "${featureSlug}".`
            );
          } else {
            const openCandidateIssues = issues.filter(
              (i) => i.state === "open" && mapGitHubIssueStatus(i) !== "resolved"
            );
            if (openCandidateIssues.length === 0) {
              errors.push(
                `Milestone "${featureSlug}" has no open candidate issues. Please assign at least one open GitHub Issue to milestone "${featureSlug}".`
              );
            }
          }
        }
      } catch (err: any) {
        errors.push(
          `Failed to query GitHub repository ${this.client.owner}/${this.client.repo}: ${err?.message ?? String(err)}`
        );
      }
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  public async getFeatureSpec(
    _workspaceDir: string,
    featureSlug: string,
    issueId?: string
  ): Promise<string | undefined> {
    const issueNum = extractIssueNumber(issueId, featureSlug);
    if (issueNum !== null) {
      try {
        const issue = await this.client.getIssue(issueNum);
        return issue.body || undefined;
      } catch {
        return undefined;
      }
    }

    const milestone = await this.resolveMilestone(featureSlug);
    if (!milestone) {
      return undefined;
    }
    return milestone.description || undefined;
  }

  public async getTickets(
    _workspaceDir: string,
    featureSlug: string,
    issueId?: string
  ): Promise<Ticket[]> {
    const issueNum = extractIssueNumber(issueId, featureSlug);
    if (issueNum !== null) {
      const issue = await this.client.getIssue(issueNum);
      return [gitHubIssueToTicket(issue)];
    }

    const milestone = await this.resolveMilestone(featureSlug);
    if (!milestone) {
      return [];
    }

    const issues = await this.client.listIssuesForMilestone(milestone.number, "all");
    const tickets = issues.map(gitHubIssueToTicket);
    tickets.sort((a, b) => a.number - b.number);
    return tickets;
  }

  public async getFrontierTickets(
    workspaceDir: string,
    featureSlug: string,
    issueId?: string
  ): Promise<Ticket[]> {
    const tickets = await this.getTickets(workspaceDir, featureSlug, issueId);
    return getFrontierTickets(tickets);
  }


  private async updateTicketLabels(
    ticketNumber: number,
    labelsToAdd: string[],
    labelsToRemove: string[]
  ): Promise<string[]> {
    const current = await this.client.getIssue(ticketNumber);
    const existingLabels = (current.labels || []).map((l) =>
      typeof l === "string" ? l : l.name
    );

    const updated = existingLabels
      .filter((l) => !labelsToRemove.includes(l))
      .concat(labelsToAdd.filter((l) => !existingLabels.includes(l)));

    await this.client.updateIssue(ticketNumber, { labels: updated });
    return updated;
  }

  public async claimTicket(
    ticket: Ticket,
    _options?: ClaimTicketOptions
  ): Promise<void> {
    await this.updateTicketLabels(
      ticket.number,
      [FACTORY_LABELS.CLAIMED],
      [FACTORY_LABELS.READY, FACTORY_LABELS.READY_FOR_HUMAN]
    );
    ticket.status = "claimed";
  }

  public async resolveTicket(
    ticket: Ticket,
    options?: ResolveTicketOptions
  ): Promise<void> {
    await this.updateTicketLabels(
      ticket.number,
      [FACTORY_LABELS.RESOLVED],
      [FACTORY_LABELS.CLAIMED, FACTORY_LABELS.READY]
    );
    ticket.status = "resolved";

    const branch = options?.branch ? `**Branch:** \`${options.branch}\`\n\n` : "";
    const commit = options?.commitSha ? `**Commit:** \`${options.commitSha}\`\n\n` : "";
    const audit = options?.auditSummary ? `### Quality Gate Audit\n\n${options.auditSummary}\n` : "";

    const commentBody = [
      `## 🏭 Software Factory: Ticket Resolved`,
      branch + commit + audit,
    ].filter(Boolean).join("\n\n");

    try {
      await this.client.addComment(ticket.number, commentBody);
    } catch {
      // Non-fatal if comment fails
    }
  }

  public async escalateTicket(
    ticket: Ticket,
    options?: EscalateTicketOptions
  ): Promise<void> {
    await this.updateTicketLabels(
      ticket.number,
      [FACTORY_LABELS.READY_FOR_HUMAN],
      [FACTORY_LABELS.CLAIMED, FACTORY_LABELS.RESOLVED]
    );
    ticket.status = "ready-for-human";

    const branch = options?.branch ? `**Branch:** \`${options.branch}\`\n\n` : "";
    const diagnostics = options?.failureDiagnostics
      ? `### Failure Diagnostics\n\n${options.failureDiagnostics}\n`
      : "";

    const commentBody = [
      `## ⚠️ Software Factory: Ticket Needs Human Intervention`,
      branch + diagnostics,
    ].filter(Boolean).join("\n\n");

    try {
      await this.client.addComment(ticket.number, commentBody);
    } catch {
      // Non-fatal if comment fails
    }
  }

  private async findActivePullRequest(branch: string): Promise<GitHubPullRequest | null> {
    if (this.activePullRequest) {
      return this.activePullRequest;
    }
    try {
      const prs = await this.client.listPullRequests({ state: "open" });
      this.activePullRequest =
        prs.find(
          (p: any) =>
            p.head === branch ||
            p.head?.ref === branch ||
            p.head?.label === `${this.client.owner}:${branch}` ||
            p.head === `${this.client.owner}:${branch}`
        ) ?? null;
      return this.activePullRequest;
    } catch {
      return null;
    }
  }

  private appendResolvedWorkItem(body: string, ticket: Ticket): string {
    const itemRef = `Fixes #${ticket.number ?? ticket.id}`;
    if (body.includes(itemRef)) {
      return body;
    }
    if (body.includes("## Resolved Work Items")) {
      return body.replace(
        /## Resolved Work Items/,
        `## Resolved Work Items\n- ${itemRef}: ${ticket.title}`
      );
    }
    return (body.trim() ? body.trim() + "\n\n" : "") + `## Resolved Work Items\n- ${itemRef}: ${ticket.title}\n`;
  }

  public async initializeDeliveryGate(
    options: DeliveryGateInitOptions
  ): Promise<DeliveryGateInitResult | null> {
    const { branch, ticket } = options;
    const featureSlug = options.featureSlug ?? (ticket ? `issue-${ticket.number ?? ticket.id}` : "");

    let pr = await this.findActivePullRequest(branch);

    if (!pr) {
      let title = `feat: resolve #${ticket?.number ?? ticket?.id ?? "issue"} - ${ticket?.title ?? featureSlug}`;
      const issueNum = extractIssueNumber(undefined, featureSlug);
      if (issueNum === null && featureSlug) {
        try {
          const ms = await this.resolveMilestone(featureSlug);
          title = `feat(${featureSlug}): implement ${ms?.title ?? featureSlug}`;
        } catch {
          title = `feat(${featureSlug}): implement ${featureSlug}`;
        }
      } else if (ticket) {
        title = `feat: resolve #${ticket.number ?? ticket.id} - ${ticket.title}`;
      }

      const workItemLine = ticket
        ? `- Fixes #${ticket.number ?? ticket.id}: ${ticket.title}`
        : "";

      const body = [
        `## Summary`,
        `Autonomous feature implementation for ${featureSlug}.`,
        ``,
        `## Resolved Work Items`,
        workItemLine,
      ]
        .filter(Boolean)
        .join("\n");

      pr = await this.client.createPullRequest({
        title,
        body,
        head: branch,
        base: "main",
        draft: true,
      });
    } else if (ticket) {
      const updatedBody = this.appendResolvedWorkItem(pr.body || "", ticket);
      if (updatedBody !== (pr.body || "")) {
        pr = await this.client.updatePullRequest(pr.number, { body: updatedBody });
      }
    }

    this.activePullRequest = pr;
    return {
      pullRequestNumber: pr.number,
      pullRequestUrl: pr.html_url,
      branch,
    };
  }

  public async updateDeliveryGate(
    options: DeliveryGateUpdateOptions
  ): Promise<void> {
    const { branch, ticket, status, diagnostics } = options;

    const pr = await this.findActivePullRequest(branch);
    if (!pr) {
      return;
    }

    if (status === "resolved") {
      const updatedBody = this.appendResolvedWorkItem(pr.body || "", ticket);
      if (updatedBody !== (pr.body || "")) {
        this.activePullRequest = await this.client.updatePullRequest(pr.number, {
          body: updatedBody,
        });
      }
    } else if (status === "ready-for-human") {
      const alertBlock = [
        ``,
        `> [!WARNING]`,
        `> ⚠️ **Software Factory Alert: Execution Halted**`,
        `> Ticket #${ticket.number ?? ticket.id} (${ticket.title}) failed after exhausting retries and requires human intervention.`,
      ].join("\n");

      const updatedBody = (pr.body || "") + "\n" + alertBlock;
      this.activePullRequest = await this.client.updatePullRequest(pr.number, {
        body: updatedBody,
      });

      const alertComment = [
        `## ⚠️ Software Factory Alert: Ticket #${ticket.number ?? ticket.id} Needs Human Intervention`,
        ``,
        `- **Ticket**: #${ticket.number ?? ticket.id} - ${ticket.title}`,
        `- **Status**: \`factory:ready-for-human\``,
        `- **Branch**: \`${branch}\``,
        ``,
        `### Failure Diagnostics`,
        diagnostics || "Ticket failed after maximum retries.",
      ].join("\n");

      try {
        await this.client.addComment(pr.number, alertComment);
      } catch {
        // Non-fatal if comment fails
      }
    }
  }

  public async finalizeDeliveryGate(
    options: DeliveryGateFinalizeOptions
  ): Promise<DeliveryGateFinalizeResult | null> {
    const { branch, summary } = options;

    const pr = await this.findActivePullRequest(branch);

    if (pr) {
      this.activePullRequest = await this.client.updatePullRequest(pr.number, {
        draft: false,
      });

      if (summary) {
        try {
          await this.client.addComment(pr.number, summary);
        } catch {
          // Non-fatal if comment fails
        }
      }

      return {
        pullRequestNumber: this.activePullRequest.number,
        pullRequestUrl: this.activePullRequest.html_url,
        readyForReview: true,
      };
    }

    return null;
  }
}
