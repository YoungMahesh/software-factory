import type { Ticket } from "../preflight.ts";
import type {
  GitHubClient,
  GitHubMilestone,
  GitHubPullRequest,
} from "../github.ts";
import type {
  DeliveryGateInitOptions,
  DeliveryGateInitResult,
  DeliveryGateUpdateOptions,
  DeliveryGateFinalizeOptions,
  DeliveryGateFinalizeResult,
} from "./types.ts";
import { extractIssueNumber } from "./github-tracker.ts";

/**
 * Searches for an active open PR matching the target feature branch.
 */
export async function findActivePullRequest(
  client: GitHubClient,
  branch: string,
  cachedPr?: GitHubPullRequest | null
): Promise<GitHubPullRequest | null> {
  if (cachedPr) {
    return cachedPr;
  }
  try {
    const prs = await client.listPullRequests({ state: "open" });
    return (
      prs.find(
        (p: any) =>
          p.head === branch ||
          p.head?.ref === branch ||
          p.head?.label === `${client.owner}:${branch}` ||
          p.head === `${client.owner}:${branch}`
      ) ?? null
    );
  } catch {
    return null;
  }
}

/**
 * Appends resolved work item link to the PR description body.
 */
export function appendResolvedWorkItem(body: string, ticket: Ticket): string {
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
  return (
    (body.trim() ? body.trim() + "\n\n" : "") +
    `## Resolved Work Items\n- ${itemRef}: ${ticket.title}\n`
  );
}

/**
 * Formats markdown alert blocks and comments for tickets requiring human intervention.
 */
export function formatDeliveryGateAlert(
  ticket: Ticket,
  branch: string,
  diagnostics?: string
): { alertBlock: string; alertComment: string } {
  const ticketRef = `#${ticket.number ?? ticket.id}`;
  const alertBlock = [
    ``,
    `> [!WARNING]`,
    `> ⚠️ **Software Factory Alert: Execution Halted**`,
    `> Ticket ${ticketRef} (${ticket.title}) failed after exhausting retries and requires human intervention.`,
  ].join("\n");

  const alertComment = [
    `## ⚠️ Software Factory Alert: Ticket ${ticketRef} Needs Human Intervention`,
    ``,
    `- **Ticket**: ${ticketRef} - ${ticket.title}`,
    `- **Status**: \`factory:ready-for-human\``,
    `- **Branch**: \`${branch}\``,
    ``,
    `### Failure Diagnostics`,
    diagnostics || "Ticket failed after maximum retries.",
  ].join("\n");

  return { alertBlock, alertComment };
}

/**
 * Initializes delivery gate by creating or updating a draft pull request.
 */
export async function initDeliveryGate(
  client: GitHubClient,
  options: DeliveryGateInitOptions,
  resolveMilestone: (slug: string) => Promise<GitHubMilestone | null>,
  currentPr?: GitHubPullRequest | null
): Promise<{ pr: GitHubPullRequest; result: DeliveryGateInitResult }> {
  const { branch, ticket } = options;
  const featureSlug =
    options.featureSlug ?? (ticket ? `issue-${ticket.number ?? ticket.id}` : "");

  let pr = await findActivePullRequest(client, branch, currentPr);

  if (!pr) {
    let title = `feat: resolve #${ticket?.number ?? ticket?.id ?? "issue"} - ${ticket?.title ?? featureSlug}`;
    const issueNum = extractIssueNumber(undefined, featureSlug);
    if (issueNum === null && featureSlug) {
      try {
        const ms = await resolveMilestone(featureSlug);
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

    pr = await client.createPullRequest({
      title,
      body,
      head: branch,
      base: "main",
      draft: true,
    });
  } else if (ticket) {
    const updatedBody = appendResolvedWorkItem(pr.body || "", ticket);
    if (updatedBody !== (pr.body || "")) {
      pr = await client.updatePullRequest(pr.number, { body: updatedBody });
    }
  }

  return {
    pr,
    result: {
      pullRequestNumber: pr.number,
      pullRequestUrl: pr.html_url,
      branch,
      title: pr.title,
    },
  };
}

/**
 * Updates delivery gate PR status and comments on ticket resolution or escalation.
 */
export async function updateDeliveryGate(
  client: GitHubClient,
  options: DeliveryGateUpdateOptions,
  currentPr?: GitHubPullRequest | null
): Promise<GitHubPullRequest | null> {
  const { branch, ticket, status, diagnostics } = options;

  let pr = await findActivePullRequest(client, branch, currentPr);
  if (!pr) {
    return null;
  }

  if (status === "resolved") {
    const updatedBody = appendResolvedWorkItem(pr.body || "", ticket);
    if (updatedBody !== (pr.body || "")) {
      pr = await client.updatePullRequest(pr.number, {
        body: updatedBody,
      });
    }
  } else if (status === "ready-for-human") {
    const { alertBlock, alertComment } = formatDeliveryGateAlert(
      ticket,
      branch,
      diagnostics
    );

    const updatedBody = (pr.body || "") + "\n" + alertBlock;
    pr = await client.updatePullRequest(pr.number, {
      body: updatedBody,
    });

    try {
      await client.addComment(pr.number, alertComment);
    } catch {
      // Non-fatal if comment fails
    }
  }

  return pr;
}

/**
 * Marks the delivery gate PR as ready for review and posts optional summary comments.
 */
export async function finalizeDeliveryGate(
  client: GitHubClient,
  options: DeliveryGateFinalizeOptions,
  currentPr?: GitHubPullRequest | null
): Promise<{ pr: GitHubPullRequest; result: DeliveryGateFinalizeResult } | null> {
  const { branch, summary } = options;

  let pr = await findActivePullRequest(client, branch, currentPr);

  if (pr) {
    pr = await client.updatePullRequest(pr.number, {
      draft: false,
    });

    if (summary) {
      try {
        await client.addComment(pr.number, summary);
      } catch {
        // Non-fatal if comment fails
      }
    }

    return {
      pr,
      result: {
        pullRequestNumber: pr.number,
        pullRequestUrl: pr.html_url,
        branch,
        title: pr.title,
        readyForReview: true,
      },
    };
  }

  return null;
}

/**
 * Manages delivery gate lifecycle for GitHub issue tracker.
 */
export class GitHubDeliveryGateManager {
  public activePullRequest: GitHubPullRequest | null = null;
  private client: GitHubClient;
  private resolveMilestone: (slug: string) => Promise<GitHubMilestone | null>;

  constructor(
    client: GitHubClient,
    resolveMilestone: (slug: string) => Promise<GitHubMilestone | null>
  ) {
    this.client = client;
    this.resolveMilestone = resolveMilestone;
  }

  public async findActivePullRequest(branch: string): Promise<GitHubPullRequest | null> {
    const pr = await findActivePullRequest(this.client, branch, this.activePullRequest);
    this.activePullRequest = pr;
    return pr;
  }

  public async initDeliveryGate(
    options: DeliveryGateInitOptions
  ): Promise<DeliveryGateInitResult | null> {
    const res = await initDeliveryGate(
      this.client,
      options,
      this.resolveMilestone,
      this.activePullRequest
    );
    this.activePullRequest = res.pr;
    return res.result;
  }

  public async updateDeliveryGate(
    options: DeliveryGateUpdateOptions
  ): Promise<void> {
    const pr = await updateDeliveryGate(
      this.client,
      options,
      this.activePullRequest
    );
    if (pr) {
      this.activePullRequest = pr;
    }
  }

  public async finalizeDeliveryGate(
    options: DeliveryGateFinalizeOptions
  ): Promise<DeliveryGateFinalizeResult | null> {
    const res = await finalizeDeliveryGate(
      this.client,
      options,
      this.activePullRequest
    );
    if (res) {
      this.activePullRequest = res.pr;
      return res.result;
    }
    return null;
  }
}
