/**
 * Synchronous stream writing, blocking socket controls, buffer flush management,
 * and lifecycle telemetry event emitting.
 */

import * as fs from "node:fs";
import type { ReviewVerdict } from "../harness.ts";
import {
  formatAttemptData,
  formatAttemptStartData,
  formatDeliveryGateData,
  formatReviewerRejectionData,
  formatTelemetryEnvelope,
  formatToolResultData,
  formatToolStartData,
} from "./formatter.ts";
import { ThinkingExtractor } from "./parser.ts";
import {
  type DeliveryGateEventData,
  type EmitOptions,
  type TelemetryEventInput,
  type TelemetryEventType,
  type TelemetryStage,
  type ToolResultOptions,
  type ToolStartOptions,
} from "./types.ts";

// Ensure Node.js container stdout and stderr handle writes synchronously without block buffering
try {
  if ((process.stdout as any)?._handle?.setBlocking) {
    (process.stdout as any)._handle.setBlocking(true);
  }
  if ((process.stderr as any)?._handle?.setBlocking) {
    (process.stderr as any)._handle.setBlocking(true);
  }
} catch {
  // Ignore in environments where _handle is not accessible
}

let globalTelemetryStream: { write: (chunk: string) => any } | null = null;

export function setGlobalTelemetryStream(stream: { write: (chunk: string) => any } | null): void {
  globalTelemetryStream = stream;
}

export function getGlobalTelemetryStream(): { write: (chunk: string) => any } | null {
  return globalTelemetryStream;
}

/**
 * Emits a structured telemetry event unbuffered to container stdout (or custom stream).
 */
export function emitTelemetryEvent<T = any>(
  input: TelemetryEventInput<T>,
  options?: EmitOptions
): string {
  const formatted = formatTelemetryEnvelope(input);
  const stream = options?.stream ?? globalTelemetryStream;

  if (stream) {
    stream.write(formatted);
  } else if (options?.sync === false) {
    process.stdout.write(formatted);
  } else {
    try {
      fs.writeSync(1, formatted);
    } catch {
      process.stdout.write(formatted);
    }
  }

  return formatted;
}

/**
 * Emits an LLM reasoning/thinking telemetry event.
 */
export function emitThinkingEvent(
  delta: string,
  stage?: TelemetryStage,
  extra?: Record<string, any>,
  options?: EmitOptions
): string {
  return emitTelemetryEvent({ type: "thinking", stage, data: { delta, ...extra } }, options);
}

/**
 * Emits a tool execution initiation telemetry event.
 */
export function emitToolStartEvent(
  toolName: string,
  args: any,
  toolCallId?: string,
  stage?: TelemetryStage,
  options?: ToolStartOptions
): string {
  const data = formatToolStartData(toolName, args, toolCallId, options);
  return emitTelemetryEvent({ type: "tool_start", stage, data }, options);
}

/**
 * Emits a tool execution completion telemetry event.
 */
export function emitToolResultEvent(
  toolName: string,
  result: any,
  isError: boolean = false,
  toolCallId?: string,
  stage?: TelemetryStage,
  durationMs?: number,
  options?: ToolResultOptions
): string {
  const data = formatToolResultData(toolName, result, isError, toolCallId, durationMs, options);
  return emitTelemetryEvent({ type: "tool_result", stage, data }, options);
}

/**
 * Emits an assembly line stage transition telemetry event.
 */
export function emitStageEvent(
  stage: TelemetryStage,
  data: Record<string, any> = {},
  options?: EmitOptions
): string {
  return emitTelemetryEvent({ type: "stage", stage, data }, options);
}

/**
 * Emits a self-correction loop attempt telemetry event.
 */
export function emitAttemptEvent(
  attempt: number,
  maxAttempts: number,
  stage: TelemetryStage = "CODER",
  data: Record<string, any> = {},
  options?: EmitOptions
): string {
  return emitTelemetryEvent({ type: "attempt", stage, data: formatAttemptData(attempt, maxAttempts, data) }, options);
}

/**
 * Emits a self-correction loop attempt_start telemetry event.
 */
export function emitAttemptStartEvent(
  attempt: number,
  maxRetries: number,
  reason?: string,
  data: Record<string, any> = {},
  stage: TelemetryStage = "CODER",
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    { type: "attempt_start", stage, data: formatAttemptStartData(attempt, maxRetries, reason, data) },
    options
  );
}

/**
 * Emits a reviewer rejection telemetry event with audit diagnostics.
 */
export function emitReviewerRejectionEvent(
  verdict: Partial<ReviewVerdict> | Record<string, any>,
  stage: TelemetryStage = "REVIEWER",
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    { type: "reviewer_rejection", stage, data: formatReviewerRejectionData(verdict) },
    options
  );
}

/**
 * Emits a structured Feature Pull Request delivery gate telemetry event.
 */
export function emitDeliveryGateEvent(
  data: DeliveryGateEventData,
  stage?: TelemetryStage,
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    { type: "delivery_gate", ...(stage ? { stage } : {}), data: formatDeliveryGateData(data) },
    options
  );
}

/**
 * Micro-batch buffer that aggregates high-frequency streaming thinking deltas
 * into 100ms chunks to prevent stdout stream saturation.
 */
export class ThinkingBatchBuffer {
  private buffer: string = "";
  private timer: NodeJS.Timeout | null = null;
  private intervalMs: number;
  private onFlush: (delta: string) => void;

  constructor(options: { intervalMs?: number; onFlush: (delta: string) => void }) {
    this.intervalMs = options.intervalMs ?? 100;
    this.onFlush = options.onFlush;
  }

  append(delta: string): void {
    this.buffer += delta;
    if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), this.intervalMs);
    }
  }

  flush(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.buffer.length > 0) {
      const content = this.buffer;
      this.buffer = "";
      this.onFlush(content);
    }
  }

  drain(): string {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const content = this.buffer;
    this.buffer = "";
    return content;
  }

  hasPending(): boolean {
    return this.buffer.length > 0;
  }
}

/**
 * Stateful telemetry stream that manages current stage context and emits typed envelopes.
 */
export class AgentEventStream {
  private currentStage?: TelemetryStage;
  private stream?: { write: (chunk: string) => any };
  private thinkingBuffer?: ThinkingBatchBuffer;
  private thinkingExtractor: ThinkingExtractor;
  private workspaceDir?: string;

  constructor(options?: {
    stage?: TelemetryStage;
    stream?: { write: (chunk: string) => any };
    batchThinkingMs?: number;
    workspaceDir?: string;
  }) {
    this.currentStage = options?.stage;
    this.stream = options?.stream;
    this.workspaceDir = options?.workspaceDir;
    const intervalMs = options?.batchThinkingMs ?? 100;
    this.thinkingExtractor = new ThinkingExtractor({
      stage: this.currentStage,
      stream: this.stream,
      intervalMs,
    });
    this.thinkingBuffer = new ThinkingBatchBuffer({
      intervalMs,
      onFlush: (delta) => {
        emitThinkingEvent(delta, this.currentStage, undefined, { stream: this.stream });
      },
    });
  }

  subscribe(agent: {
    subscribe: (listener: (event: any, signal: any) => Promise<void> | void) => () => void;
  }): { unsubscribe: () => void; flush: () => void } {
    return subscribeAgentTelemetry(agent, this.currentStage ?? "PLANNER", {
      stream: this.stream,
      extractor: this.thinkingExtractor,
      workspaceDir: this.workspaceDir,
    });
  }

  setStage(stage: TelemetryStage): void {
    this.thinkingBuffer?.flush();
    this.currentStage = stage;
  }

  getStage(): TelemetryStage | undefined {
    return this.currentStage;
  }

  emit<T = any>(type: TelemetryEventType, data: T, stage?: TelemetryStage): string {
    return emitTelemetryEvent({ type, stage: stage ?? this.currentStage, data }, { stream: this.stream });
  }

  emitStage(stage: TelemetryStage, data: Record<string, any> = {}): string {
    this.thinkingBuffer?.flush();
    this.currentStage = stage;
    return emitStageEvent(stage, data, { stream: this.stream });
  }

  emitThinking(delta: string, extra?: Record<string, any>): string {
    return emitThinkingEvent(delta, this.currentStage, extra, { stream: this.stream });
  }

  bufferThinking(delta: string): void {
    this.thinkingBuffer?.append(delta);
  }

  flushThinking(): void {
    this.thinkingBuffer?.flush();
  }

  emitToolStart(toolName: string, args: any, toolCallId?: string): string {
    this.thinkingBuffer?.flush();
    return emitToolStartEvent(toolName, args, toolCallId, this.currentStage, { stream: this.stream });
  }

  emitToolResult(
    toolName: string,
    result: any,
    isError: boolean = false,
    toolCallId?: string,
    durationMs?: number
  ): string {
    return emitToolResultEvent(toolName, result, isError, toolCallId, this.currentStage, durationMs, {
      stream: this.stream,
    });
  }

  emitAttempt(attempt: number, maxAttempts: number, data: Record<string, any> = {}): string {
    return emitAttemptEvent(attempt, maxAttempts, this.currentStage ?? "CODER", data, { stream: this.stream });
  }

  emitAttemptStart(
    attempt: number,
    maxRetries: number,
    reason?: string,
    data: Record<string, any> = {}
  ): string {
    return emitAttemptStartEvent(attempt, maxRetries, reason, data, this.currentStage ?? "CODER", {
      stream: this.stream,
    });
  }

  emitReviewerRejection(verdict: Partial<ReviewVerdict> | Record<string, any>): string {
    return emitReviewerRejectionEvent(verdict, this.currentStage ?? "REVIEWER", { stream: this.stream });
  }

  emitDeliveryGate(data: DeliveryGateEventData, stage?: TelemetryStage): string {
    return emitDeliveryGateEvent(data, stage ?? this.currentStage, { stream: this.stream });
  }
}

/**
 * Subscribes to an Agent instance lifecycle events and emits structured telemetry envelopes.
 */
export function subscribeAgentTelemetry(
  agent: {
    subscribe: (listener: (event: any, signal: any) => Promise<void> | void) => () => void;
  },
  stage: TelemetryStage,
  options?: {
    stream?: { write: (chunk: string) => any };
    intervalMs?: number;
    extractor?: ThinkingExtractor;
    workspaceDir?: string;
  }
): {
  extractor: ThinkingExtractor;
  unsubscribe: () => void;
  flush: () => void;
} {
  const extractor =
    options?.extractor ??
    new ThinkingExtractor({
      stage,
      stream: options?.stream,
      intervalMs: options?.intervalMs,
    });

  const activeToolCalls = new Map<
    string,
    {
      toolName: string;
      args: any;
      startTime: number;
      cwd?: string;
      command?: string;
      path?: string;
      pattern?: string;
    }
  >();

  const unsubscribe = agent.subscribe((event: any) => {
    if (event.type === "message_update") {
      const ame = event.assistantMessageEvent;
      if (ame) {
        if (ame.type === "thinking_start") {
          // Native thinking start
        } else if (ame.type === "thinking_delta") {
          extractor.handleThinkingDelta(ame.delta);
        } else if (ame.type === "thinking_end") {
          extractor.handleThinkingEnd();
        } else if (ame.type === "text_delta") {
          extractor.handleTextDelta(ame.delta);
        } else if (ame.type === "toolcall_start") {
          extractor.flush(true);
        }
      }
    } else if (event.type === "tool_execution_start") {
      const cwd = event.args?.cwd ?? options?.workspaceDir ?? process.cwd();
      const command = event.args?.command ?? event.args?.cmd;
      const path = event.args?.path;
      const pattern = event.args?.pattern;
      if (event.toolCallId) {
        activeToolCalls.set(event.toolCallId, {
          toolName: event.toolName,
          args: event.args,
          startTime: Date.now(),
          cwd,
          command,
          path,
          pattern,
        });
      }
      extractor.handleToolStart(event.toolName, event.args, event.toolCallId, { cwd, command, path, pattern });
    } else if (event.type === "tool_execution_end") {
      const saved = event.toolCallId ? activeToolCalls.get(event.toolCallId) : undefined;
      if (event.toolCallId) {
        activeToolCalls.delete(event.toolCallId);
      }
      const durationMs =
        typeof event.durationMs === "number"
          ? event.durationMs
          : saved
          ? Date.now() - saved.startTime
          : undefined;

      emitToolResultEvent(
        event.toolName,
        event.result,
        event.isError,
        event.toolCallId,
        stage,
        durationMs,
        {
          stream: options?.stream,
          command: saved?.command,
          cwd: saved?.cwd,
          path: saved?.path,
          pattern: saved?.pattern,
          args: saved?.args,
        }
      );
    } else if (event.type === "turn_end" || event.type === "agent_end") {
      extractor.handleTurnEnd();
    }
  });

  return {
    extractor,
    unsubscribe,
    flush: () => extractor.flush(true),
  };
}
