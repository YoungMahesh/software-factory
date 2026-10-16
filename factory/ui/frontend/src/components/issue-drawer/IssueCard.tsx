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
      className="p-3.5 rounded-xl bg-white border border-hairline hover:border-muted/40 transition-colors space-y-2.5 shadow-2xs"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start space-x-2">
          <span className="text-xs font-mono font-bold text-primary shrink-0 mt-0.5">
            #{issue.number}
          </span>
          <span className="text-xs font-semibold text-ink leading-snug">
            {issue.title}
          </span>
        </div>

        {issue.html_url && (
          <a
            href={issue.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted hover:text-ink p-0.5 transition-colors shrink-0"
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
          let pillStyle = "bg-soft-stone text-ink border-hairline";

          if (lowerLabel === "factory:ready") {
            pillStyle = "bg-pale-green text-deep-green border-deep-green/20";
          } else if (lowerLabel === "factory:claimed") {
            pillStyle = "bg-soft-stone text-ink border-hairline";
          } else if (lowerLabel === "factory:resolved") {
            pillStyle = "bg-deep-green text-pale-green border-deep-green";
          } else if (lowerLabel === "factory:ready-for-human") {
            pillStyle = "bg-coral/15 text-coral border-coral/30";
          }

          return (
            <span
              key={label}
              data-testid={`status-pill-${label}`}
              className={`px-2.5 py-0.5 rounded-pill text-[10px] font-mono font-medium border ${pillStyle}`}
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
          className="flex items-center space-x-1.5 p-2 rounded-lg bg-coral/10 border border-coral/30 text-[11px] text-coral font-mono"
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>Blocked by open issue(s): #{openBlockers.join(", #")}</span>
        </div>
      )}

      {/* Body preview (expandable) */}
      {issue.body && (
        <div className="text-[11px] text-muted">
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="flex items-center space-x-1 text-muted hover:text-ink text-[10px] font-mono mb-1 cursor-pointer"
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <span>{isExpanded ? "Hide Details" : "Show Details"}</span>
          </button>
          {isExpanded && (
            <div
              data-testid={`issue-body-${issue.number}`}
              className="p-2.5 rounded-lg bg-soft-stone border border-hairline whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink max-h-48 overflow-y-auto"
            >
              {issue.body}
            </div>
          )}
        </div>
      )}

      {/* Action Buttons Row */}
      <div className="flex items-center justify-end space-x-2 pt-2 border-t border-hairline">
        {/* Grill & Align button (always enabled) */}
        <button
          data-testid={`grill-align-btn-${issue.number}`}
          type="button"
          onClick={() => onGrillAndAlign(issue)}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-pill bg-soft-stone hover:bg-hairline text-ink text-xs font-medium transition-colors border border-hairline cursor-pointer"
          title="Interview requirements with Grilling Assistant before changing code"
        >
          <MessageSquareQuote className="w-3.5 h-3.5 text-primary" />
          <span>Grill & Align</span>
        </button>

        {/* Instant Dispatch button (disabled if blocked or claimed) */}
        <button
          data-testid={`instant-dispatch-btn-${issue.number}`}
          type="button"
          onClick={() => onInstantDispatch(issue)}
          disabled={isInstantDisabled}
          title={disableInstantReason || "Bypass Grilling Assistant and dispatch assembly line directly"}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-semibold transition-colors ${
            isInstantDisabled
              ? "bg-soft-stone/50 text-muted border border-hairline cursor-not-allowed"
              : "bg-primary hover:bg-cohere-black text-white shadow-xs cursor-pointer"
          }`}
        >
          {isInstantDisabled ? (
            <Lock className="w-3 h-3 text-muted" />
          ) : (
            <Zap className="w-3 h-3 fill-current" />
          )}
          <span>Instant Dispatch</span>
        </button>
      </div>
    </div>
  );
};
