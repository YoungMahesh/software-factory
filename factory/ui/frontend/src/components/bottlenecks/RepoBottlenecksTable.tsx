import React from "react";
import { Loader2, AlertCircle, RefreshCw, Terminal, BrainCircuit } from "lucide-react";
import { RepoBottleneck } from "../../types";
import { getCategoryBadgeStyle } from "./classification";
import { InfrastructureCategory } from "./types";

export interface RepoBottlenecksTableProps {
  repo?: string;
  bottlenecks?: RepoBottleneck[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function formatDuration(ms: number): string {
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }
  return `${Math.round(ms)}ms`;
}

export const RepoBottlenecksTable: React.FC<RepoBottlenecksTableProps> = ({
  repo,
  bottlenecks = [],
  isLoading = false,
  error = null,
  onRetry,
}) => {
  if (isLoading) {
    return (
      <div
        data-testid="repo-bottlenecks-loading"
        className="flex flex-col items-center justify-center py-12 space-y-3 bg-white rounded-xl border border-hairline p-6 text-center"
      >
        <Loader2 className="w-5 h-5 text-primary animate-spin" />
        <span className="text-xs font-mono text-muted">
          Loading repository aggregated bottlenecks...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="repo-bottlenecks-error"
        className="p-4 rounded-xl bg-red-500/10 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-xs flex items-center justify-between gap-3"
      >
        <div className="flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="font-mono">{error}</span>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center space-x-1 px-2.5 py-1 rounded-pill bg-white dark:bg-slate-900 border border-red-300 dark:border-red-800 text-ink text-[11px] font-mono hover:bg-soft-stone transition-colors cursor-pointer shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        )}
      </div>
    );
  }

  if (!repo || !repo.trim()) {
    return (
      <div className="text-center py-12 text-slate-500 text-xs font-mono bg-white rounded-xl border border-hairline p-6">
        Select a repository to view aggregated bottlenecks across past runs.
      </div>
    );
  }

  if (bottlenecks.length === 0) {
    return (
      <div
        data-testid="repo-bottlenecks-empty"
        className="text-center py-12 text-slate-500 text-xs font-mono bg-white rounded-xl border border-hairline p-6"
      >
        No aggregated bottlenecks recorded for this repository yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1 text-xs">
        <span className="font-sans font-semibold text-ink">
          Repository Recurring Bottlenecks ({bottlenecks.length})
        </span>
        <span className="text-[10px] font-mono text-muted">
          Sorted by cumulative execution time
        </span>
      </div>

      <div
        data-testid="repo-bottlenecks-table"
        className="overflow-x-auto bg-white rounded-xl border border-hairline shadow-2xs"
      >
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-hairline bg-soft-stone/40 text-[10px] font-mono uppercase tracking-wider text-muted">
              <th className="py-2.5 px-3 w-10 text-center">#</th>
              <th className="py-2.5 px-3">Command / Phase</th>
              <th className="py-2.5 px-3 text-right">Total Duration</th>
              <th className="py-2.5 px-3 text-center">Invocations</th>
              <th className="py-2.5 px-3 text-right">Avg Duration</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline/60">
            {bottlenecks.map((item, index) => {
              const rank = index + 1;
              const isThinking = item.category === "LLM Thinking";
              const categoryBadge = getCategoryBadgeStyle(
                (item.category as InfrastructureCategory) || "Command"
              );

              return (
                <tr
                  key={`${item.command}-${index}`}
                  className="hover:bg-soft-stone/30 transition-colors"
                >
                  {/* Rank */}
                  <td className="py-2.5 px-3 text-center font-mono text-[11px] font-bold text-muted">
                    #{rank}
                  </td>

                  {/* Command / Phase with Badges */}
                  <td className="py-2.5 px-3">
                    <div className="flex items-start space-x-2">
                      {isThinking ? (
                        <BrainCircuit className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
                      ) : (
                        <Terminal className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                      )}
                      <div className="space-y-1 min-w-0">
                        <span className="font-mono text-[11px] font-semibold text-ink break-all block">
                          {item.command}
                        </span>
                        <div className="flex items-center space-x-1.5 flex-wrap gap-y-1">
                          <span
                            className={`px-1.5 py-0.2 rounded-pill text-[9px] font-mono font-medium border ${categoryBadge}`}
                          >
                            {item.category}
                          </span>
                          {item.stage && (
                            <span className="px-1.5 py-0.2 rounded-pill text-[9px] font-mono bg-soft-stone text-muted border border-hairline uppercase">
                              {item.stage}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* Total Duration */}
                  <td className="py-2.5 px-3 text-right font-mono text-[11px] font-bold text-ink whitespace-nowrap">
                    {formatDuration(item.total_duration_ms)}
                  </td>

                  {/* Invocations */}
                  <td className="py-2.5 px-3 text-center font-mono text-[11px] text-muted whitespace-nowrap">
                    {item.count}
                  </td>

                  {/* Avg Duration */}
                  <td className="py-2.5 px-3 text-right font-mono text-[11px] text-slate-600 dark:text-slate-300 whitespace-nowrap">
                    {formatDuration(item.avg_duration_ms)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
