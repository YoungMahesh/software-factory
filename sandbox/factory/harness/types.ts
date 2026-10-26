import { type Model, type Provider } from "@earendil-works/pi-ai";

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

export interface TicketInput {
  id: string;
  title?: string;
  content?: string;
  filePath?: string;
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
  visualSummary?: string;
}
