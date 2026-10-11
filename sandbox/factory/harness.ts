import * as fs from "node:fs";
import { Agent } from "@earendil-works/pi-agent-core";
import { type Model, type Provider } from "@earendil-works/pi-ai";
import { getFactoryModel, createOpenCodeGoProvider } from "./provider.ts";
import {
  createRoleTools,
  assertRoleToolPrivileges,
  LeastPrivilegeViolationError,
} from "./tools.ts";
import {
  AgentEventStream,
  stripThinkTags,
  type TelemetryStage,
} from "./events.ts";

export interface ImplementationPlan {
  ticketId: string;
  summary: string;
  affectedFiles: string[];
  testCommands: string[];
  steps: string[];
  rationale?: string;
  rawContent: string;
}

export interface ReviewIssue {
  severity: "blocker" | "warning" | "suggestion";
  description: string;
  file?: string;
}

export interface ReviewVerdict {
  verdict: "approved" | "rejected";
  summary: string;
  specCompliance: {
    passed: boolean;
    details: string;
  };
  standardsCompliance: {
    passed: boolean;
    details: string;
  };
  issues: ReviewIssue[];
  remediation?: string;
  rawContent: string;
}

export class PlanParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PlanParseError";
  }
}

export class ReviewParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReviewParseError";
  }
}

export class HarnessExecutionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HarnessExecutionError";
  }
}

/**
 * Parses an implementation plan from JSON or markdown text.
 * Requires non-empty affectedFiles and testCommands.
 */
export function parseImplementationPlan(
  content: string,
  fallbackTicketId: string = "unknown"
): ImplementationPlan {
  const trimmed = content.trim();

  // Try extracting from all JSON blocks first
  const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)\s*```/g;
  let codeMatch: RegExpExecArray | null;
  while ((codeMatch = codeBlockRegex.exec(trimmed)) !== null) {
    try {
      const parsed = JSON.parse(codeMatch[1]);
      if (typeof parsed === "object" && parsed !== null) {
        const ticketId = String(parsed.ticketId || fallbackTicketId);
        const summary = String(parsed.summary || "");
        const rawFiles = parsed.affectedFiles ?? parsed.affected_files ?? parsed.files ?? parsed.targetFiles;
        const affectedFiles = Array.isArray(rawFiles)
          ? rawFiles.map(String).map((f: string) => f.trim()).filter(Boolean)
          : [];
        const rawCmds = parsed.testCommands ?? parsed.test_commands ?? parsed.tests ?? parsed.commands;
        const testCommands = Array.isArray(rawCmds)
          ? rawCmds.map(String).map((c: string) => c.trim()).filter(Boolean)
          : [];
        const rawSteps = parsed.steps ?? parsed.tasks ?? parsed.plan;
        const steps = Array.isArray(rawSteps)
          ? rawSteps.map(String).map((s: string) => s.trim()).filter(Boolean)
          : [];
        const rationale = parsed.rationale ? String(parsed.rationale) : undefined;

        const hasPlanFields =
          parsed.affectedFiles !== undefined ||
          parsed.affected_files !== undefined ||
          parsed.files !== undefined ||
          parsed.testCommands !== undefined ||
          parsed.test_commands !== undefined;

        if (hasPlanFields) {
          if (affectedFiles.length === 0) {
            throw new PlanParseError("Implementation plan must specify at least one affected file in affectedFiles.");
          }
          if (testCommands.length === 0) {
            throw new PlanParseError("Implementation plan must specify at least one test command in testCommands.");
          }
          return {
            ticketId,
            summary,
            affectedFiles,
            testCommands,
            steps,
            rationale,
            rawContent: trimmed,
          };
        }
      }
    } catch (e: any) {
      if (e instanceof PlanParseError) throw e;
    }
  }

  // Parse structured Markdown
  const summaryMatch = trimmed.match(/(?:^|\n)#+\s*Summary\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i);
  const summary = summaryMatch ? summaryMatch[1].trim() : "";

  // Extract Affected Files from markdown (handles ##, ###, or **bold** headings)
  const filesMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:affected\s+files|files\s+to\s+(?:modify|change)|target\s+files|files)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const affectedFiles: string[] = [];
  if (filesMatch) {
    const lines = filesMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^[-*+]\s*/, "").trim();
      const codeMatch = cleaned.match(/`([^`]+)`/);
      const filePath = codeMatch ? codeMatch[1].trim() : cleaned;
      if (filePath && !filePath.startsWith("#") && !filePath.endsWith(":")) {
        const cleanPath = filePath.split(/\s+/)[0];
        if (cleanPath && !affectedFiles.includes(cleanPath)) {
          affectedFiles.push(cleanPath);
        }
      }
    }
  }

  // Fallback: extract backticked code file paths if Affected Files section was absent/empty
  if (affectedFiles.length === 0) {
    const fileMatches = trimmed.matchAll(/`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`/g);
    for (const match of fileMatches) {
      const candidate = match[1].trim();
      if (
        (candidate.startsWith("src/") ||
          candidate.startsWith("test/") ||
          candidate.startsWith("lib/") ||
          candidate.endsWith(".ts") ||
          candidate.endsWith(".js") ||
          candidate.endsWith(".json")) &&
        !affectedFiles.includes(candidate)
      ) {
        affectedFiles.push(candidate);
      }
    }
  }

  // Extract Test Commands from markdown
  const testsMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:test\s+commands|tests|verification\s+commands)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const testCommands: string[] = [];
  if (testsMatch) {
    const blockMatch = testsMatch[1].match(/```(?:bash|sh)?\s*([\s\S]*?)\s*```/);
    if (blockMatch) {
      const lines = blockMatch[1].split("\n");
      for (const line of lines) {
        const cmd = line.trim();
        if (cmd && !cmd.startsWith("#")) {
          testCommands.push(cmd);
        }
      }
    } else {
      const lines = testsMatch[1].split("\n");
      for (const line of lines) {
        const cleaned = line.replace(/^[-*+]\s*/, "").replace(/^`|`$/g, "").trim();
        if (cleaned && !cleaned.startsWith("#")) {
          testCommands.push(cleaned);
        }
      }
    }
  }

  // Fallback: search for common test invocations if section was absent
  if (testCommands.length === 0) {
    const cmdMatches = trimmed.matchAll(/`(npm\s+test|pnpm\s+test|node\s+--[^`]+|pytest[^`]*)`/g);
    for (const match of cmdMatches) {
      const cmd = match[1].trim();
      if (!testCommands.includes(cmd)) {
        testCommands.push(cmd);
      }
    }
  }

  // Extract Steps from markdown
  const stepsMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:steps|implementation\s+steps|tasks)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const steps: string[] = [];
  if (stepsMatch) {
    const lines = stepsMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^\d+\.\s*/, "").replace(/^[-*+]\s*/, "").trim();
      if (cleaned) {
        steps.push(cleaned);
      }
    }
  }

  if (affectedFiles.length === 0) {
    throw new PlanParseError("Implementation plan must specify at least one affected file under Affected Files.");
  }
  if (testCommands.length === 0) {
    throw new PlanParseError("Implementation plan must specify at least one test command under Test Commands.");
  }

  return {
    ticketId: fallbackTicketId,
    summary,
    affectedFiles,
    testCommands,
    steps,
    rawContent: trimmed,
  };
}

/**
 * Parses a review verdict from JSON or markdown text.
 */
export function parseReviewVerdict(content: string): ReviewVerdict {
  const trimmed = content.trim();

  // Try all JSON blocks first
  const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)\s*```/g;
  let codeMatch: RegExpExecArray | null;
  while ((codeMatch = codeBlockRegex.exec(trimmed)) !== null) {
    try {
      const parsed = JSON.parse(codeMatch[1]);
      if (typeof parsed === "object" && parsed !== null && parsed.verdict) {
        const rawVerdict = String(parsed.verdict).toLowerCase().trim();
        if (rawVerdict !== "approved" && rawVerdict !== "rejected") {
          throw new ReviewParseError(`Invalid review verdict: "${parsed.verdict}". Expected "approved" or "rejected".`);
        }
        let verdict: "approved" | "rejected" = rawVerdict;

        const summary = String(parsed.summary || "");
        const specCompliance = {
          passed: Boolean(parsed.specCompliance?.passed),
          details: String(parsed.specCompliance?.details || ""),
        };
        const standardsCompliance = {
          passed: Boolean(parsed.standardsCompliance?.passed),
          details: String(parsed.standardsCompliance?.details || ""),
        };
        if (!specCompliance.passed || !standardsCompliance.passed) {
          verdict = "rejected";
        }
        const issues: ReviewIssue[] = Array.isArray(parsed.issues)
          ? parsed.issues.map((i: any) => ({
              severity: i.severity === "blocker" || i.severity === "warning" || i.severity === "suggestion" ? i.severity : "warning",
              description: String(i.description || ""),
              file: i.file ? String(i.file) : undefined,
            }))
          : [];
        const remediation = parsed.remediation ? String(parsed.remediation) : undefined;

        return {
          verdict,
          summary,
          specCompliance,
          standardsCompliance,
          issues,
          remediation,
          rawContent: trimmed,
        };
      }
    } catch (e: any) {
      if (e instanceof ReviewParseError) throw e;
    }
  }

  // Parse markdown format - accommodate all common markdown styles:
  // **Verdict:** APPROVED, **Verdict**: APPROVED, **Verdict**: **APPROVED**,
  // # Verdict: APPROVED, Verdict: `APPROVED`, etc.
  const verdictMatch =
    trimmed.match(/(?:[*#_`\s]*(?:review\s+)?verdict[*#_`\s]*:?)\s*[*_`\s]*(APPROVED|REJECTED)[*_`\s]*/i) ||
    trimmed.match(/(?:^|\n)\s*(?:#+\s*)?(?:[*_`\s]*(?:review\s+)?verdict[*_`\s]*:?)?\s*[*_`\s]*(APPROVED|REJECTED)\b/i);

  if (!verdictMatch) {
    throw new ReviewParseError('Could not determine review verdict. Must clearly state "APPROVED" or "REJECTED".');
  }

  let verdict = verdictMatch[1].toLowerCase() as "approved" | "rejected";
  const summaryMatch = trimmed.match(/##\s*Summary\s*([\s\S]*?)(?=##|$)/i);
  const summary = summaryMatch ? summaryMatch[1].trim() : "";

  const specMatch = trimmed.match(/##\s*Spec Compliance\s*([\s\S]*?)(?=##|$)/i);
  const specPassed = specMatch ? /status:\s*passed/i.test(specMatch[1]) : verdict === "approved";
  const specDetailsMatch = specMatch ? specMatch[1].match(/details:\s*([\s\S]*?)$/im) : null;
  const specDetails = specDetailsMatch ? specDetailsMatch[1].trim() : specMatch ? specMatch[1].trim() : "";

  const standardsMatch = trimmed.match(/##\s*Standards Compliance\s*([\s\S]*?)(?=##|$)/i);
  const standardsPassed = standardsMatch ? /status:\s*passed/i.test(standardsMatch[1]) : verdict === "approved";
  const standardsDetailsMatch = standardsMatch ? standardsMatch[1].match(/details:\s*([\s\S]*?)$/im) : null;
  const standardsDetails = standardsDetailsMatch ? standardsDetailsMatch[1].trim() : standardsMatch ? standardsMatch[1].trim() : "";

  if (!specPassed || !standardsPassed) {
    verdict = "rejected";
  }

  const issuesMatch = trimmed.match(/##\s*Issues\s*([\s\S]*?)(?=##|$)/i);
  const issues: ReviewIssue[] = [];
  if (issuesMatch) {
    const lines = issuesMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^[-*+]\s*/, "").trim();
      if (cleaned && !/^(none|n\/a)\.?$/i.test(cleaned)) {
        const severity: "blocker" | "warning" | "suggestion" =
          /\b(blocker|critical|error)\b/i.test(cleaned)
            ? "blocker"
            : /\b(suggestion|nit)\b/i.test(cleaned)
            ? "suggestion"
            : "warning";
        issues.push({ severity, description: cleaned });
      }
    }
  }

  const remediationMatch = trimmed.match(/##\s*Remediation\s*([\s\S]*?)(?=##|$)/i);
  const remediation = remediationMatch ? remediationMatch[1].trim() : undefined;

  return {
    verdict,
    summary,
    specCompliance: {
      passed: specPassed,
      details: specDetails,
    },
    standardsCompliance: {
      passed: standardsPassed,
      details: standardsDetails,
    },
    issues,
    remediation,
    rawContent: trimmed,
  };
}

// System prompts per specialized role
export const PLANNER_SYSTEM_PROMPT = `You are the Planner Agent in the Software Factory assembly line.
Your role is strictly read-only: inspect the target repository workspace using file viewing, search, and directory navigation tools (read, grep, find, ls).
You must analyze the work item, feature specification, domain documentation (CONTEXT.md), and accepted Architectural Decision Records (docs/adr/).
You must ensure the planned implementation adheres strictly to all accepted ADRs and repo standards.
You must generate a clear, structured implementation plan specifying:
1. Affected files (explicit paths that must be created or modified)
2. Test commands (explicit verification commands, e.g. "pnpm test", "pytest")
3. Step-by-step implementation instructions

Always provide your plan containing a JSON block:
\`\`\`json
{
  "ticketId": "<ticket-id>",
  "summary": "<high-level summary>",
  "affectedFiles": ["path/to/file1.ts", "path/to/file2.ts"],
  "testCommands": ["command to test"],
  "steps": ["1. ...", "2. ..."],
  "rationale": "<design decisions and alignment with ADRs>"
}
\`\`\``;

export const CODER_SYSTEM_PROMPT = `You are the Coder Agent in the Software Factory assembly line.
Your role is to implement changes, reproduction tests, and documentation according to the ticket specification and the implementation plan.
You have read, write, edit, bash, and git diff capabilities.
Implement minimal, robust changes adhering to the repository's coding standards.
Execute tests via bash when verifying your work.`;

export const REVIEWER_SYSTEM_PROMPT = `You are the Reviewer Agent in the Software Factory assembly line.
Your role is strictly read-only: inspect git diffs, tickets, plans, and repository standards using read, grep, find, ls, and diff inspection tools.
You MUST evaluate whether the changes satisfy the ticket specification and repo standards.
Under standardsCompliance, you MUST verify that code changes adhere strictly to accepted Architectural Decision Records in docs/adr/. If any code change contradicts or violates an accepted ADR, you MUST mark standardsCompliance as failed and set verdict to "rejected".
You must emit a structured review verdict in a JSON block:
\`\`\`json
{
  "verdict": "approved" | "rejected",
  "summary": "<summary of review>",
  "specCompliance": {
    "passed": true | false,
    "details": "<assessment against acceptance criteria>"
  },
  "standardsCompliance": {
    "passed": true | false,
    "details": "<assessment against coding standards and accepted ADRs in docs/adr/>"
  },
  "issues": [
    {
      "severity": "blocker" | "warning" | "suggestion",
      "description": "<issue details>",
      "file": "<optional file path>"
    }
  ],
  "remediation": "<actionable instructions if rejected>"
}
\`\`\``;

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

export interface TicketInput {
  id: string;
  title?: string;
  content?: string;
  filePath?: string;
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

export interface StageAgentCommonOptions {
  workspaceDir: string;
  model?: Model<any>;
  provider?: Provider;
  streamFn?: (model: Model<any>, context: any, options: any) => any;
  tools?: any[];
  telemetryStream?: { write: (chunk: string) => any };
}

export interface PlannerOptions extends StageAgentCommonOptions {
  ticket: TicketInput | string;
  specContent?: string;
  contextContent?: string;
  adrsContent?: string;
}

export interface CoderOptions extends StageAgentCommonOptions {
  ticket: TicketInput | string;
  plan: ImplementationPlan | string;
  diagnostics?: string;
}

export interface ReviewerOptions extends StageAgentCommonOptions {
  ticket: TicketInput | string;
  plan: ImplementationPlan | string;
  diff?: string;
  contextContent?: string;
  adrsContent?: string;
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
