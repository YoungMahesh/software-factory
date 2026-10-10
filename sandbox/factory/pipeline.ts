import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { type Provider, type Model } from "@earendil-works/pi-ai";
import {
  assertPreflightAsync,
  type Ticket,
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
import { resolveIssueTracker } from "./tracker/factory.ts";
import type { IssueTracker, TrackerType } from "./tracker/types.ts";

export interface PipelineOptions {
  workspaceDir: string;
  featureSlug?: string;
  issueId?: string;
  branch?: string;
  tracker?: IssueTracker;
  trackerType?: TrackerType;
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
  const { workspaceDir } = options;
  const featureSlug =
    options.featureSlug ?? (options.issueId ? `issue-${options.issueId.trim()}` : "");

  const branch =
    options.branch ??
    (options.featureSlug
      ? `factory/${options.featureSlug}`
      : `factory/issue-${options.issueId?.trim()}`);

  // Resolve issue tracker abstraction
  const tracker =
    options.tracker ??
    resolveIssueTracker({
      workspaceDir,
      featureSlug,
      trackerType: options.trackerType,
    });

  // 1. Stage 0: Pre-flight Guard Check on checked out branch
  console.log(`\n🛡️  Stage 0: Pre-flight Guard Check on workspace...`);
  await assertPreflightAsync(workspaceDir, featureSlug, {
    tracker,
    trackerType: options.trackerType,
    issueId: options.issueId,
  });

  // 2. Ensure Feature Branch upon checkout per ADR 0028, ADR 0033 & CONTEXT.md
  ensureFeatureBranch({
    workspaceDir,
    featureSlug,
    branch,
  });

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
  let deliveryGateInitialized = false;

  if (options.issueId) {
    // Mode A: Targeted single-ticket mode
    const tickets = await tracker.getTickets(workspaceDir, featureSlug, options.issueId);
    const targetId = options.issueId.trim().replace(/^#/, "");
    const targetTicket = tickets.find(
      (t) =>
        t.id === targetId ||
        String(t.number) === targetId ||
        t.slug === targetId ||
        t.id === options.issueId?.trim()
    );

    if (!targetTicket) {
      throw new Error(
        `Ticket "${options.issueId}" not found in issue tracker`
      );
    }

    const lifecycleResult = await runTicketLifecycle({
      workspaceDir,
      featureSlug,
      branch,
      ticket: targetTicket,
      tracker,
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

    if (lifecycleResult.status === "resolved") {
      if (tracker.initializeDeliveryGate) {
        await tracker.initializeDeliveryGate({
          workspaceDir,
          featureSlug,
          branch,
          ticket: targetTicket,
        });
        deliveryGateInitialized = true;
      }
    } else {
      haltedOnError = true;
      if (tracker.updateDeliveryGate) {
        await tracker.updateDeliveryGate({
          workspaceDir,
          featureSlug,
          branch,
          ticket: targetTicket,
          status: "ready-for-human",
          diagnostics: lifecycleResult.error,
        });
      }
    }
  } else {
    // Mode B: Autonomous Feature Batch across unblocked frontier tickets
    while (true) {
      const frontierTickets = await tracker.getFrontierTickets(workspaceDir, featureSlug);
      const nextTicket = frontierTickets.length > 0 ? frontierTickets[0] : null;
      if (!nextTicket) {
        // Frontier is empty (all unblocked tickets processed)
        break;
      }

      const lifecycleResult = await runTicketLifecycle({
        workspaceDir,
        featureSlug,
        branch,
        ticket: nextTicket,
        tracker,
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

      if (lifecycleResult.status === "resolved") {
        if (!deliveryGateInitialized) {
          if (tracker.initializeDeliveryGate) {
            await tracker.initializeDeliveryGate({
              workspaceDir,
              featureSlug,
              branch,
              ticket: nextTicket,
            });
          }
          deliveryGateInitialized = true;
        } else {
          if (tracker.updateDeliveryGate) {
            await tracker.updateDeliveryGate({
              workspaceDir,
              featureSlug,
              branch,
              ticket: nextTicket,
              status: "resolved",
            });
          }
        }
      } else {
        // Persistent failure after retries exhausted: halt batch immediately (fail-fast)
        haltedOnError = true;
        if (tracker.updateDeliveryGate) {
          await tracker.updateDeliveryGate({
            workspaceDir,
            featureSlug,
            branch,
            ticket: nextTicket,
            status: "ready-for-human",
            diagnostics: lifecycleResult.error,
          });
        }
        break;
      }
    }
  }

  const allMilestoneOrIssueTickets = options.featureSlug
    ? await tracker.getTickets(workspaceDir, featureSlug)
    : await tracker.getTickets(workspaceDir, featureSlug, options.issueId);

  const allResolved =
    !haltedOnError &&
    allMilestoneOrIssueTickets.length > 0 &&
    allMilestoneOrIssueTickets.every((t) => t.status === "resolved");

  const summary = formatPipelineSummary(
    featureSlug,
    branch,
    executedTickets,
    haltedOnError
  );

  // When all frontier tickets in milestone are resolved, finalize PR
  if (allResolved && tracker.finalizeDeliveryGate) {
    const executedTicketObjects: Ticket[] = executedTickets.map((t) => ({
      id: t.ticketId,
      number: parseInt(t.ticketId, 10) || 0,
      slug: t.ticketId,
      title: t.ticketTitle ?? t.ticketId,
      filePath: "",
      status: t.status,
      blockedBy: [],
    }));

    await tracker.finalizeDeliveryGate({
      workspaceDir,
      featureSlug,
      branch,
      tickets: executedTicketObjects,
      summary,
    });
  }

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
  tracker?: string;
  push: boolean;
} {
  const args = process.argv.slice(2);
  let workspace = process.cwd();
  let feature = "";
  let issue: string | undefined;
  let model: string | undefined;
  let tracker: string | undefined;
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
    } else if (arg === "--tracker" || arg === "-t") {
      tracker = args[++i];
    } else if (arg === "--no-push") {
      push = false;
    }
  }

  if (!feature && issue) {
    feature = `issue-${issue.trim().replace(/^#/, "")}`;
  }

  if (!feature) {
    console.error("Usage: node pipeline.ts --feature <slug> [--workspace <dir>] [--issue <id>] [--model <model>] [--tracker <github|local>] [--no-push]");
    process.exit(1);
  }

  return { workspace, feature, issue, model, tracker, push };
}

const isDirectRun =
  process.argv[1] &&
  (import.meta.url === pathToFileURL(process.argv[1]).href ||
    path.basename(process.argv[1]) === "pipeline.ts" ||
    path.basename(process.argv[1]) === "pipeline.js");

if (isDirectRun) {
  const { workspace, feature, issue, model, tracker, push } = parseCliArgs();
  console.log(`🚀 Launching Assembly Line Pipeline for feature "${feature}" in ${workspace}...`);

  runAssemblyLinePipeline({
    workspaceDir: workspace,
    featureSlug: feature,
    issueId: issue,
    modelId: model,
    trackerType: (tracker as TrackerType) || undefined,
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
