/**
 * Telemetry event payload serialization, JSON stringification, timestamp injection,
 * and diff/patch formatting.
 */

import { generateUnifiedPatch } from "@earendil-works/pi-coding-agent";
import type { ReviewVerdict } from "../harness.ts";
import {
  EVENT_PREFIX,
  type DeliveryGateEventData,
  type TelemetryEnvelope,
  type TelemetryEventInput,
  type ToolResultOptions,
  type ToolStartOptions,
} from "./types.ts";

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
 * Formats and normalizes payload data for a tool execution start event.
 */
export function formatToolStartData(
  toolName: string,
  args: any,
  toolCallId?: string,
  options?: ToolStartOptions
): Record<string, any> {
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
  } else {
    const targetPath = args?.path ?? options?.path ?? "";

    if (toolName === "edit") {
      const editCount = Array.isArray(args?.edits) ? args.edits.length : 1;
      data.path = targetPath;
      data.args = { path: targetPath, editCount };
    } else if (toolName === "write") {
      const bytes =
        args?.content !== undefined
          ? Buffer.byteLength(String(args.content), "utf8")
          : (options?.bytes ?? args?.bytes ?? 0);
      data.path = targetPath;
      data.bytes = bytes;
      data.args = { path: targetPath, bytes };
    } else if (toolName === "read") {
      data.path = targetPath;
      data.args = {
        path: targetPath,
        ...(args?.offset !== undefined ? { offset: args.offset } : {}),
        ...(args?.limit !== undefined ? { limit: args.limit } : {}),
      };
    } else if (toolName === "grep") {
      const pattern = args?.pattern ?? options?.pattern ?? "";
      data.pattern = pattern;
      if (targetPath) data.path = targetPath;
      data.args = {
        pattern,
        ...(targetPath ? { path: targetPath } : {}),
        ...(args?.glob ? { glob: args.glob } : {}),
      };
    } else if (toolName === "diff") {
      if (targetPath) data.path = targetPath;
      data.args = {
        ...(targetPath ? { path: targetPath } : {}),
        ...(args?.cached !== undefined ? { cached: args.cached } : {}),
        ...(args?.commit ? { commit: args.commit } : {}),
      };
    }
  }

  return data;
}

/**
 * Formats, normalizes, and constructs diff/patch representations for tool completion results.
 */
export function formatToolResultData(
  toolName: string,
  result: any,
  isError: boolean = false,
  toolCallId?: string,
  durationMs?: number,
  options?: ToolResultOptions
): Record<string, any> {
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

  const targetPath = options?.path ?? result?.path ?? options?.args?.path ?? "";

  if (toolName === "bash" || cmd !== undefined) {
    if (cmd !== undefined) data.command = cmd;
    if (cwd !== undefined) data.cwd = cwd;
    data.exitCode = exitCode;
    data.stdout = stdout;
    data.stderr = stderr;
    data.output = output;
  } else if (toolName === "read") {
    let lineCount = options?.lineCount ?? result?.lineCount;
    if (typeof lineCount !== "number") {
      const text =
        typeof result === "string"
          ? result
          : (typeof result?.structuredContent === "string"
            ? result.structuredContent
            : result?.content?.[0]?.text ?? "");
      if (text === "") {
        lineCount = 0;
      } else {
        const lines = text.split("\n");
        lineCount = text.endsWith("\n") ? lines.length - 1 : lines.length;
      }
    }
    data.path = targetPath;
    data.lineCount = lineCount;
    data.result = { path: targetPath, lineCount };
  } else if (toolName === "write") {
    const bytes =
      options?.bytes ??
      (options?.args?.content !== undefined
        ? Buffer.byteLength(String(options.args.content), "utf8")
        : (result?.bytes ?? 0));
    data.path = targetPath;
    data.bytes = bytes;
    data.result = { path: targetPath, bytes };
  } else if (toolName === "edit") {
    let diff =
      options?.diff ??
      options?.patch ??
      result?.details?.patch ??
      result?.patch ??
      result?.diff ??
      result?.details?.diff;

    if (!diff && Array.isArray(options?.args?.edits)) {
      let gen = "";
      for (const e of options.args.edits) {
        if (e && e.oldText !== undefined && e.newText !== undefined) {
          gen += generateUnifiedPatch(targetPath || "file", e.oldText, e.newText) + "\n";
        }
      }
      if (gen) diff = gen.trim();
    } else if (!diff && result?.oldContent !== undefined && result?.newContent !== undefined) {
      diff = generateUnifiedPatch(targetPath || "file", result.oldContent, result.newContent);
    } else if (!diff && typeof result === "string" && (result.includes("---") || result.includes("@@"))) {
      diff = result;
    }

    if (!diff) {
      diff = "";
    }

    data.path = targetPath;
    data.diff = diff;
    data.patch = diff;
    if (finalIsError) {
      const errText =
        typeof result === "string"
          ? result
          : (result?.error ?? result?.message ?? result?.content?.[0]?.text ?? "Edit failed");
      data.result = errText;
      data.error = errText;
    } else {
      data.result =
        typeof result === "string" && !result.includes("---") && !result.includes("@@")
          ? result
          : { path: targetPath, diff };
    }
  } else if (toolName === "grep") {
    const pattern = options?.pattern ?? result?.pattern ?? options?.args?.pattern ?? "";
    let matchCount = options?.matchCount ?? result?.matchCount;
    if (typeof matchCount !== "number") {
      const text = typeof result === "string" ? result : result?.content?.[0]?.text ?? "";
      if (!text || text.startsWith("No matches found")) {
        matchCount = 0;
      } else {
        const lines = text
          .split("\n")
          .filter((l: string) => !l.startsWith("[") && !l.endsWith("]") && l.trim().length > 0);
        const matchLines = lines.filter((l: string) => /:\d+:/.test(l));
        matchCount = matchLines.length > 0 ? matchLines.length : lines.length;
      }
    }
    data.path = targetPath;
    data.pattern = pattern;
    data.matchCount = matchCount;
    data.result = { path: targetPath, pattern, matchCount };
  } else if (toolName === "diff") {
    let lineCount = options?.lineCount ?? result?.lineCount;
    if (typeof lineCount !== "number") {
      const text = typeof result === "string" ? result : result?.content?.[0]?.text ?? "";
      if (!text || text.startsWith("No changes detected") || text.startsWith("No diff output")) {
        lineCount = 0;
      } else {
        lineCount = text.split("\n").filter((l: string) => l.trim().length > 0).length;
      }
    }
    data.path = targetPath;
    data.lineCount = lineCount;
    data.result = { path: targetPath, lineCount };
  }

  return data;
}

/**
 * Normalizes self-correction loop attempt telemetry payload.
 */
export function formatAttemptData(
  attempt: number,
  maxAttempts: number,
  data: Record<string, any> = {}
): Record<string, any> {
  return { attempt, maxAttempts, ...data };
}

/**
 * Normalizes self-correction loop attempt_start telemetry payload.
 */
export function formatAttemptStartData(
  attempt: number,
  maxRetries: number,
  reason?: string,
  data: Record<string, any> = {}
): Record<string, any> {
  return {
    attempt,
    maxRetries,
    maxAttempts: maxRetries + 1,
    ...(reason !== undefined ? { reason } : {}),
    ...data,
  };
}

/**
 * Normalizes reviewer rejection diagnostics payload.
 */
export function formatReviewerRejectionData(
  verdict: Partial<ReviewVerdict> | Record<string, any>
): Record<string, any> {
  return {
    verdict: typeof verdict === "object" ? verdict?.verdict : verdict,
    summary: verdict?.summary,
    remediation: verdict?.remediation,
    issues: verdict?.issues,
    specCompliance: verdict?.specCompliance,
    standardsCompliance: verdict?.standardsCompliance,
  };
}

/**
 * Normalizes Feature Pull Request delivery gate telemetry payload.
 */
export function formatDeliveryGateData(
  data: DeliveryGateEventData
): DeliveryGateEventData {
  return {
    ...data,
    ...(data.pullRequestNumber !== undefined && data.pull_request_number === undefined
      ? { pull_request_number: data.pullRequestNumber }
      : {}),
    ...(data.pullRequestUrl !== undefined
      ? {
          ...(data.pull_request_url === undefined ? { pull_request_url: data.pullRequestUrl } : {}),
          ...(data.html_url === undefined ? { html_url: data.pullRequestUrl } : {}),
        }
      : {}),
  };
}
