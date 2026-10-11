export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (err) {
    console.error("Failed to copy to clipboard:", err);
  }
  return false;
}

export function formatToolLabel(toolName: string, data: any): string {
  const d = data || {};
  const path = d.path || d.args?.path || "file";
  const normTool = (toolName || "").toLowerCase();

  switch (normTool) {
    case "read": {
      const lines = d.lineCount !== undefined ? ` (${d.lineCount} lines)` : "";
      return `Read ${path}${lines}`;
    }
    case "write": {
      const bytes = d.bytes !== undefined ? ` (${d.bytes} B)` : "";
      return `Write ${path}${bytes}`;
    }
    case "edit":
      return `Edit ${path}`;
    case "grep": {
      const pattern = d.pattern || d.args?.pattern || "";
      const matches = d.matchCount !== undefined ? ` (${d.matchCount} matches)` : "";
      return `Grep "${pattern}" in ${path}${matches}`;
    }
    case "diff": {
      const lines = d.lineCount !== undefined ? ` (${d.lineCount} lines)` : "";
      return `Diff ${path}${lines}`;
    }
    case "bash": {
      const cmd = d.command || d.args?.command || "bash";
      return `Ran ${cmd}`;
    }
    default:
      return `${toolName} ${path}`;
  }
}

import { ChatMessage, DbChatMessage } from "./types";

export function convertDbMessageToChatMessage(dbMsg: DbChatMessage): ChatMessage {
  const timestamp =
    typeof dbMsg.created_at === "number"
      ? dbMsg.created_at < 1e11
        ? dbMsg.created_at * 1000
        : dbMsg.created_at
      : Date.now();

  if (dbMsg.role === "user") {
    return {
      id: dbMsg.id,
      role: "user",
      text: dbMsg.content,
      timestamp,
    };
  }

  const turnData = dbMsg.turn_data;

  // 1. Refusal check
  if (turnData && turnData.refusal) {
    return {
      id: dbMsg.id,
      role: "assistant",
      text: dbMsg.content,
      timestamp,
      refusal: {
        message: dbMsg.content,
        reason: turnData.reason || undefined,
        category: turnData.category || undefined,
      },
    };
  }

  // 2. Grilling turn (grill_round or ready_for_approval)
  if (turnData && (turnData.type === "grill_round" || turnData.type === "ready_for_approval")) {
    return {
      id: dbMsg.id,
      role: "assistant",
      text: turnData.formatted_text || turnData.summary || dbMsg.content,
      timestamp,
      grillTurn: turnData,
    };
  }

  // 3. Approved plan or job launch
  if (turnData && (turnData.job_id || turnData.status === "approved")) {
    return {
      id: dbMsg.id,
      role: "assistant",
      text: dbMsg.content,
      timestamp,
      jobId: turnData.job_id || undefined,
    };
  }

  // 4. Default assistant message
  return {
    id: dbMsg.id,
    role: "assistant",
    text: dbMsg.content,
    timestamp,
  };
}

