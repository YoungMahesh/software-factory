import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { type Provider, type Model } from "@earendil-works/pi-ai";
import {
  assertPreflight,
  parseTickets,
  getNextFrontierTicket,
} from "./preflight.ts";
import { ensureFeatureBranch } from "./git.ts";
import {
  runTicketLifecycle,
  type TicketLifecycleResult,
} from "./lifecycle.ts";
import { createOpenCodeGoProvider, getFactoryModel } from "./provider.ts";
import {
  runPlannerAgent,
  runCoderAgent,
  runReviewerAgent,
} from "./harness.ts";
import { verifyWorkspace } from "./verifier.ts";

export interface PipelineOptions {
  workspaceDir: string;
  featureSlug: string;
  issueId?: string;
  maxRetries?: number;
  modelId?: string;
  push?: boolean;
  provider?: Provider;
  model?: Model<any>;
  plannerRunner?: typeof runPlannerAgent;
  coderRunner?: typeof runCoderAgent;
  verifierRunner?: typeof verifyWorkspace;
  reviewerRunner?: typeof runReviewerAgent;
}

export interface PipelineResult {
  featureSlug: string;
  branch: string;
  preflightPassed: boolean;
  executedTickets: TicketLifecycleResult[];
  allResolved: boolean;
  haltedOnError: boolean;
  summary: string;
}

export function formatPipelineSummary(
  featureSlug: string,
  branch: string,
  executedTickets: TicketLifecycleResult[],
  haltedOnError: boolean
): string {
  const lines: string[] = [
    `# Software Factory Assembly Line Summary: ${featureSlug}`,
    ``,
    `- **Feature**: \`${featureSlug}\``,
    `- **Branch**: \`${branch}\``,
    `- **Status**: ${haltedOnError ? "HALTED (Self-Correction Exhausted)" : "SUCCESS"}`,
    `- **Executed Tickets**: ${executedTickets.length}`,
    ``,
    `| Ticket | Status | Retries | Commit | Details |`,
    `| :--- | :--- | :--- | :--- | :--- |`,
  ];

  for (const t of executedTickets) {
    const statusBadge = t.status === "resolved" ? "RESOLVED" : "READY-FOR-HUMAN";
    const commit = t.commitSha ? `\`${t.commitSha.slice(0, 7)}\`` : "-";
    const details = t.error ? t.error.split("\n")[0].slice(0, 50) : "Quality gate passed";
    lines.push(`| ${t.ticketId} | ${statusBadge} | ${t.retriesUsed} | ${commit} | ${details} |`);
  }

  return lines.join("\n");
}

/**
 * Orchestrates the sequential assembly line pipeline:
 * Pre-flight -> Git Branch -> Ticket Discovery -> Assembly Line Stages -> Self-Correction.
 */
export async function runAssemblyLinePipeline(
  options: PipelineOptions
): Promise<PipelineResult> {
  const { workspaceDir, featureSlug } = options;

  // 1. Ensure Feature Branch (factory/<feature>) upon checkout per ADR 0028 & CONTEXT.md
  const branch = ensureFeatureBranch({
    workspaceDir,
    featureSlug,
  });

  // 2. Stage 0: Pre-flight Guard Check on checked out branch
  assertPreflight(workspaceDir, featureSlug);

  // 3. Resolve Provider & Model
  let provider = options.provider;
  let model = options.model;

  if (!provider && !options.plannerRunner) {
    try {
      provider = createOpenCodeGoProvider();
    } catch {
      // If no provider could be created ambiently, will throw when runner is called
    }
  }

  if (provider && !model) {
    model = getFactoryModel(options.modelId, provider);
  }

  const executedTickets: TicketLifecycleResult[] = [];
  let haltedOnError = false;

  if (options.issueId) {
    // Mode A: Targeted single-ticket mode
    const tickets = parseTickets(workspaceDir, featureSlug);
    const targetId = options.issueId.trim();
    const targetTicket = tickets.find(
      (t) =>
        t.id === targetId ||
        String(t.number) === targetId ||
        t.slug === targetId
    );

    if (!targetTicket) {
      throw new Error(
        `Ticket "${options.issueId}" not found in .scratch/${featureSlug}/issues/`
      );
    }

    const lifecycleResult = await runTicketLifecycle({
      workspaceDir,
      featureSlug,
      ticket: targetTicket,
      maxRetries: options.maxRetries,
      push: options.push,
      provider,
      model,
      plannerRunner: options.plannerRunner,
      coderRunner: options.coderRunner,
      verifierRunner: options.verifierRunner,
      reviewerRunner: options.reviewerRunner,
    });

    executedTickets.push(lifecycleResult);
    if (lifecycleResult.status !== "resolved") {
      haltedOnError = true;
    }
  } else {
    // Mode B: Autonomous Feature Batch across unblocked frontier tickets
    while (true) {
      const tickets = parseTickets(workspaceDir, featureSlug);
      const nextTicket = getNextFrontierTicket(tickets);
      if (!nextTicket) {
        // Frontier is empty (all unblocked tickets processed)
        break;
      }

      const lifecycleResult = await runTicketLifecycle({
        workspaceDir,
        featureSlug,
        ticket: nextTicket,
        maxRetries: options.maxRetries,
        push: options.push,
        provider,
        model,
        plannerRunner: options.plannerRunner,
        coderRunner: options.coderRunner,
        verifierRunner: options.verifierRunner,
        reviewerRunner: options.reviewerRunner,
      });

      executedTickets.push(lifecycleResult);

      if (lifecycleResult.status !== "resolved") {
        // Persistent failure after 2 retries: halt batch immediately (fail-fast)
        haltedOnError = true;
        break;
      }
    }
  }

  const allResolved =
    !haltedOnError &&
    executedTickets.length > 0 &&
    executedTickets.every((t) => t.status === "resolved");

  const summary = formatPipelineSummary(
    featureSlug,
    branch,
    executedTickets,
    haltedOnError
  );

  return {
    featureSlug,
    branch,
    preflightPassed: true,
    executedTickets,
    allResolved,
    haltedOnError,
    summary,
  };
}

// CLI entrypoint if executed directly via node
function parseCliArgs(): {
  workspace: string;
  feature: string;
  issue?: string;
  model?: string;
  push: boolean;
} {
  const args = process.argv.slice(2);
  let workspace = process.cwd();
  let feature = "";
  let issue: string | undefined;
  let model: string | undefined;
  let push = true;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--workspace" || arg === "-w") {
      workspace = path.resolve(args[++i]);
    } else if (arg === "--feature" || arg === "-f") {
      feature = args[++i];
    } else if (arg === "--issue" || arg === "-i") {
      issue = args[++i];
    } else if (arg === "--model" || arg === "-m") {
      model = args[++i];
    } else if (arg === "--no-push") {
      push = false;
    }
  }

  if (!feature) {
    console.error("Usage: node pipeline.ts --feature <slug> [--workspace <dir>] [--issue <id>] [--model <model>] [--no-push]");
    process.exit(1);
  }

  return { workspace, feature, issue, model, push };
}

const isDirectRun =
  process.argv[1] &&
  (import.meta.url === pathToFileURL(process.argv[1]).href ||
    path.basename(process.argv[1]) === "pipeline.ts" ||
    path.basename(process.argv[1]) === "pipeline.js");

if (isDirectRun) {
  const { workspace, feature, issue, model, push } = parseCliArgs();
  console.log(`🚀 Launching Assembly Line Pipeline for feature "${feature}" in ${workspace}...`);

  runAssemblyLinePipeline({
    workspaceDir: workspace,
    featureSlug: feature,
    issueId: issue,
    modelId: model,
    push,
  })
    .then((result) => {
      console.log("\n" + result.summary);
      if (result.haltedOnError) {
        console.error("❌ Assembly line pipeline halted on error.");
        process.exit(1);
      } else {
        console.log("🎉 Assembly line pipeline completed successfully!");
        process.exit(0);
      }
    })
    .catch((err) => {
      console.error("❌ Fatal pipeline error:", err);
      process.exit(1);
    });
}
