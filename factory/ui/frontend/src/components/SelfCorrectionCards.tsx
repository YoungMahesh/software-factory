import React from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";

interface AttemptDividerProps {
  id?: string;
  attempt: number;
  maxAttempts?: number;
  maxRetries?: number;
  reason?: string;
  summary?: string;
}

export const AttemptDividerCard: React.FC<AttemptDividerProps> = ({
  id,
  attempt,
  maxAttempts = 3,
  reason,
  summary,
}) => {
  return (
    <div
      id={id}
      className="attempt-divider-card my-4 relative flex flex-col items-center justify-center"
    >
      <div className="absolute inset-0 flex items-center" aria-hidden="true">
        <div className="w-full border-t border-amber-600/40" />
      </div>
      <div className="relative z-10 flex flex-col items-center bg-slate-950 px-4 py-1.5 rounded-full border border-amber-500/50 shadow-md">
        <div className="flex items-center space-x-2 text-amber-400 font-semibold text-xs">
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          <span>
            Self-Correction Loop: Attempt {attempt} of {maxAttempts}
          </span>
        </div>
      </div>
      {(reason || summary) && (
        <div className="mt-2 text-center text-[11px] text-amber-300/80 font-mono max-w-md">
          {reason && <span className="font-semibold capitalize">[{reason}] </span>}
          {summary && <span>{summary}</span>}
        </div>
      )}
    </div>
  );
};

interface ReviewerRejectionCardProps {
  id?: string;
  verdict?: string;
  summary: string;
  remediation?: string;
}

export const ReviewerRejectionCard: React.FC<ReviewerRejectionCardProps> = ({
  id,
  verdict = "rejected",
  summary,
  remediation,
}) => {
  return (
    <div
      id={id}
      className="reviewer-rejection-card my-3 p-3 rounded-lg border border-rose-800/80 bg-rose-950/30 text-xs shadow-md"
    >
      <div className="flex items-center space-x-2 text-rose-400 font-semibold mb-2">
        <ShieldAlert className="w-4 h-4 shrink-0" />
        <span className="uppercase tracking-wider text-[11px]">
          Reviewer Rejection ({verdict})
        </span>
      </div>

      <div className="rejection-summary text-rose-200 mb-2 font-mono text-[11px] bg-rose-950/40 p-2 rounded border border-rose-900/40">
        {summary}
      </div>

      {remediation && (
        <div className="remediation-instructions text-[11px] text-slate-300">
          <span className="font-semibold text-rose-300">Remediation: </span>
          <span className="font-mono text-slate-300">{remediation}</span>
        </div>
      )}
    </div>
  );
};
