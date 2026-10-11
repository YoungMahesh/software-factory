import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, FileCode2, Play, Sparkles } from "lucide-react";
import { GrillTurnResult } from "../types";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";

export interface ApprovalCardProps {
  turn: GrillTurnResult;
  onApprove: (turn: GrillTurnResult) => void;
  isApproving?: boolean;
  isApproved?: boolean;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  turn,
  onApprove,
  isApproving = false,
  isApproved = false,
}) => {
  const [isAdrExpanded, setIsAdrExpanded] = useState<boolean>(false);

  return (
    <div
      id="studio-approval-card"
      data-testid="approval-card"
      className="p-4 rounded-xl border border-emerald-800/70 bg-gradient-to-b from-emerald-950/40 to-slate-900/90 shadow-md space-y-3"
    >
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-emerald-400">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs tracking-wide">
            {isApproved ? "Plan Approved & Dispatched" : "Plan Ready for Approval"}
          </span>
        </div>
        <Badge
          data-testid="approval-badge"
          variant="success"
          className="text-[11px] font-mono tracking-wider uppercase px-2 py-0.5"
        >
          {isApproved ? "Approved" : "Ready for Approval"}
        </Badge>
      </div>

      {/* Plan Summary */}
      {turn.summary && (
        <div
          data-testid="plan-summary"
          className="text-xs text-slate-200 font-medium leading-relaxed"
        >
          {turn.summary}
        </div>
      )}

      {/* Plan Content */}
      {turn.plan && (
        <div
          data-testid="plan-details"
          className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-300 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto"
        >
          {turn.plan}
        </div>
      )}

      {/* Proposed Architectural Decision Record (ADR) Preview */}
      {turn.draft_adr && (
        <div
          data-testid="draft-adr-preview"
          className="rounded-lg border border-slate-800 bg-slate-950/50 overflow-hidden"
        >
          <button
            type="button"
            data-testid="toggle-adr-content"
            onClick={() => setIsAdrExpanded((prev) => !prev)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-slate-800/40 transition-colors text-left"
          >
            <div className="flex items-center space-x-2 truncate mr-2">
              <FileCode2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              <span className="font-mono text-indigo-300 text-[11px] truncate">
                {turn.draft_adr.filename}
              </span>
              <span className="text-slate-400 text-[11px] truncate">
                — {turn.draft_adr.title}
              </span>
            </div>
            <div className="flex items-center space-x-1 text-slate-400 text-[10px] shrink-0">
              <span>{isAdrExpanded ? "Collapse" : "Preview ADR"}</span>
              {isAdrExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </div>
          </button>

          {isAdrExpanded && (
            <div
              data-testid="adr-content"
              className="p-3 bg-slate-950 border-t border-slate-800 font-mono text-[11px] text-slate-300 whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed"
            >
              {turn.draft_adr.content}
            </div>
          )}
        </div>
      )}

      {/* Action Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-emerald-900/40">
        <span className="text-[10px] text-slate-400 flex items-center space-x-1">
          <Sparkles className="w-3 h-3 text-indigo-400" />
          <span>
            or type <code className="text-indigo-300 font-mono font-medium">/proceed</code> in chat
          </span>
        </span>

        <Button
          id="btn-approve-build"
          data-testid="approve-plan-build-btn"
          type="button"
          variant="primary"
          size="sm"
          onClick={() => onApprove(turn)}
          isLoading={isApproving}
          disabled={isApproving || isApproved}
          icon={isApproved ? <CheckCircle2 className="w-3 h-3 text-emerald-300" /> : <Play className="w-3 h-3 fill-current" />}
          className={
            isApproved
              ? "bg-emerald-950/80 border border-emerald-800 text-emerald-300 cursor-default"
              : "bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-sm"
          }
        >
          {isApproved ? "Plan Approved" : "Approve Plan & Build"}
        </Button>
      </div>
    </div>
  );
};
