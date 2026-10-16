import React, { useState } from "react";
import { GitCompare, ChevronDown, ChevronRight } from "lucide-react";

interface DiffViewerProps {
  id?: string;
  path: string;
  diff: string;
  stage?: string;
  defaultExpanded?: boolean;
}

interface ParsedLine {
  type: "header" | "hunk" | "addition" | "deletion" | "context";
  text: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  id,
  path,
  diff,
  stage,
  defaultExpanded = true,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded);

  const rawLines = diff ? diff.split(/\r?\n/) : [];
  let additions = 0;
  let deletions = 0;

  const parsedLines: ParsedLine[] = rawLines.map((line) => {
    if (line.startsWith("+++") || line.startsWith("---")) {
      return { type: "header", text: line };
    }
    if (line.startsWith("+")) {
      additions++;
      return { type: "addition", text: line };
    }
    if (line.startsWith("-")) {
      deletions++;
      return { type: "deletion", text: line };
    }
    if (line.startsWith("@@")) {
      return { type: "hunk", text: line };
    }
    return { type: "context", text: line };
  });

  return (
    <div
      id={id}
      className="diff-preview-card my-2 rounded-xl border border-white/10 bg-primary text-xs overflow-hidden transition-all duration-200 shadow-sm"
    >
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 bg-cohere-black/60 hover:bg-cohere-black text-left transition-colors border-b border-white/10 focus:outline-none cursor-pointer"
      >
        <div className="flex items-center space-x-2 truncate">
          <GitCompare className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span className="font-mono font-semibold text-slate-200 truncate">
            {path}
          </span>
          {stage && (
            <span className="px-2 py-0.5 rounded-pill text-[10px] bg-cohere-black text-slate-300 font-mono border border-white/10">
              {stage}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <div className="flex items-center space-x-1.5 font-mono text-[11px]">
            <span className="diff-additions text-pale-green font-medium">
              +{additions}
            </span>
            <span className="diff-deletions text-coral font-medium">
              -{deletions}
            </span>
          </div>
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="p-2 font-mono text-[11px] leading-relaxed max-h-80 overflow-y-auto bg-primary">
          {parsedLines.map((pl, idx) => {
            let lineClass = "text-slate-300 px-2 py-0.5";
            if (pl.type === "header") {
              lineClass = "text-slate-500 font-bold px-2 py-0.5";
            } else if (pl.type === "hunk") {
              lineClass = "text-cyan-300 bg-white/5 px-2 py-0.5 my-0.5 rounded";
            } else if (pl.type === "addition") {
              lineClass = "diff-addition text-pale-green bg-pale-green/10 px-2 py-0.5 border-l-2 border-pale-green";
            } else if (pl.type === "deletion") {
              lineClass = "diff-deletion text-coral bg-coral/10 px-2 py-0.5 border-l-2 border-coral";
            }

            return (
              <div key={idx} className={lineClass}>
                {pl.text || "\u00A0"}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
