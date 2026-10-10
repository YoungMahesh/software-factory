import React from "react";
import { FileText, FileEdit, Terminal, Search, GitCompare, Code2 } from "lucide-react";

interface ToolChipProps {
  toolName: string;
  toolCallId?: string;
  stage?: string;
  data: any;
  onClick?: (toolCallId?: string) => void;
}

export const ToolChip: React.FC<ToolChipProps> = ({
  toolName,
  toolCallId,
  stage,
  data,
  onClick,
}) => {
  const getIcon = () => {
    switch (toolName.toLowerCase()) {
      case "read":
        return <FileText className="w-3 h-3 text-sky-400 shrink-0" />;
      case "write":
        return <FileEdit className="w-3 h-3 text-emerald-400 shrink-0" />;
      case "edit":
        return <Code2 className="w-3 h-3 text-amber-400 shrink-0" />;
      case "grep":
        return <Search className="w-3 h-3 text-purple-400 shrink-0" />;
      case "diff":
        return <GitCompare className="w-3 h-3 text-indigo-400 shrink-0" />;
      case "bash":
      default:
        return <Terminal className="w-3 h-3 text-slate-400 shrink-0" />;
    }
  };

  const getLabel = () => {
    const d = data || {};
    const path = d.path || d.args?.path || "file";
    switch (toolName.toLowerCase()) {
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
  };

  return (
    <button
      type="button"
      onClick={() => onClick && onClick(toolCallId)}
      className="tool-chip inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-slate-900/80 hover:bg-slate-800 text-slate-300 border border-slate-800/80 hover:border-slate-700 transition-colors shadow-sm focus:outline-none"
    >
      {getIcon()}
      <span className="truncate max-w-[280px]">{getLabel()}</span>
      {stage && (
        <span className="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400">
          {stage}
        </span>
      )}
    </button>
  );
};
