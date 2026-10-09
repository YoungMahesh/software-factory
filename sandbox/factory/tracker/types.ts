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
}

export interface DeliveryGateFinalizeResult {
  pullRequestNumber?: number;
  pullRequestUrl?: string;
  readyForReview: boolean;
}

export interface IssueTracker {
  readonly id: TrackerType;
  validatePreflight(workspaceDir: string, featureSlug: string): Promise<PreflightCheckResult>;
  getFeatureSpec(workspaceDir: string, featureSlug: string): Promise<string | undefined>;
  getTickets(workspaceDir: string, featureSlug: string): Promise<Ticket[]>;
  getFrontierTickets(workspaceDir: string, featureSlug: string): Promise<Ticket[]>;
  claimTicket(ticket: Ticket, options?: ClaimTicketOptions): Promise<void>;
  resolveTicket(ticket: Ticket, options?: ResolveTicketOptions): Promise<void>;
  escalateTicket(ticket: Ticket, options?: EscalateTicketOptions): Promise<void>;
  initializeDeliveryGate?(options: {
    workspaceDir: string;
    featureSlug: string;
    branch: string;
    tickets: Ticket[];
  }): Promise<DeliveryGateInitResult | null>;
  finalizeDeliveryGate?(options: {
    workspaceDir: string;
    featureSlug: string;
    branch: string;
    tickets: Ticket[];
    summary?: string;
  }): Promise<DeliveryGateFinalizeResult | null>;
}
