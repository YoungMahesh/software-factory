import { ChatMessage, AgentEvent, Job } from "../types";
import { formatToolLabel } from "../utils";

/**
 * Pure reducer function to fold real-time telemetry events into conversational chat messages.
 *
 * Updates reasoning deltas, deduplicates sequential tool execution chips, and reflects stage transitions
 * without mutating input messages.
 */
export function foldTelemetryEvents(
  messages: ChatMessage[],
  events: AgentEvent[],
  activeJobId?: string | null,
  activeJob?: Job | null
): ChatMessage[] {
  if (!events || events.length === 0 || !activeJobId) {
    return messages;
  }

  const existingMsg = messages.find((m) => m.role === "assistant" && m.jobId === activeJobId);
  const isNew = !existingMsg;

  const baseMsg: ChatMessage = existingMsg
    ? existingMsg
    : {
        id: `assistant-${activeJobId}`,
        role: "assistant",
        timestamp: Date.now(),
        jobId: activeJobId,
        stage: activeJob?.stage,
        text: `Assembly line execution for ${activeJob?.feature || activeJob?.repo || activeJobId}`,
        stepChips: [],
      };

  const updated: ChatMessage = {
    ...baseMsg,
    stepChips: [...(baseMsg.stepChips || [])],
    thinking: baseMsg.thinking ? { ...baseMsg.thinking } : undefined,
  };

  let hasThinkingEvent = false;
  let accumulatedThinkingText = "";
  let durationMs = baseMsg.thinking?.durationMs;
  let isDone = baseMsg.thinking?.done ?? false;

  events.forEach((evt) => {
    if (evt.type === "thinking") {
      hasThinkingEvent = true;
      if (evt.data?.delta) {
        accumulatedThinkingText += evt.data.delta;
      }
      if (evt.data?.durationMs !== undefined) {
        durationMs = evt.data.durationMs;
      }
      if (evt.data?.done !== undefined) {
        isDone = Boolean(evt.data.done);
      }
    }
  });

  if (hasThinkingEvent) {
    updated.thinking = {
      text: accumulatedThinkingText,
      durationMs,
      done: isDone,
    };
  }

  events.forEach((evt) => {

    if (evt.type === "tool_result") {
      const chipId = evt.data?.toolCallId || `chip-${evt.data?.toolName}-${evt.timestamp || Date.now()}`;
      if (!updated.stepChips!.some((c) => c.id === chipId)) {
        const toolName = evt.data?.toolName || "tool";
        const label = `[${formatToolLabel(toolName, evt.data)}]`;

        updated.stepChips!.push({
          id: chipId,
          toolName,
          label,
          data: evt.data,
          stage: evt.stage,
          toolCallId: evt.data?.toolCallId,
        });
      }
    }

    if (evt.stage && !updated.stage) {
      updated.stage = evt.stage;
    }
  });

  if (isNew) {
    return [...messages, updated];
  }
  return messages.map((m) => (m.id === updated.id ? updated : m));
}
