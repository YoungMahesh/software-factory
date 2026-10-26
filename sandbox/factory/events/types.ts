/**
 * Telemetry event types, interfaces, and constants.
 */

import type { ReviewVerdict } from "../harness.ts";

export const EVENT_PREFIX = "__SF_EVENT__:";

export type TelemetryEventType =
  | "thinking"
  | "tool_start"
  | "tool_result"
  | "stage"
  | "attempt"
  | "attempt_start"
  | "reviewer_rejection"
  | "delivery_gate"
  | "visual_qa"
  | (string & {});

export type TelemetryStage =
  | "PREFLIGHT"
  | "PLANNER"
  | "CODER"
  | "VERIFIER"
  | "REVIEWER"
  | "COMPLETED"
  | (string & {});

export interface TelemetryEnvelope<T = any> {
  type: TelemetryEventType;
  stage?: TelemetryStage;
  data: T;
  timestamp: number;
}

export interface TelemetryEventInput<T = any> {
  type: TelemetryEventType;
  stage?: TelemetryStage;
  data?: T;
  timestamp?: number;
}

export interface EmitOptions {
  stream?: { write: (chunk: string) => any };
  sync?: boolean;
}

export interface ToolStartOptions extends EmitOptions {
  cwd?: string;
  command?: string;
  path?: string;
  pattern?: string;
  bytes?: number;
  [key: string]: any;
}

export interface ToolResultOptions extends EmitOptions {
  command?: string;
  cwd?: string;
  exitCode?: number;
  stdout?: string;
  stderr?: string;
  output?: string;
  path?: string;
  pattern?: string;
  bytes?: number;
  lineCount?: number;
  matchCount?: number;
  diff?: string;
  patch?: string;
  args?: any;
  [key: string]: any;
}

export interface DeliveryGateEventData {
  pull_number?: number;
  pullRequestNumber?: number;
  pull_request_number?: number;
  pullRequestUrl?: string;
  pull_request_url?: string;
  html_url?: string;
  branch: string;
  title?: string;
  draft?: boolean;
  ready_for_review?: boolean;
  [key: string]: any;
}

export interface ThinkingExtractorOptions {
  stage?: TelemetryStage;
  stream?: { write: (chunk: string) => any };
  intervalMs?: number;
  onEmit?: (envelope: TelemetryEnvelope) => void;
}
