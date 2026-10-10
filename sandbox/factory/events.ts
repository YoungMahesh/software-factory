/**
 * In-Sandbox Agent Event Stream Telemetry Emitter.
 *
 * Formats structured telemetry events (thinking, tool_start, tool_result, stage, attempt)
 * into single-line JSON envelopes tagged with '__SF_EVENT__:' and transmits them unbuffered
 * through container stdout to the host JobRegistry and SSE stream.
 */

import * as fs from "node:fs";

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

export interface ToolStartOptions extends EmitOptions {
  cwd?: string;
  command?: string;
}

export interface ToolResultOptions extends EmitOptions {
  command?: string;
  cwd?: string;
  exitCode?: number;
  stdout?: string;
  stderr?: string;
  output?: string;
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
  const data: Record<string, any> = {
    toolName,
    args: args !== undefined ? (typeof args === "object" && args !== null ? { ...args } : args) : {},
    toolCallId,
  };

  if (toolName === "bash") {
    const cmd = args?.command ?? args?.cmd ?? options?.command ?? "";
    const cwd = args?.cwd ?? options?.cwd ?? process.cwd();
    data.command = cmd;
    data.cwd = cwd;
    if (data.args && typeof data.args === "object" && !data.args.cwd && cwd) {
      data.args.cwd = cwd;
    }
  }

  return emitTelemetryEvent(
    {
      type: "tool_start",
      stage,
      data,
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
  options?: ToolResultOptions
): string {
  let exitCode = options?.exitCode;
  let stdout = options?.stdout;
  let stderr = options?.stderr;
  let output = options?.output;
  let cmd = options?.command;
  let cwd = options?.cwd;
  let finalDurationMs = durationMs ?? (typeof result === "object" && result !== null ? result.durationMs : undefined);
  let finalIsError = Boolean(isError);

  if (result && typeof result === "object") {
    if (exitCode === undefined) {
      if (typeof result.exitCode === "number") {
        exitCode = result.exitCode;
      } else if (result.structuredContent && typeof result.structuredContent.exit_code === "number") {
        exitCode = result.structuredContent.exit_code;
      }
    }
    if (cmd === undefined && typeof result.command === "string") {
      cmd = result.command;
    }
    if (cwd === undefined && typeof result.cwd === "string") {
      cwd = result.cwd;
    }
    if (stdout === undefined && typeof result.stdout === "string") {
      stdout = result.stdout;
    }
    if (stderr === undefined && typeof result.stderr === "string") {
      stderr = result.stderr;
    }
    if (output === undefined) {
      if (typeof result.output === "string") {
        output = result.output;
      } else if (result.structuredContent && typeof result.structuredContent.output === "string") {
        output = result.structuredContent.output;
      } else if (Array.isArray(result.content) && result.content[0]?.text) {
        output = result.content[0].text;
      }
    }
    if (result.isError !== undefined) {
      finalIsError = Boolean(result.isError || isError);
    }
  } else if (typeof result === "string" && output === undefined) {
    output = result;
  }

  if (exitCode !== undefined && exitCode !== 0) {
    finalIsError = true;
  } else if (exitCode === undefined) {
    exitCode = finalIsError ? 1 : 0;
  }

  if (output === undefined) {
    output = stdout || stderr || "";
  }
  if (stdout === undefined) {
    stdout = output || "";
  }
  if (stderr === undefined) {
    stderr = exitCode !== 0 ? output : "";
  }

  const data: Record<string, any> = {
    toolName,
    result,
    isError: finalIsError,
    toolCallId,
    durationMs: finalDurationMs ?? 0,
  };

  if (toolName === "bash" || cmd !== undefined) {
    if (cmd !== undefined) data.command = cmd;
    if (cwd !== undefined) data.cwd = cwd;
    data.exitCode = exitCode;
    data.stdout = stdout;
    data.stderr = stderr;
    data.output = output;
  }

  return emitTelemetryEvent(
    {
      type: "tool_result",
      stage,
      data,
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
 * Micro-batch buffer that aggregates high-frequency streaming thinking deltas
 * into 100ms chunks to prevent stdout stream saturation.
 */
export class ThinkingBatchBuffer {
  private buffer: string = "";
  private timer: NodeJS.Timeout | null = null;
  private intervalMs: number;
  private onFlush: (delta: string) => void;

  constructor(options: {
    intervalMs?: number;
    onFlush: (delta: string) => void;
  }) {
    this.intervalMs = options.intervalMs ?? 100;
    this.onFlush = options.onFlush;
  }

  append(delta: string): void {
    this.buffer += delta;
    if (!this.timer) {
      this.timer = setTimeout(() => {
        this.flush();
      }, this.intervalMs);
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
        emitThinkingEvent(delta, this.currentStage, undefined, {
          stream: this.stream,
        });
      },
    });
  }

  /**
   * Subscribes to an Agent instance lifecycle events, streaming 100ms micro-batched
   * reasoning deltas, tool executions, and turn completions per ADR-0035.
   */
  subscribe(agent: {
    subscribe: (
      listener: (event: any, signal: any) => Promise<void> | void
    ) => () => void;
  }): {
    unsubscribe: () => void;
    flush: () => void;
  } {
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
    this.thinkingBuffer?.flush();
    this.currentStage = stage;
    return emitStageEvent(stage, data, { stream: this.stream });
  }

  emitThinking(delta: string, extra?: Record<string, any>): string {
    return emitThinkingEvent(delta, this.currentStage, extra, {
      stream: this.stream,
    });
  }

  bufferThinking(delta: string): void {
    this.thinkingBuffer?.append(delta);
  }

  flushThinking(): void {
    this.thinkingBuffer?.flush();
  }

  emitToolStart(toolName: string, args: any, toolCallId?: string): string {
    this.thinkingBuffer?.flush();
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

/**
 * Strips <think>...</think> reasoning blocks from text.
 */
export function stripThinkTags(content: string): string {
  return content.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
}

export interface ThinkingExtractorOptions {
  stage?: TelemetryStage;
  stream?: { write: (chunk: string) => any };
  intervalMs?: number;
  onEmit?: (envelope: TelemetryEnvelope) => void;
}

/**
 * Dual-extraction reasoning engine that captures native thinking_delta events
 * as well as parses and strips streamed <think>...</think> blocks, aggregating
 * them into a 100ms micro-batch buffer and tracking duration.
 */
export class ThinkingExtractor {
  private currentStage?: TelemetryStage;
  private stream?: { write: (chunk: string) => any };
  private onEmit?: (envelope: TelemetryEnvelope) => void;
  private thinkingBuffer: ThinkingBatchBuffer;
  private inThinkTag: boolean = false;
  private tagBuffer: string = "";
  private accumulatedThinking: string = "";
  private thinkingStartTime: number | null = null;
  private lastDurationMs: number = 0;

  constructor(options?: ThinkingExtractorOptions) {
    this.currentStage = options?.stage;
    this.stream = options?.stream;
    this.onEmit = options?.onEmit;
    const intervalMs = options?.intervalMs ?? 100;

    this.thinkingBuffer = new ThinkingBatchBuffer({
      intervalMs,
      onFlush: (delta) => {
        const durationMs =
          this.thinkingStartTime !== null
            ? Date.now() - this.thinkingStartTime
            : this.lastDurationMs;
        this.lastDurationMs = durationMs;
        this.emitThinking(delta, { durationMs });
      },
    });
  }

  setStage(stage: TelemetryStage): void {
    this.currentStage = stage;
  }

  getStage(): TelemetryStage | undefined {
    return this.currentStage;
  }

  isThinkingActive(): boolean {
    return this.thinkingStartTime !== null || this.thinkingBuffer.hasPending();
  }

  getAccumulatedThinking(): string {
    return this.accumulatedThinking;
  }

  private emitThinking(delta: string, extra?: Record<string, any>): string {
    const formatted = emitThinkingEvent(delta, this.currentStage, extra, {
      stream: this.stream,
    });
    if (this.onEmit) {
      const parsed = parseTelemetryEnvelope(formatted);
      if (parsed) this.onEmit(parsed);
    }
    return formatted;
  }

  handleThinkingDelta(delta: string): void {
    if (this.thinkingStartTime === null) {
      this.thinkingStartTime = Date.now();
    }
    this.accumulatedThinking += delta;
    this.thinkingBuffer.append(delta);
  }

  handleThinkingEnd(): void {
    const durationMs =
      this.thinkingStartTime !== null
        ? Date.now() - this.thinkingStartTime
        : this.lastDurationMs;
    this.lastDurationMs = durationMs;

    if (this.thinkingBuffer.hasPending()) {
      const pending = this.thinkingBuffer.drain();
      this.emitThinking(pending, { durationMs, done: true });
    } else {
      this.emitThinking("", { durationMs, done: true });
    }

    this.thinkingStartTime = null;
    this.inThinkTag = false;
  }

  handleTextDelta(delta: string): { strippedText: string } {
    let current = this.tagBuffer + delta;
    this.tagBuffer = "";
    let strippedText = "";

    const openTag = "<think>";
    const closeTag = "</think>";

    while (current.length > 0) {
      if (!this.inThinkTag) {
        const openIdx = current.indexOf(openTag);
        if (openIdx !== -1) {
          strippedText += current.slice(0, openIdx);
          current = current.slice(openIdx + openTag.length);
          this.inThinkTag = true;
          if (this.thinkingStartTime === null) {
            this.thinkingStartTime = Date.now();
          }
        } else {
          // Check for trailing prefix of openTag
          let matchedLen = 0;
          for (
            let len = Math.min(openTag.length - 1, current.length);
            len > 0;
            len--
          ) {
            if (current.endsWith(openTag.slice(0, len))) {
              matchedLen = len;
              break;
            }
          }
          if (matchedLen > 0) {
            strippedText += current.slice(0, current.length - matchedLen);
            this.tagBuffer = current.slice(current.length - matchedLen);
            break;
          } else {
            strippedText += current;
            break;
          }
        }
      } else {
        const closeIdx = current.indexOf(closeTag);
        if (closeIdx !== -1) {
          const thinkContent = current.slice(0, closeIdx);
          if (thinkContent) {
            this.handleThinkingDelta(thinkContent);
          }
          this.handleThinkingEnd();
          current = current.slice(closeIdx + closeTag.length);
        } else {
          // Check for trailing prefix of closeTag
          let matchedLen = 0;
          for (
            let len = Math.min(closeTag.length - 1, current.length);
            len > 0;
            len--
          ) {
            if (current.endsWith(closeTag.slice(0, len))) {
              matchedLen = len;
              break;
            }
          }
          if (matchedLen > 0) {
            const thinkContent = current.slice(0, current.length - matchedLen);
            if (thinkContent) {
              this.handleThinkingDelta(thinkContent);
            }
            this.tagBuffer = current.slice(current.length - matchedLen);
            break;
          } else {
            this.handleThinkingDelta(current);
            break;
          }
        }
      }
    }

    return { strippedText };
  }

  handleToolStart(
    toolName: string,
    args: any,
    toolCallId?: string,
    extra?: { cwd?: string; command?: string }
  ): string {
    if (this.isThinkingActive()) {
      this.handleThinkingEnd();
    }
    return emitToolStartEvent(toolName, args, toolCallId, this.currentStage, {
      stream: this.stream,
      ...extra,
    });
  }

  handleTurnEnd(): void {
    if (this.isThinkingActive()) {
      this.handleThinkingEnd();
    }
  }

  flush(done: boolean = false): void {
    if (done) {
      if (this.isThinkingActive()) {
        this.handleThinkingEnd();
      }
    } else {
      this.thinkingBuffer.flush();
    }
  }
}

/**
 * Subscribes to an Agent instance lifecycle events and emits structured telemetry envelopes.
 */
export function subscribeAgentTelemetry(
  agent: {
    subscribe: (
      listener: (event: any, signal: any) => Promise<void> | void
    ) => () => void;
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
      const cwd =
        event.args?.cwd ?? options?.workspaceDir ?? process.cwd();
      const command = event.args?.command ?? event.args?.cmd;
      if (event.toolCallId) {
        activeToolCalls.set(event.toolCallId, {
          toolName: event.toolName,
          args: event.args,
          startTime: Date.now(),
          cwd,
          command,
        });
      }
      extractor.handleToolStart(event.toolName, event.args, event.toolCallId, {
        cwd,
        command,
      });
    } else if (event.type === "tool_execution_end") {
      const saved = event.toolCallId
        ? activeToolCalls.get(event.toolCallId)
        : undefined;
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

