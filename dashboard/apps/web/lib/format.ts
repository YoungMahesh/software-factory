import {
  FreshLaunchStreamEventSchema,
  type FreshLaunchStreamEvent,
  type LaunchResponse,
  type SandboxCost,
  type SandboxSummary,
  type ScratchpadNoteSummaryView,
} from "@dashboard/types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    const day = String(d.getDate()).padStart(2, "0");
    const month = MONTHS[d.getMonth()];
    const year = d.getFullYear();
    let hours = d.getHours();
    const minutes = String(d.getMinutes()).padStart(2, "0");
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    return `${day} ${month} ${year} ${String(hours).padStart(2, "0")}:${minutes} ${ampm}`;
  } catch {
    return "—";
  }
}

export function formatTimeout(seconds: number | null | undefined): string {
  if (!seconds || typeof seconds !== "number" || seconds <= 0) return "";
  if (seconds % 86400 === 0) {
    const days = seconds / 86400;
    return `${days} ${days === 1 ? "day" : "days"} timeout`;
  }
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} ${hours === 1 ? "hour" : "hours"} timeout`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `${minutes} ${minutes === 1 ? "minute" : "minutes"} timeout`;
  }
  const hours = Math.round(seconds / 3600);
  if (hours >= 1) {
    return `${hours} ${hours === 1 ? "hour" : "hours"} timeout`;
  }
  const minutes = Math.round(seconds / 60);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"} timeout`;
}

export function formatUsdCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined || !Number.isFinite(cost)) return "—";
  if (cost <= 0) return "$0.00";
  if (cost < 0.0001) return "<$0.0001";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function formatCostBreakdown(
  costByResource: Record<string, number> | null | undefined,
): string {
  if (!costByResource) return "";
  const priority: Record<string, number> = { CPU: 0, Memory: 1 };
  const entries = Object.entries(costByResource)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value) && value > 0)
    .sort(([a], [b]) => {
      const pa = priority[a] ?? 99;
      const pb = priority[b] ?? 99;
      return pa !== pb ? pa - pb : a.localeCompare(b);
    });
  if (entries.length === 0) return "";
  return entries
    .map(([resource, value]) => {
      const label = resource === "Memory" ? "Mem" : resource;
      return `${label} ${formatUsdCost(value)}`;
    })
    .join(" · ");
}

export function formatDurationCompact(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "";
  }
  const totalMinutes = Math.floor(seconds / 60);
  if (totalMinutes < 1) return "<1m";
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

export function summarizeSandboxCosts(
  sandboxes: ReadonlyArray<{ id: string }>,
  costs: Record<string, SandboxCost | undefined>,
): { totalUsd: number | null; knownCount: number; pendingCount: number } {
  let total = 0;
  let knownCount = 0;
  let pendingCount = 0;
  for (const sb of sandboxes) {
    const costVal = costs[sb.id]?.cost_usd;
    if (typeof costVal === "number" && Number.isFinite(costVal)) {
      total += costVal;
      knownCount += 1;
    } else {
      pendingCount += 1;
    }
  }
  return {
    totalUsd: knownCount > 0 ? total : null,
    knownCount,
    pendingCount,
  };
}

export function slugifyScratchpadTitle(title: string): string {
  const ascii = (title || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/g, "");
  return slug || "untitled-note";
}

export function previewScratchpadTargetPath(
  title: string,
  existingIdeas: ScratchpadNoteSummaryView[],
  configRepo: string,
): string {
  const existing = new Set(existingIdeas.map((n) => (n.filename || "").toLowerCase()));
  const base = slugifyScratchpadTitle(title);
  let candidate = base;
  let counter = 2;
  while (existing.has(`${candidate}.md`)) {
    const suffix = `-${counter}`;
    const stem = base.slice(0, Math.max(1, 80 - suffix.length)).replace(/-+$/g, "");
    candidate = `${stem}${suffix}`;
    counter += 1;
  }
  const prefix = configRepo ? `${configRepo}/` : "";
  return `${prefix}scratchpad/${candidate}.md`;
}

export function getLaunchSshCommand(result: LaunchResponse | null): string {
  if (!result) return "";
  if (result.ssh_command) return result.ssh_command;
  if (result.ssh_info) {
    return `ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p ${result.ssh_info[1]} root@${result.ssh_info[0]}`;
  }
  return `modal shell ${result.sandbox_id}`;
}

export function getLaunchSshConfig(result: LaunchResponse | null): string {
  if (!result) return "";
  if (result.ssh_config) return result.ssh_config;
  if (result.ssh_info) {
    const [host, port] = result.ssh_info;
    const name = result.t3_ssh_host || result.sandbox_name || result.app_name || result.sandbox_id;
    return [
      `Host ${name}`,
      `  HostName ${host}`,
      `  Port ${port}`,
      `  User root`,
      `  IdentityFile ~/.ssh/modal-sandbox`,
      `  StrictHostKeyChecking no`,
      `  UserKnownHostsFile /dev/null`,
      "",
    ].join("\n");
  }
  return getLaunchSshCommand(result);
}

export function getSandboxCopyTarget(sb: SandboxSummary): { text: string; toast: string } {
  if (sb.ssh_config) {
    return {
      text: sb.ssh_config,
      toast: "SSH config snippet copied! Append to ~/.ssh/config",
    };
  }
  const cmd = sb.ssh_command || (sb.name ? `ssh ${sb.name}` : `modal shell ${sb.id}`);
  return {
    text: cmd,
    toast: `SSH command copied: ${cmd}`,
  };
}

export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false;
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fallback below
    }
  }
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

export async function extractApiError(response: Response, fallback?: string): Promise<{
  code?: string;
  message: string;
}> {
  const defaultMsg = fallback || `Server error (${response.status})`;
  try {
    const data = await response.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return { message: detail };
      }
      if (detail && typeof detail === "object") {
        const obj = detail as { code?: unknown; message?: unknown };
        const message = typeof obj.message === "string" ? obj.message : defaultMsg;
        const code = typeof obj.code === "string" ? obj.code : undefined;
        return { code, message };
      }
    }
  } catch {
    // Ignore parse error
  }
  return { message: defaultMsg };
}

export async function consumeSseStream(
  response: Response,
  onEvent: (event: FreshLaunchStreamEvent) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error("Response stream was unavailable.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const processBlock = (block: string) => {
    const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
    if (!dataLine) return;
    let rawJson: unknown;
    try {
      rawJson = JSON.parse(dataLine.slice(6));
    } catch {
      return;
    }
    const parsed = FreshLaunchStreamEventSchema.safeParse(rawJson);
    if (parsed.success) {
      onEvent(parsed.data);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      processBlock(block);
    }
  }

  if (buffer.trim()) {
    processBlock(buffer);
  }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) {
    return "—";
  }
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  if (unitIndex === 0) return `${Math.round(value)} B`;
  const formatted = value >= 100 ? value.toFixed(0) : value.toFixed(value >= 10 ? 1 : 2);
  const trimmed = formatted.includes(".") ? formatted.replace(/\.?0+$/, "") : formatted;
  return `${trimmed} ${units[unitIndex]}`;
}
