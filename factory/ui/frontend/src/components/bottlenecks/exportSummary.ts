import { BottleneckItem } from "./types";
import { RepoBottleneck } from "../../types";

function sanitizeCell(text: string): string {
  return (text || "")
    .replace(/\r?\n/g, " ")
    .replace(/\|/g, "\\|")
    .trim();
}

export function formatBottlenecksMarkdown(items: BottleneckItem[]): string {
  const headers = ["Rank", "Category", "Stage", "Operation", "Duration", "Status"];
  const divider = ["---:", ":---", ":---", ":---", "---:", ":---"];

  if (!items || items.length === 0) {
    return [`| ${headers.join(" | ")} |`, `| ${divider.join(" | ")} |`].join("\n");
  }

  const rows = items.map((item, idx) => {
    const rank = idx + 1;
    const category = item.category || "Command";
    const stage = item.stage || "—";
    const cleanTitle = sanitizeCell(item.title);
    const operation = item.type === "command" ? `\`${cleanTitle}\`` : cleanTitle;
    const duration = `${(item.durationMs / 1000).toFixed(2)}s (${item.durationMs}ms)`;

    let status = "Success";
    if (item.type === "command") {
      if (item.exitCode !== undefined) {
        status = `Exit ${item.exitCode}`;
      } else if (item.isError) {
        status = "Error";
      }
    }

    return `| ${rank} | ${category} | ${stage} | ${operation} | ${duration} | ${status} |`;
  });

  return [
    `| ${headers.join(" | ")} |`,
    `| ${divider.join(" | ")} |`,
    ...rows,
  ].join("\n");
}

export function formatRepoBottlenecksMarkdown(
  bottlenecks: RepoBottleneck[]
): string {
  const headers = [
    "Rank",
    "Operation",
    "Category",
    "Stage",
    "Total Duration",
    "Invocations",
    "Avg Duration",
    "Max Duration",
  ];
  const divider = ["---:", ":---", ":---", ":---", "---:", "---:", "---:", "---:"];

  if (!bottlenecks || bottlenecks.length === 0) {
    return [`| ${headers.join(" | ")} |`, `| ${divider.join(" | ")} |`].join("\n");
  }

  const rows = bottlenecks.map((item, idx) => {
    const rank = idx + 1;
    const isThinking = item.category === "LLM Thinking";
    const cleanCmd = sanitizeCell(item.command);
    const operation = isThinking ? cleanCmd : `\`${cleanCmd}\``;
    const category = item.category || (isThinking ? "LLM Thinking" : "Command");
    const stage = item.stage || "—";
    const total = `${(item.total_duration_ms / 1000).toFixed(2)}s`;
    const count = item.invocation_count ?? item.count ?? 1;
    const avg = `${(item.avg_duration_ms / 1000).toFixed(2)}s`;
    const max =
      item.max_duration_ms !== undefined
        ? `${(item.max_duration_ms / 1000).toFixed(2)}s`
        : "—";

    return `| ${rank} | ${operation} | ${category} | ${stage} | ${total} | ${count} | ${avg} | ${max} |`;
  });

  return [
    `| ${headers.join(" | ")} |`,
    `| ${divider.join(" | ")} |`,
    ...rows,
  ].join("\n");
}
