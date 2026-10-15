/**
 * In-stream event line extraction, prefix stripping, error parsing,
 * and dual-extraction thinking stream parser.
 */

import { ThinkingBatchBuffer, emitThinkingEvent, emitToolStartEvent } from "./emitter.ts";
import {
  EVENT_PREFIX,
  type TelemetryEnvelope,
  type TelemetryStage,
  type ThinkingExtractorOptions,
  type ToolStartOptions,
} from "./types.ts";

/**
 * Strips <think>...</think> reasoning blocks from text.
 */
export function stripThinkTags(content: string): string {
  return content.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
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
    extra?: ToolStartOptions
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
