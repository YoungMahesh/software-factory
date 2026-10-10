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
