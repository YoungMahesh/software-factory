import * as fs from "node:fs";
import * as path from "node:path";
import { execSync } from "node:child_process";
import { type Provider, type Model } from "@earendil-works/pi-ai";
import {
  type ImplementationPlan,
  type ReviewVerdict,
  runPlannerAgent,
  runCoderAgent,
  runReviewerAgent,
} from "./harness.ts";
import { type VerificationResult, verifyWorkspace } from "./verifier.ts";
import { type Ticket, findContextFile } from "./preflight.ts";
import { updateTicketFile } from "./ticket.ts";
import { commitAndPushFeatureBranch, commitFailureDiagnostics } from "./git.ts";
import { resolveIssueTracker } from "./tracker/factory.ts";
import type { IssueTracker } from "./tracker/types.ts";
import { emitStageEvent } from "./events.ts";

export interface TicketLifecycleOptions {
  workspaceDir: string;
  featureSlug?: string;
  branch?: string;
  ticket: Ticket;
  tracker?: IssueTracker;
  maxRetries?: number;
  push?: boolean;
  provider?: Provider;
  model?: Model<any>;
  plannerRunner?: typeof runPlannerAgent;
  coderRunner?: typeof runCoderAgent;
  verifierRunner?: typeof verifyWorkspace;
  reviewerRunner?: typeof runReviewerAgent;
}

export interface TicketLifecycleResult {
  ticketId: string;
  ticketTitle?: string;
  status: "resolved" | "ready-for-human";
  retriesUsed: number;
  commitSha?: string;
  branch: string;
  plan?: ImplementationPlan;
  verification?: VerificationResult;
  review?: ReviewVerdict;
  error?: string;
}

export function formatReviewDiagnostics(verdict: ReviewVerdict): string {
  const parts: string[] = [
    `### Reviewer Rejection: REJECTED`,
    `**Summary**: ${verdict.summary}`,
  ];
  if (!verdict.specCompliance.passed) {
    parts.push(`**Spec Compliance Failure**: ${verdict.specCompliance.details}`);
  }
  if (!verdict.standardsCompliance.passed) {
    parts.push(`**Standards Compliance Failure**: ${verdict.standardsCompliance.details}`);
  }
  if (verdict.issues && verdict.issues.length > 0) {
    parts.push(`**Issues**:`);
    for (const issue of verdict.issues) {
      parts.push(
        `- [${issue.severity.toUpperCase()}] ${issue.description}${issue.file ? ` (${issue.file})` : ""}`
      );
    }
  }
  if (verdict.remediation) {
    parts.push(`**Remediation**: ${verdict.remediation}`);
  }
  return parts.join("\n\n");
}

/**
 * Executes the complete assembly line lifecycle for a single ticket:
 * Planner -> Coder -> Verifier -> Reviewer, with up to maxRetries self-correction loops.
 */
export async function runTicketLifecycle(
  options: TicketLifecycleOptions
): Promise<TicketLifecycleResult> {
  const { workspaceDir, ticket } = options;
  const featureSlug = options.featureSlug ?? (ticket ? `issue-${ticket.number ?? ticket.id}` : "");
  const maxRetries = options.maxRetries ?? 2;
  const push = options.push ?? true;
  const branch =
    options.branch ??
    (featureSlug ? `factory/${featureSlug}` : `factory/issue-${ticket.number ?? ticket.id}`);

  const tracker =
    options.tracker ??
    resolveIssueTracker({
      workspaceDir,
      featureSlug,
    });

  const plannerRunner = options.plannerRunner ?? runPlannerAgent;
  const coderRunner = options.coderRunner ?? runCoderAgent;
  const verifierRunner = options.verifierRunner ?? verifyWorkspace;
  const reviewerRunner = options.reviewerRunner ?? runReviewerAgent;

  // 1. Claim ticket via active issue tracker
  await tracker.claimTicket(ticket, { branch });

  // 2. Read spec and context documentation
  const specContent =
    (await tracker.getFeatureSpec(workspaceDir, featureSlug, ticket.id)) ?? undefined;

  const contextFilePath = findContextFile(workspaceDir);
  const contextContent = contextFilePath && fs.existsSync(contextFilePath)
    ? fs.readFileSync(contextFilePath, "utf-8")
    : undefined;

  // 3. Stage 1: Planner Agent
  emitStageEvent("PLANNER", { ticketId: ticket.id, title: ticket.title });
  console.log(`\n🧠 Stage 1: Planner Agent: Planning implementation for ticket #${ticket.number ?? ticket.id}...`);
  let plan: ImplementationPlan;
  try {
    const planResult = await plannerRunner({
      workspaceDir,
      ticket,
      specContent,
      contextContent,
      provider: options.provider,
      model: options.model,
    });
    plan = planResult.plan;
  } catch (planErr: any) {
    const errorMsg = planErr?.message ?? String(planErr);
    await tracker.escalateTicket(ticket, {
      branch,
      failureDiagnostics: `### Planner Stage Failure\n\n${errorMsg}`,
    });
    if (tracker.id === "local") {
      commitFailureDiagnostics({
        workspaceDir,
        featureSlug,
        branch,
        ticketId: ticket.id,
        ticketFilePath: ticket.filePath,
        push,
      });
    }
    return {
      ticketId: ticket.id,
      ticketTitle: ticket.title,
      status: "ready-for-human",
      retriesUsed: 0,
      branch,
      error: errorMsg,
    };
  }

  // Save plan.md if local tracker
  const scratchDir = path.join(workspaceDir, ".scratch", featureSlug);
  if (tracker.id === "local") {
    if (!fs.existsSync(scratchDir)) {
      fs.mkdirSync(scratchDir, { recursive: true });
    }
    const planPath = path.join(scratchDir, "plan.md");
    fs.writeFileSync(planPath, plan.rawContent, "utf-8");

    // Also archive ticket-specific plan
    const plansDir = path.join(scratchDir, "plans");
    if (!fs.existsSync(plansDir)) {
      fs.mkdirSync(plansDir, { recursive: true });
    }
    fs.writeFileSync(path.join(plansDir, `${ticket.id}-plan.md`), plan.rawContent, "utf-8");
  }

  // 4. Self-Correction Loop: Coder -> Verifier -> Reviewer (up to maxRetries)
  let lastDiagnostics: string | undefined = undefined;
  let lastVerification: VerificationResult | undefined = undefined;
  let lastReview: ReviewVerdict | undefined = undefined;
  let retriesUsed = 0;
  let passed = false;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    retriesUsed = attempt;

    // Stage 2: Coder Agent
    emitStageEvent("CODER", {
      ticketId: ticket.id,
      attempt: attempt + 1,
      maxAttempts: maxRetries + 1,
    });
    console.log(`\n💻 Stage 2: Coder Agent: Coding implementation (attempt ${attempt + 1}/${maxRetries + 1})...`);
    await coderRunner({
      workspaceDir,
      ticket,
      plan,
      diagnostics: lastDiagnostics,
      provider: options.provider,
      model: options.model,
    });

    // Stage 3: Deterministic Verifier
    emitStageEvent("VERIFIER", { ticketId: ticket.id });
    console.log(`\n🧪 Stage 3: Deterministic Verifier: Running verification suites...`);
    const verifierLogPath = path.join(scratchDir, "verification.md");
    const verification = await verifierRunner({
      workspacePath: workspaceDir,
      commands: plan.testCommands && plan.testCommands.length > 0 ? plan.testCommands : undefined,
      logPath: verifierLogPath,
    });
    lastVerification = verification;

    if (!verification.passed) {
      lastDiagnostics = `Deterministic Verification Failed:\n\n${verification.summary}`;
      continue;
    }

    // Stage 4: Reviewer Agent (only after verifier passes)
    emitStageEvent("REVIEWER", { ticketId: ticket.id });
    console.log(`\n🔍 Stage 4: Reviewer Agent: Reviewing diff against repo standards...`);
    let gitDiff = "";
    try {
      execSync("git add -N .", {
        cwd: workspaceDir,
        stdio: "ignore",
      });
      gitDiff = execSync("git diff HEAD", {
        cwd: workspaceDir,
        encoding: "utf-8",
      });
    } catch {
      try {
        gitDiff = execSync("git diff HEAD", {
          cwd: workspaceDir,
          encoding: "utf-8",
        });
      } catch {
        gitDiff = "";
      }
    }

    let verdict: ReviewVerdict;
    try {
      const reviewResult = await reviewerRunner({
        workspaceDir,
        ticket,
        plan,
        diff: gitDiff,
        provider: options.provider,
        model: options.model,
      });
      verdict = reviewResult.verdict;
    } catch (reviewErr: any) {
      lastDiagnostics = `### Reviewer Stage Failure\n\nFailed to complete review: ${reviewErr?.message ?? String(reviewErr)}`;
      continue;
    }
    lastReview = verdict;

    if (verdict.verdict === "rejected") {
      lastDiagnostics = formatReviewDiagnostics(verdict);
      continue;
    }

    // Both passed!
    passed = true;
    break;
  }

  // 4. Handle resolution or escalation
  if (passed) {
    const auditSummary = [
      plan?.rawContent ? `### Implementation Plan\n\n${plan.rawContent}` : "",
      lastVerification ? `### Deterministic Verification\n\n${lastVerification.summary}` : "### Deterministic Verification\n\nPASSED",
      lastReview
        ? `### Reviewer Verdict: ${lastReview.verdict.toUpperCase()}\n\n${lastReview.summary}`
        : "### Reviewer Verdict\n\nAPPROVED",
    ].filter(Boolean).join("\n\n");

    // Commit code changes first to obtain the commit SHA
    const initialCommit = commitAndPushFeatureBranch({
      workspaceDir,
      featureSlug,
      branch,
      ticketId: ticket.id,
      ticketTitle: ticket.title,
      push: tracker.id === "local" ? false : push,
    });

    // Update ticket via active issue tracker
    await tracker.resolveTicket(ticket, {
      branch,
      commitSha: initialCommit.commitSha,
      auditSummary,
    });

    // For local tracker, commit the updated ticket markdown file
    if (tracker.id === "local") {
      commitAndPushFeatureBranch({
        workspaceDir,
        featureSlug,
        branch,
        ticketId: ticket.id,
        ticketTitle: ticket.title,
        commitMessage: `docs(${featureSlug}): resolve ticket ${ticket.id} (${initialCommit.commitSha.slice(0, 7)})`,
        push,
      });
    }

    return {
      ticketId: ticket.id,
      ticketTitle: ticket.title,
      status: "resolved",
      retriesUsed,
      commitSha: initialCommit.commitSha,
      branch,
      plan,
      verification: lastVerification,
      review: lastReview,
    };
  } else {
    // Retries exhausted: escalate ticket via active issue tracker
    await tracker.escalateTicket(ticket, {
      branch,
      failureDiagnostics: lastDiagnostics || "Quality gate failed after maximum retries.",
    });

    if (tracker.id === "local") {
      commitFailureDiagnostics({
        workspaceDir,
        featureSlug,
        branch,
        ticketId: ticket.id,
        ticketFilePath: ticket.filePath,
        push,
      });
    }

    return {
      ticketId: ticket.id,
      ticketTitle: ticket.title,
      status: "ready-for-human",
      retriesUsed,
      branch,
      plan,
      verification: lastVerification,
      review: lastReview,
      error: lastDiagnostics,
    };
  }
}
