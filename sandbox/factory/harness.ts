import { Agent } from "@earendil-works/pi-agent-core";
import { type Model, type Provider } from "@earendil-works/pi-ai";
import { getFactoryModel, createOpenCodeGoProvider } from "./provider.ts";
import {
  createRoleTools,
  assertRoleToolPrivileges,
  LeastPrivilegeViolationError,
} from "./tools.ts";

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

  // Try extracting from JSON block first
  const jsonMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (jsonMatch && jsonMatch[1]) {
    try {
      const parsed = JSON.parse(jsonMatch[1]);
      if (typeof parsed === "object" && parsed !== null) {
        const ticketId = String(parsed.ticketId || fallbackTicketId);
        const summary = String(parsed.summary || "");
        const affectedFiles = Array.isArray(parsed.affectedFiles)
          ? parsed.affectedFiles.map(String).map((f: string) => f.trim()).filter(Boolean)
          : [];
        const testCommands = Array.isArray(parsed.testCommands)
          ? parsed.testCommands.map(String).map((c: string) => c.trim()).filter(Boolean)
          : [];
        const steps = Array.isArray(parsed.steps)
          ? parsed.steps.map(String).map((s: string) => s.trim()).filter(Boolean)
          : [];
        const rationale = parsed.rationale ? String(parsed.rationale) : undefined;

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
    } catch (e: any) {
      if (e instanceof PlanParseError) throw e;
      // If JSON parse failed, fall through to markdown parser
    }
  }

  // Parse structured Markdown
  const summaryMatch = trimmed.match(/##\s*Summary\s*([\s\S]*?)(?=##|$)/i);
  const summary = summaryMatch ? summaryMatch[1].trim() : "";

  // Extract Affected Files from markdown
  const filesMatch = trimmed.match(/##\s*Affected Files\s*([\s\S]*?)(?=##|$)/i);
  const affectedFiles: string[] = [];
  if (filesMatch) {
    const lines = filesMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^[-*+]\s*/, "").trim();
      const codeMatch = cleaned.match(/`([^`]+)`/);
      const filePath = codeMatch ? codeMatch[1].trim() : cleaned;
      if (filePath && !filePath.startsWith("#")) {
        affectedFiles.push(filePath);
      }
    }
  }

  // Extract Test Commands from markdown
  const testsMatch = trimmed.match(/##\s*Test Commands\s*([\s\S]*?)(?=##|$)/i);
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

  // Extract Steps from markdown
  const stepsMatch = trimmed.match(/##\s*Steps\s*([\s\S]*?)(?=##|$)/i);
  const steps: string[] = [];
  if (stepsMatch) {
    const lines = stepsMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^\d+\.\s*/, "").trim();
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

  // Try JSON block first
  const jsonMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (jsonMatch && jsonMatch[1]) {
    try {
      const parsed = JSON.parse(jsonMatch[1]);
      if (typeof parsed === "object" && parsed !== null && parsed.verdict) {
        const rawVerdict = String(parsed.verdict).toLowerCase().trim();
        const verdict = rawVerdict === "approved" ? "approved" : rawVerdict === "rejected" ? "rejected" : null;
        if (!verdict) {
          throw new ReviewParseError(`Invalid review verdict: "${parsed.verdict}". Expected "approved" or "rejected".`);
        }

        const summary = String(parsed.summary || "");
        const specCompliance = {
          passed: Boolean(parsed.specCompliance?.passed),
          details: String(parsed.specCompliance?.details || ""),
        };
        const standardsCompliance = {
          passed: Boolean(parsed.standardsCompliance?.passed),
          details: String(parsed.standardsCompliance?.details || ""),
        };
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

  // Parse markdown format
  const verdictMatch = trimmed.match(/(?:\*\*Verdict:\*\*|Verdict:)\s*(APPROVED|REJECTED)/i);
  if (!verdictMatch) {
    throw new ReviewParseError('Could not determine review verdict. Must clearly state "APPROVED" or "REJECTED".');
  }

  const verdict = verdictMatch[1].toLowerCase() as "approved" | "rejected";
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
You must analyze the work item, feature specification, and domain documentation (CONTEXT.md).
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
    "details": "<assessment against coding standards>"
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
      if (typeof msg.content === "string") return msg.content;
      if (Array.isArray(msg.content)) {
        const textParts = msg.content
          .filter((c: any) => c.type === "text" && c.text)
          .map((c: any) => c.text);
        if (textParts.length > 0) return textParts.join("\n");
      }
    }
  }
  return "";
}

export interface TicketInput {
  id: string;
  title?: string;
  content: string;
}

export interface StageAgentCommonOptions {
  workspaceDir: string;
  model?: Model<any>;
  provider?: Provider;
  streamFn?: (model: Model<any>, context: any, options: any) => any;
  tools?: any[];
}

export interface PlannerOptions extends StageAgentCommonOptions {
  ticket: TicketInput | string;
  specContent?: string;
  contextContent?: string;
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

  const ticketObj: TicketInput =
    typeof options.ticket === "string"
      ? { id: "ticket", content: options.ticket }
      : options.ticket;

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

  promptParts.push(
    "Please inspect the repository and draft a structured implementation plan with affectedFiles and testCommands."
  );

  await agent.prompt(promptParts.join("\n\n"));
  assertAgentSuccess(agent.state.messages);

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

  const ticketObj: TicketInput =
    typeof options.ticket === "string"
      ? { id: "ticket", content: options.ticket }
      : options.ticket;

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

  await agent.prompt(promptParts.join("\n\n"));
  assertAgentSuccess(agent.state.messages);

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

  const ticketObj: TicketInput =
    typeof options.ticket === "string"
      ? { id: "ticket", content: options.ticket }
      : options.ticket;

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

  if (options.diff) {
    promptParts.push("# Git Diff", options.diff);
  } else {
    promptParts.push("Please inspect the git diff using your diff inspection tool.");
  }

  promptParts.push("Review the implementation against the ticket and repo standards and emit your review verdict.");

  await agent.prompt(promptParts.join("\n\n"));
  assertAgentSuccess(agent.state.messages);

  const responseText = extractAssistantText(agent.state.messages);
  const verdict = parseReviewVerdict(responseText);

  return {
    verdict,
    messages: agent.state.messages,
  };
}
