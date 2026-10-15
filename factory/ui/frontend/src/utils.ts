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

import { ChatMessage, DbChatMessage, PullRequest, PullRequestStatus, DeliveryGateData } from "./types";
import { BadgeVariant } from "./components/ui/Badge";

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

  // 2. Grilling turn (grill_round, ready_for_approval, or error)
  if (
    turnData &&
    (turnData.type === "grill_round" ||
      turnData.type === "ready_for_approval" ||
      turnData.type === "error")
  ) {
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

  // 4. Delivery Gate card
  if (turnData && turnData.type === "delivery_gate") {
    return {
      id: dbMsg.id,
      role: "assistant",
      text: dbMsg.content,
      timestamp,
      turn_data: turnData,
      deliveryGate: turnData,
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

export function getLastUserPromptBefore(messages: ChatMessage[], currentMsgId: string): string | undefined {
  const msgIndex = messages.findIndex((m) => m.id === currentMsgId);
  const searchMessages = msgIndex >= 0 ? messages.slice(0, msgIndex) : messages;
  return [...searchMessages].reverse().find((m) => m.role === "user")?.text;
}

export function getPullRequestStatus(
  pr?: PullRequest | null,
  gateData?: DeliveryGateData | null
): PullRequestStatus {
  if (
    gateData?.merged ||
    pr?.merged ||
    pr?.status === "merged" ||
    gateData?.status === "merged"
  ) {
    return "merged";
  }

  if (pr?.state === "closed" || gateData?.status === "closed") {
    return "closed";
  }

  if (
    pr?.status === "conflict" ||
    pr?.mergeable === false ||
    pr?.mergeable_state === "dirty" ||
    pr?.mergeable_state === "conflict" ||
    gateData?.status === "conflict"
  ) {
    return "conflict";
  }

  if (pr?.draft || pr?.status === "draft" || gateData?.status === "draft") {
    return "draft";
  }

  return "ready_for_review";
}

export interface PullRequestBadgeConfig {
  label: string;
  variant: BadgeVariant;
  className: string;
}

export function getPullRequestBadgeConfig(status: PullRequestStatus): PullRequestBadgeConfig {
  switch (status) {
    case "merged":
      return {
        label: "Merged",
        variant: "stage",
        className: "bg-purple-950/80 text-purple-300 border-purple-800",
      };
    case "conflict":
      return {
        label: "Conflict",
        variant: "danger",
        className: "bg-rose-950/80 text-rose-300 border-rose-800",
      };
    case "draft":
      return {
        label: "Draft",
        variant: "warning",
        className: "bg-amber-950/80 text-amber-300 border-amber-800",
      };
    case "closed":
      return {
        label: "Closed",
        variant: "neutral",
        className: "bg-slate-800/80 text-slate-300 border-slate-700",
      };
    case "ready_for_review":
    default:
      return {
        label: "Ready for Review",
        variant: "success",
        className: "bg-emerald-950/80 text-emerald-300 border-emerald-800",
      };
  }
}


