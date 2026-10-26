import * as fs from "node:fs";
import { Agent } from "@earendil-works/pi-agent-core";
import { type Model } from "@earendil-works/pi-ai";
import { getFactoryModel, createOpenCodeGoProvider } from "../provider.ts";
import {
  createRoleTools,
  assertRoleToolPrivileges,
} from "../tools.ts";
import {
  AgentEventStream,
  stripThinkTags,
  type TelemetryStage,
} from "../events.ts";
import {
  PLANNER_SYSTEM_PROMPT,
  CODER_SYSTEM_PROMPT,
  REVIEWER_SYSTEM_PROMPT,
} from "./prompts.ts";
import {
  parseImplementationPlan,
  parseReviewVerdict,
} from "./parser.ts";
import {
  type ImplementationPlan,
  type ReviewVerdict,
  type TicketInput,
  type StageAgentCommonOptions,
  type PlannerOptions,
  type CoderOptions,
  type ReviewerOptions,
  HarnessExecutionError,
} from "./types.ts";

function extractAssistantText(messages: any[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role === "assistant") {
      if (typeof msg.content === "string") return stripThinkTags(msg.content);
      if (Array.isArray(msg.content)) {
        const textParts = msg.content
          .filter((c: any) => c.type === "text" && c.text)
          .map((c: any) => c.text);
        if (textParts.length > 0) return stripThinkTags(textParts.join("\n"));
      }
    }
  }
  return "";
}

function resolveTicketContent(ticket: TicketInput | string): { id: string; title?: string; content: string } {
  if (typeof ticket === "string") {
    return { id: "ticket", content: ticket };
  }
  let content = ticket.content;
  if (!content && ticket.filePath && fs.existsSync(ticket.filePath)) {
    try {
      content = fs.readFileSync(ticket.filePath, "utf-8");
    } catch {
      // ignore
    }
  }
  return {
    id: ticket.id,
    title: ticket.title,
    content: content || "",
  };
}

function resolveAgentContext(options: StageAgentCommonOptions) {
  const provider =
    options.provider ??
    (options.streamFn ? undefined : createOpenCodeGoProvider());
  const model = options.model ?? getFactoryModel(undefined, provider);
  const streamFn =
    options.streamFn ??
    (provider
      ? (m: Model<any>, ctx: any, opt: any) => provider.streamSimple(m, ctx, opt)
      : undefined);

  if (!streamFn) {
    throw new HarnessExecutionError("No stream function available for agent execution.");
  }

  return { model, streamFn };
}

function assertAgentSuccess(messages: any[]): void {
  const lastAssistant = messages.slice().reverse().find((m: any) => m.role === "assistant");
  if (lastAssistant && lastAssistant.stopReason === "error") {
    throw new HarnessExecutionError(
      `Agent execution failed: ${lastAssistant.errorMessage || "Unknown agent error"}`
    );
  }
}

async function runAgentPromptWithTelemetry(
  agent: Agent,
  stage: TelemetryStage,
  prompt: string,
  options: StageAgentCommonOptions
): Promise<void> {
  const eventStream = new AgentEventStream({
    stage,
    stream: options.telemetryStream,
    workspaceDir: options.workspaceDir,
  });
  const telemetry = eventStream.subscribe(agent);

  try {
    await agent.prompt(prompt);
    assertAgentSuccess(agent.state.messages);
  } finally {
    telemetry.flush();
    telemetry.unsubscribe();
  }
}

/**
 * Runs the read-only Planner Agent to explore the repository and draft a structured plan.
 */
export async function runPlannerAgent(options: PlannerOptions): Promise<{
  plan: ImplementationPlan;
  messages: any[];
}> {
  const tools = options.tools ?? createRoleTools("planner", options.workspaceDir);
  assertRoleToolPrivileges("planner", tools.map((t) => t.name));

  const { model, streamFn } = resolveAgentContext(options);

  const ticketObj = resolveTicketContent(options.ticket);

  const agent = new Agent({
    initialState: {
      systemPrompt: PLANNER_SYSTEM_PROMPT,
      model,
      tools,
      messages: [],
    },
    streamFn,
  });

  const promptParts: string[] = [
    `# Ticket: ${ticketObj.title ?? ticketObj.id}`,
    ticketObj.content,
  ];

  if (options.specContent) {
    promptParts.push("# Feature Specification", options.specContent);
  }
  if (options.contextContent) {
    promptParts.push("# Domain Context (CONTEXT.md)", options.contextContent);
  }
  if (options.adrsContent) {
    promptParts.push("# Architectural Decision Records (docs/adr/)", options.adrsContent);
  }

  promptParts.push(
    "Please inspect the repository and draft a structured implementation plan with affectedFiles and testCommands adhering strictly to all accepted ADRs."
  );

  await runAgentPromptWithTelemetry(agent, "PLANNER", promptParts.join("\n\n"), options);

  const responseText = extractAssistantText(agent.state.messages);
  const plan = parseImplementationPlan(responseText, ticketObj.id);

  return {
    plan,
    messages: agent.state.messages,
  };
}

/**
 * Runs the Coder Agent with editing and bash execution capabilities.
 */
export async function runCoderAgent(options: CoderOptions): Promise<{
  summary: string;
  messages: any[];
}> {
  const tools = options.tools ?? createRoleTools("coder", options.workspaceDir);
  assertRoleToolPrivileges("coder", tools.map((t) => t.name));

  const { model, streamFn } = resolveAgentContext(options);

  const ticketObj = resolveTicketContent(options.ticket);

  const planText =
    typeof options.plan === "string" ? options.plan : JSON.stringify(options.plan, null, 2);

  const agent = new Agent({
    initialState: {
      systemPrompt: CODER_SYSTEM_PROMPT,
      model,
      tools,
      messages: [],
    },
    streamFn,
  });

  const promptParts: string[] = [
    `# Ticket: ${ticketObj.title ?? ticketObj.id}`,
    ticketObj.content,
    "# Implementation Plan",
    planText,
  ];

  if (options.diagnostics) {
    promptParts.push(
      "# Previous Run Failure Diagnostics (Self-Correction)",
      options.diagnostics,
      "Please review the diagnostics above and fix the failing tests or review issues."
    );
  } else {
    promptParts.push("Please implement the requested changes and any required reproduction tests.");
  }

  await runAgentPromptWithTelemetry(agent, "CODER", promptParts.join("\n\n"), options);

  const responseText = extractAssistantText(agent.state.messages);
  return {
    summary: responseText,
    messages: agent.state.messages,
  };
}

/**
 * Runs the read-only Reviewer Agent to inspect diffs and evaluate code standards.
 */
export async function runReviewerAgent(options: ReviewerOptions): Promise<{
  verdict: ReviewVerdict;
  messages: any[];
}> {
  const tools = options.tools ?? createRoleTools("reviewer", options.workspaceDir);
  assertRoleToolPrivileges("reviewer", tools.map((t) => t.name));

  const { model, streamFn } = resolveAgentContext(options);

  const ticketObj = resolveTicketContent(options.ticket);

  const planText =
    typeof options.plan === "string" ? options.plan : JSON.stringify(options.plan, null, 2);

  const agent = new Agent({
    initialState: {
      systemPrompt: REVIEWER_SYSTEM_PROMPT,
      model,
      tools,
      messages: [],
    },
    streamFn,
  });

  const promptParts: string[] = [
    `# Ticket: ${ticketObj.title ?? ticketObj.id}`,
    ticketObj.content,
    "# Implementation Plan",
    planText,
  ];

  if (options.contextContent) {
    promptParts.push("# Domain Context (CONTEXT.md)", options.contextContent);
  }
  if (options.adrsContent) {
    promptParts.push("# Architectural Decision Records (docs/adr/)", options.adrsContent);
  }
  if (options.visualSummary) {
    promptParts.push("# Visual QA Evidence", options.visualSummary);
  }

  if (options.diff) {
    promptParts.push("# Git Diff", options.diff);
  } else {
    promptParts.push("Please inspect the git diff using your diff inspection tool.");
  }

  promptParts.push("Review the implementation against the ticket, repo standards, and accepted ADRs in docs/adr/, and emit your review verdict.");

  await runAgentPromptWithTelemetry(agent, "REVIEWER", promptParts.join("\n\n"), options);

  const responseText = extractAssistantText(agent.state.messages);
  const verdict = parseReviewVerdict(responseText);

  return {
    verdict,
    messages: agent.state.messages,
  };
}
