/**
 * In-Sandbox Agent Event Stream Telemetry Emitter.
 *
 * Formats structured telemetry events (thinking, tool_start, tool_result, stage, attempt)
 * into single-line JSON envelopes tagged with '__SF_EVENT__:' and transmits them unbuffered
 * through container stdout to the host JobRegistry and SSE stream.
 */

import * as fs from "node:fs";

export const EVENT_PREFIX = "__SF_EVENT__:";

export type TelemetryEventType =
  | "thinking"
  | "tool_start"
  | "tool_result"
  | "stage"
  | "attempt"
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

/**
 * Formats a telemetry event into a single-line JSON string prefixed with '__SF_EVENT__:'.
 */
export function formatTelemetryEnvelope<T = any>(
  input: TelemetryEventInput<T>
): string {
  const envelope: TelemetryEnvelope<T> = {
    type: input.type,
    ...(input.stage ? { stage: input.stage } : {}),
    data: (input.data !== undefined ? input.data : {}) as T,
    timestamp:
      typeof input.timestamp === "number" ? input.timestamp : Date.now() / 1000,
  };

  return `${EVENT_PREFIX}${JSON.stringify(envelope)}\n`;
}

/**
 * Parses an incoming stdout line into a typed TelemetryEnvelope if prefixed with '__SF_EVENT__:'.
 * Returns null if the line is not a valid telemetry envelope.
 */
export function parseTelemetryEnvelope<T = any>(
  line: string
): TelemetryEnvelope<T> | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith(EVENT_PREFIX)) {
    return null;
  }

  const payloadStr = trimmed.slice(EVENT_PREFIX.length).trim();
  try {
    const parsed = JSON.parse(payloadStr);
    if (typeof parsed === "object" && parsed !== null && "type" in parsed) {
      return parsed as TelemetryEnvelope<T>;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Emits a structured telemetry event unbuffered to container stdout (or custom stream).
 */
export function emitTelemetryEvent<T = any>(
  input: TelemetryEventInput<T>,
  options?: EmitOptions
): string {
  const formatted = formatTelemetryEnvelope(input);

  if (options?.stream) {
    options.stream.write(formatted);
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
  return emitTelemetryEvent(
    {
      type: "thinking",
      stage,
      data: { delta, ...extra },
    },
    options
  );
}

/**
 * Emits a tool execution initiation telemetry event.
 */
export function emitToolStartEvent(
  toolName: string,
  args: any,
  toolCallId?: string,
  stage?: TelemetryStage,
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    {
      type: "tool_start",
      stage,
      data: { toolName, args, toolCallId },
    },
    options
  );
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
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    {
      type: "tool_result",
      stage,
      data: { toolName, result, isError, toolCallId, durationMs },
    },
    options
  );
}

/**
 * Emits an assembly line stage transition telemetry event.
 */
export function emitStageEvent(
  stage: TelemetryStage,
  data: Record<string, any> = {},
  options?: EmitOptions
): string {
  return emitTelemetryEvent(
    {
      type: "stage",
      stage,
      data,
    },
    options
  );
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
  return emitTelemetryEvent(
    {
      type: "attempt",
      stage,
      data: { attempt, maxAttempts, ...data },
    },
    options
  );
}

/**
 * Stateful telemetry stream that manages current stage context and emits typed envelopes.
 */
export class AgentEventStream {
  private currentStage?: TelemetryStage;
  private stream?: { write: (chunk: string) => any };

  constructor(options?: {
    stage?: TelemetryStage;
    stream?: { write: (chunk: string) => any };
  }) {
    this.currentStage = options?.stage;
    this.stream = options?.stream;
  }

  setStage(stage: TelemetryStage): void {
    this.currentStage = stage;
  }

  getStage(): TelemetryStage | undefined {
    return this.currentStage;
  }

  emit<T = any>(
    type: TelemetryEventType,
    data: T,
    stage?: TelemetryStage
  ): string {
    return emitTelemetryEvent(
      {
        type,
        stage: stage ?? this.currentStage,
        data,
      },
      { stream: this.stream }
    );
  }

  emitStage(stage: TelemetryStage, data: Record<string, any> = {}): string {
    this.currentStage = stage;
    return emitStageEvent(stage, data, { stream: this.stream });
  }

  emitThinking(delta: string, extra?: Record<string, any>): string {
    return emitThinkingEvent(delta, this.currentStage, extra, {
      stream: this.stream,
    });
  }

  emitToolStart(toolName: string, args: any, toolCallId?: string): string {
    return emitToolStartEvent(toolName, args, toolCallId, this.currentStage, {
      stream: this.stream,
    });
  }

  emitToolResult(
    toolName: string,
    result: any,
    isError: boolean = false,
    toolCallId?: string,
    durationMs?: number
  ): string {
    return emitToolResultEvent(
      toolName,
      result,
      isError,
      toolCallId,
      this.currentStage,
      durationMs,
      { stream: this.stream }
    );
  }

  emitAttempt(
    attempt: number,
    maxAttempts: number,
    data: Record<string, any> = {}
  ): string {
    return emitAttemptEvent(
      attempt,
      maxAttempts,
      this.currentStage ?? "CODER",
      data,
      { stream: this.stream }
    );
  }
}
