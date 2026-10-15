import React, { useState } from "react";
import {
  ExternalLink,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  MessageSquareQuote,
  Lock,
  Zap,
} from "lucide-react";
import { Issue } from "../../types";

export interface IssueCardProps {
  issue: Issue;
  isResolved: boolean;
  openBlockers: string[];
  onGrillAndAlign: (issue: Issue) => void;
  onInstantDispatch: (issue: Issue) => Promise<void> | void;
}

export const IssueCard: React.FC<IssueCardProps> = ({
  issue,
  isResolved,
  openBlockers,
  onGrillAndAlign,
  onInstantDispatch,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const isBlocked = openBlockers.length > 0;
  const isClaimed =
    issue.labels?.includes("factory:claimed") || issue.status === "claimed";

  let disableInstantReason = "";
  if (isBlocked) {
    disableInstantReason = `Blocked by open issue(s): #${openBlockers.join(", #")}`;
  } else if (isClaimed) {
    disableInstantReason = "Issue is currently claimed by an active job (factory:claimed)";
  } else if (isResolved) {
    disableInstantReason = "Issue is already resolved";
  }

  const isInstantDisabled = isBlocked || isClaimed || isResolved;

  return (
    <div
      key={issue.number}
      data-testid={`issue-card-${issue.number}`}
      className="p-3.5 rounded-lg bg-slate-900 border border-slate-800/90 hover:border-slate-700/80 transition-colors space-y-2.5"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start space-x-2">
          <span className="text-xs font-mono font-bold text-indigo-400 shrink-0 mt-0.5">
            #{issue.number}
          </span>
          <span className="text-xs font-semibold text-slate-200 leading-snug">
            {issue.title}
          </span>
        </div>

        {issue.html_url && (
          <a
            href={issue.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-500 hover:text-slate-300 p-0.5 transition-colors shrink-0"
            title="View on GitHub"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>

      {/* Labels & Status Row */}
      <div className="flex flex-wrap items-center gap-1.5">
        {(issue.labels || []).map((label) => {
          const lowerLabel = label.toLowerCase();
          let pillStyle = "bg-slate-800 text-slate-400 border-slate-700";

          if (lowerLabel === "factory:ready") {
            pillStyle = "bg-emerald-950/80 text-emerald-300 border-emerald-800";
          } else if (lowerLabel === "factory:claimed") {
            pillStyle = "bg-amber-950/80 text-amber-300 border-amber-800";
          } else if (lowerLabel === "factory:resolved") {
            pillStyle = "bg-purple-950/80 text-purple-300 border-purple-800";
          } else if (lowerLabel === "factory:ready-for-human") {
            pillStyle = "bg-red-950/80 text-red-300 border-red-800";
          }

          return (
            <span
              key={label}
              data-testid={`status-pill-${label}`}
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${pillStyle}`}
            >
              {label}
            </span>
          );
        })}
      </div>

      {/* Blocker alert if blocked */}
      {isBlocked && (
        <div
          data-testid={`blocked-alert-${issue.number}`}
          className="flex items-center space-x-1.5 p-2 rounded bg-amber-950/40 border border-amber-800/60 text-[11px] text-amber-300 font-mono"
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>Blocked by open issue(s): #{openBlockers.join(", #")}</span>
        </div>
      )}

      {/* Body preview (expandable) */}
      {issue.body && (
        <div className="text-[11px] text-slate-400">
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="flex items-center space-x-1 text-slate-500 hover:text-slate-300 text-[10px] font-mono mb-1"
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <span>{isExpanded ? "Hide Details" : "Show Details"}</span>
          </button>
          {isExpanded && (
            <div
              data-testid={`issue-body-${issue.number}`}
              className="p-2.5 rounded bg-slate-950/70 border border-slate-800/80 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-slate-300 max-h-48 overflow-y-auto"
            >
              {issue.body}
            </div>
          )}
        </div>
      )}

      {/* Action Buttons Row */}
      <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800/70">
        {/* Grill & Align button (always enabled) */}
        <button
          data-testid={`grill-align-btn-${issue.number}`}
          type="button"
          onClick={() => onGrillAndAlign(issue)}
          className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors border border-slate-700"
          title="Interview requirements with Grilling Assistant before changing code"
        >
          <MessageSquareQuote className="w-3.5 h-3.5 text-indigo-400" />
          <span>Grill & Align</span>
        </button>

        {/* Instant Dispatch button (disabled if blocked or claimed) */}
        <button
          data-testid={`instant-dispatch-btn-${issue.number}`}
          type="button"
          onClick={() => onInstantDispatch(issue)}
          disabled={isInstantDisabled}
          title={disableInstantReason || "Bypass Grilling Assistant and dispatch assembly line directly"}
          className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            isInstantDisabled
              ? "bg-slate-800/50 text-slate-500 border border-slate-800 cursor-not-allowed"
              : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs"
          }`}
        >
          {isInstantDisabled ? (
            <Lock className="w-3 h-3 text-slate-500" />
          ) : (
            <Zap className="w-3 h-3 fill-current" />
          )}
          <span>Instant Dispatch</span>
        </button>
      </div>
    </div>
  );
};
