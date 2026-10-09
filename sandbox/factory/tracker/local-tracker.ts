import * as fs from "node:fs";
import * as path from "node:path";
import {
  type Ticket,
  type PreflightCheckResult,
  validatePreflight as validateLocalPreflight,
  parseTickets,
  getFrontierTickets as computeLocalFrontierTickets,
} from "../preflight.ts";
import { updateTicketFile } from "../ticket.ts";
import type {
  IssueTracker,
  ClaimTicketOptions,
  ResolveTicketOptions,
  EscalateTicketOptions,
} from "./types.ts";

export class LocalScratchTracker implements IssueTracker {
  public readonly id = "local" as const;

  public async validatePreflight(
    workspaceDir: string,
    featureSlug: string
  ): Promise<PreflightCheckResult> {
    return validateLocalPreflight(workspaceDir, featureSlug);
  }

  public async getFeatureSpec(
    workspaceDir: string,
    featureSlug: string
  ): Promise<string | undefined> {
    const specPath = path.join(workspaceDir, ".scratch", featureSlug, "spec.md");
    if (fs.existsSync(specPath)) {
      return fs.readFileSync(specPath, "utf-8");
    }
    return undefined;
  }

  public async getTickets(
    workspaceDir: string,
    featureSlug: string
  ): Promise<Ticket[]> {
    return parseTickets(workspaceDir, featureSlug);
  }

  public async getFrontierTickets(
    workspaceDir: string,
    featureSlug: string
  ): Promise<Ticket[]> {
    const tickets = await this.getTickets(workspaceDir, featureSlug);
    return computeLocalFrontierTickets(tickets);
  }

  public async claimTicket(
    ticket: Ticket,
    options?: ClaimTicketOptions
  ): Promise<void> {
    if (!ticket.filePath) {
      throw new Error(`Ticket ${ticket.id} has no filePath associated for local update`);
    }
    updateTicketFile({
      filePath: ticket.filePath,
      status: "claimed",
      branch: options?.branch,
    });
    ticket.status = "claimed";
  }

  public async resolveTicket(
    ticket: Ticket,
    options?: ResolveTicketOptions
  ): Promise<void> {
    if (!ticket.filePath) {
      throw new Error(`Ticket ${ticket.id} has no filePath associated for local update`);
    }
    updateTicketFile({
      filePath: ticket.filePath,
      status: "resolved",
      branch: options?.branch,
      commitSha: options?.commitSha,
      auditSummary: options?.auditSummary,
    });
    ticket.status = "resolved";
  }

  public async escalateTicket(
    ticket: Ticket,
    options?: EscalateTicketOptions
  ): Promise<void> {
    if (!ticket.filePath) {
      throw new Error(`Ticket ${ticket.id} has no filePath associated for local update`);
    }
    updateTicketFile({
      filePath: ticket.filePath,
      status: "ready-for-human",
      branch: options?.branch,
      failureDiagnostics: options?.failureDiagnostics,
    });
    ticket.status = "ready-for-human";
  }
}
