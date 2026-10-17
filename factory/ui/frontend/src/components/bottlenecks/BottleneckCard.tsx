import React, { useMemo } from "react";
import {
  Terminal,
  BrainCircuit,
  ShieldAlert,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FolderGit2,
} from "lucide-react";
import { BottleneckItem } from "./types";
import { getCategoryBadgeStyle } from "./classification";

interface BottleneckCardProps {
  item: BottleneckItem;
  rank: number;
  maxDurationMs: number;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

export const BottleneckCard: React.FC<BottleneckCardProps> = ({
  item,
  rank,
  maxDurationMs,
  isExpanded,
  onToggleExpand,
}) => {
  const percentage = Math.max(
    2,
    Math.min(100, Math.round((item.durationMs / maxDurationMs) * 100))
  );

  const isFailure =
    item.isError || (item.exitCode !== undefined && item.exitCode !== 0);

  const formatDurationDisplay = (ms: number): string => {
    return `${(ms / 1000).toFixed(2)}s (${ms}ms)`;
  };

  const isStderrLine = (line: string, stderr?: string): boolean => {
    if (!line.trim()) return false;
    const trimmed = line.trim();
    if (stderr) {
      const stderrLines = stderr
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean);
      if (stderrLines.includes(trimmed)) return true;
    }
    return /^(FAIL|FAILED|Error:|Exception:|AssertionError|Traceback|STDERR:|npm ERR!|error\[)/i.test(
      trimmed
    );
  };

  // Unify stdout and stderr so stderr is never omitted if emitted separately
  const fullOutput = useMemo(() => {
    const out = item.output || "";
    const err = item.stderr || "";
    if (out && err) {
      return out.includes(err) ? out : `${out}\n${err}`;
    }
    return out || err;
  }, [item.output, item.stderr]);

  const outputLines = fullOutput ? fullOutput.split(/\r?\n/) : [];
  if (outputLines.length > 0 && outputLines[outputLines.length - 1] === "") {
    outputLines.pop();
  }

  return (
    <div
      data-testid="bottleneck-row"
      className="bg-white border border-hairline rounded-xl p-3 shadow-2xs hover:border-slate-300 transition-colors space-y-2"
    >
      {/* Header: Rank, Type, Badges, Title, Exit Code, Duration, Chevron */}
      <div
        className="flex items-center justify-between text-xs cursor-pointer select-none"
        onClick={onToggleExpand}
        data-testid="bottleneck-card-header"
      >
        <div className="flex items-center space-x-2 truncate">
          <span
            data-testid="bottleneck-rank"
            className="font-mono font-bold text-muted text-[11px] shrink-0"
          >
            #{rank}
          </span>
          {item.type === "thinking" ? (
            <BrainCircuit className="w-3.5 h-3.5 text-purple-500 shrink-0" />
          ) : (
            <Terminal className="w-3.5 h-3.5 text-muted shrink-0" />
          )}

          {/* Infrastructure Category Badge */}
          <span
            data-testid="category-badge"
            className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border shrink-0 ${getCategoryBadgeStyle(
              item.category
            )}`}
          >
            {item.category}
          </span>

          {/* Title */}
          <span
            data-testid="bottleneck-title"
            className="font-mono font-semibold text-ink truncate text-xs"
            title={item.title}
          >
            {item.title}
          </span>

          {/* Stage Badge */}
          {item.stage && (
            <span
              data-testid="stage-badge"
              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-soft-stone text-muted shrink-0 uppercase"
            >
              {item.stage}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          {/* Exit Code Indicator */}
          {item.type === "command" && (item.exitCode !== undefined || item.isError) && (
            <span
              data-testid="exit-code-indicator"
              className={`inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-mono ${
                isFailure
                  ? "bg-coral/10 text-coral border border-coral/30"
                  : "bg-pale-green text-deep-green border border-deep-green/30"
              }`}
            >
              {isFailure ? (
                <ShieldAlert className="w-2.5 h-2.5 text-coral" />
              ) : (
                <CheckCircle2 className="w-2.5 h-2.5 text-deep-green" />
              )}
              <span>exit {item.exitCode ?? 1}</span>
            </span>
          )}

          {/* Duration */}
          <span
            data-testid="bottleneck-duration"
            className="font-mono text-xs font-semibold text-primary"
          >
            {formatDurationDisplay(item.durationMs)}
          </span>

          {/* Accordion Chevron Toggle */}
          <button
            type="button"
            data-testid="bottleneck-expand-btn"
            aria-label={isExpanded ? "Collapse bottleneck details" : "Expand bottleneck details"}
            className="text-muted hover:text-ink p-0.5 rounded hover:bg-soft-stone transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpand();
            }}
          >
            {isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Relative Duration Bar */}
      <div className="w-full bg-soft-stone/70 h-2 rounded-full overflow-hidden border border-hairline/60">
        <div
          data-testid="bottleneck-duration-bar"
          className={`h-full rounded-full transition-all duration-300 ${
            item.type === "thinking"
              ? "bg-purple-500"
              : isFailure
              ? "bg-coral"
              : "bg-primary"
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Accordion Expanded Details */}
      {isExpanded && (
        <div
          data-testid="bottleneck-expanded-details"
          className="pt-2 border-t border-hairline/70 space-y-2.5 text-xs animate-in fade-in duration-150"
        >
          {item.type === "command" ? (
            <>
              {/* Working Directory */}
              {item.cwd && (
                <div className="flex items-center space-x-1.5 text-[11px] font-mono text-slate-600 bg-soft-stone/40 px-2 py-1 rounded border border-hairline/50">
                  <FolderGit2 className="w-3.5 h-3.5 text-muted shrink-0" />
                  <span className="text-muted text-[10px] uppercase font-semibold">cwd:</span>
                  <span data-testid="expanded-cwd" className="text-ink break-all select-text">
                    {item.cwd}
                  </span>
                </div>
              )}

              {/* Command String */}
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-semibold block">
                  Command
                </span>
                <div
                  data-testid="expanded-command-string"
                  className="font-mono text-xs text-ink bg-soft-stone/50 p-2 rounded border border-hairline break-all select-text leading-relaxed"
                >
                  {item.title}
                </div>
              </div>

              {/* Output (stdout/stderr with highlighted error lines) */}
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-semibold block">
                  Output (stdout / stderr)
                </span>
                <div
                  data-testid="expanded-output"
                  className="font-mono text-[11px] leading-relaxed max-h-72 overflow-y-auto bg-primary text-slate-300 p-2.5 rounded border border-white/10 select-text"
                >
                  {outputLines.length > 0 ? (
                    outputLines.map((line, idx) => {
                      const isErr = isStderrLine(line, item.stderr);
                      return (
                        <div
                          key={idx}
                          data-testid={isErr ? "stderr-line" : undefined}
                          className={
                            isErr
                              ? "stderr-line text-red-400 font-semibold bg-red-950/40 px-1 rounded my-0.5"
                              : "text-slate-300"
                          }
                        >
                          {line || "\u00A0"}
                        </div>
                      );
                    })
                  ) : (
                    <span className="text-slate-500 italic">No output recorded.</span>
                  )}
                </div>
              </div>
            </>
          ) : (
            /* LLM Thinking Details */
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-semibold block">
                Reasoning Process
              </span>
              <div
                data-testid="expanded-thinking-text"
                className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words max-h-72 overflow-y-auto bg-cohere-black/80 text-slate-200 p-3 rounded border border-white/10 select-text"
              >
                {item.output || "No reasoning text available."}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
