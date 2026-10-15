/**
 * In-Sandbox Agent Event Stream Telemetry Emitter.
 *
 * Formats structured telemetry events (thinking, tool_start, tool_result, stage, attempt)
 * into single-line JSON envelopes tagged with '__SF_EVENT__:' and transmits them unbuffered
 * through container stdout to the host JobRegistry and SSE stream.
 */

export * from "./types.ts";
export * from "./formatter.ts";
export * from "./parser.ts";
export * from "./emitter.ts";
