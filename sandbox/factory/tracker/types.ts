import type { Ticket, PreflightCheckResult } from "../preflight.ts";

export type TrackerType = "github" | "local";

export interface ClaimTicketOptions {
  branch?: string;
}

export interface ResolveTicketOptions {
  branch?: string;
  commitSha?: string;
  auditSummary?: string;
}

export interface EscalateTicketOptions {
  branch?: string;
  failureDiagnostics?: string;
}

export interface DeliveryGateInitResult {
  pullRequestNumber?: number;
  pullRequestUrl?: string;
  branch: string;
  title?: string;
}

export interface DeliveryGateFinalizeResult {
  pullRequestNumber?: number;
  pullRequestUrl?: string;
  branch?: string;
  title?: string;
  readyForReview: boolean;
}

export interface DeliveryGateInitOptions {
  workspaceDir: string;
  featureSlug?: string;
  branch: string;
  ticket?: Ticket;
  tickets?: Ticket[];
}

export interface DeliveryGateUpdateOptions {
  workspaceDir: string;
  featureSlug?: string;
  branch: string;
  ticket: Ticket;
  status: "resolved" | "ready-for-human";
  diagnostics?: string;
}

export interface DeliveryGateFinalizeOptions {
  workspaceDir: string;
  featureSlug?: string;
  branch: string;
  tickets?: Ticket[];
  summary?: string;
}

export interface IssueTracker {
  readonly id: TrackerType;
  validatePreflight(workspaceDir: string, featureSlug: string, issueId?: string): Promise<PreflightCheckResult>;
  getFeatureSpec(workspaceDir: string, featureSlug: string, issueId?: string): Promise<string | undefined>;
  getTickets(workspaceDir: string, featureSlug: string, issueId?: string): Promise<Ticket[]>;
  getFrontierTickets(workspaceDir: string, featureSlug: string, issueId?: string): Promise<Ticket[]>;
  claimTicket(ticket: Ticket, options?: ClaimTicketOptions): Promise<void>;
  resolveTicket(ticket: Ticket, options?: ResolveTicketOptions): Promise<void>;
  escalateTicket(ticket: Ticket, options?: EscalateTicketOptions): Promise<void>;
  initializeDeliveryGate?(options: DeliveryGateInitOptions): Promise<DeliveryGateInitResult | null>;
  updateDeliveryGate?(options: DeliveryGateUpdateOptions): Promise<void>;
  finalizeDeliveryGate?(options: DeliveryGateFinalizeOptions): Promise<DeliveryGateFinalizeResult | null>;
}
