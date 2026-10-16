import React, { useState } from "react";
import { ChevronDown, ChevronRight, BrainCircuit } from "lucide-react";

interface ThinkingAccordionProps {
  stage?: string;
  text: string;
  durationMs?: number;
  done?: boolean;
  defaultExpanded?: boolean;
}

export const ThinkingAccordion: React.FC<ThinkingAccordionProps> = ({
  stage,
  text,
  durationMs,
  done = false,
  defaultExpanded,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(
    defaultExpanded !== undefined ? defaultExpanded : !done
  );

  const formattedDuration = durationMs
    ? `${(durationMs / 1000).toFixed(1)}s`
    : null;

  return (
    <div className="thinking-accordion my-2 rounded-lg border border-white/10 bg-primary text-xs overflow-hidden transition-all duration-200">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/5 transition-colors focus:outline-none cursor-pointer"
      >
        <div className="flex items-center space-x-2">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              !done
                ? "bg-emerald-400 animate-pulse ring-2 ring-emerald-400/40"
                : "bg-muted"
            }`}
          />
          <BrainCircuit className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-medium text-slate-200">
            {!done ? "Thinking..." : "Thought Process"}
          </span>
          {stage && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-white/10 text-slate-300 font-mono">
              {stage}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {done && formattedDuration && (
            <span className="text-[11px] text-slate-400">
              Reasoning finished in {formattedDuration}
            </span>
          )}
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="px-3 py-2 border-t border-white/10 text-slate-300 font-mono text-[11px] whitespace-pre-wrap max-h-72 overflow-y-auto leading-relaxed bg-cohere-black/70">
          {text || "No reasoning text available."}
        </div>
      )}
    </div>
  );
};
