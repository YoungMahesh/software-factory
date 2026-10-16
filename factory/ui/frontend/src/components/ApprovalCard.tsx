import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, FileCode2, Play, Sparkles, RotateCcw } from "lucide-react";
import { GrillTurnResult } from "../types";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";

export interface ApprovalCardProps {
  turn: GrillTurnResult;
  onApprove: (turn: GrillTurnResult) => void;
  isApproving?: boolean;
  isApproved?: boolean;
  isReverted?: boolean;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  turn,
  onApprove,
  isApproving = false,
  isApproved = false,
  isReverted = false,
}) => {
  const [isAdrExpanded, setIsAdrExpanded] = useState<boolean>(false);

  return (
    <div
      id="studio-approval-card"
      data-testid="approval-card"
      className={`p-4 rounded-xl border ${
        isReverted
          ? "border-white/10 bg-primary/80 opacity-75 text-slate-300"
          : "border-white/20 bg-primary text-white"
      } shadow-md space-y-3`}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className={`flex items-center space-x-2 ${isReverted ? "text-muted" : "text-emerald-400"}`}>
          {isReverted ? (
            <RotateCcw className="w-4 h-4 shrink-0 text-muted" />
          ) : (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          )}
          <span className="font-semibold text-xs tracking-wide">
            {isReverted ? "Plan Reverted" : isApproved ? "Plan Approved & Dispatched" : "Plan Ready for Approval"}
          </span>
        </div>
        <Badge
          data-testid="approval-badge"
          variant={isReverted ? "neutral" : "success"}
          className={`text-[11px] font-mono tracking-wider uppercase px-2.5 py-0.5 ${
            isReverted ? "bg-white/10 text-slate-400 border-white/10" : ""
          }`}
        >
          {isReverted ? "Reverted" : isApproved ? "Approved" : "Ready for Approval"}
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
          className="p-3 rounded-lg bg-cohere-black/70 border border-white/10 text-[11px] text-slate-300 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto"
        >
          {turn.plan}
        </div>
      )}

      {/* Proposed Architectural Decision Record (ADR) Preview */}
      {turn.draft_adr && turn.draft_adr.filename && (
        <div
          data-testid="draft-adr-preview"
          className="rounded-lg border border-white/10 bg-cohere-black/50 overflow-hidden"
        >
          <button
            type="button"
            data-testid="toggle-adr-content"
            onClick={() => setIsAdrExpanded((prev) => !prev)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-white/5 transition-colors text-left"
          >
            <div className="flex items-center space-x-2 truncate mr-2">
              <FileCode2 className="w-3.5 h-3.5 text-coral shrink-0" />
              <span className="font-mono text-coral text-[11px] truncate">
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
              className="p-3 bg-cohere-black border-t border-white/10 font-mono text-[11px] text-slate-300 whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed"
            >
              {turn.draft_adr.content}
            </div>
          )}
        </div>
      )}

      {/* Action Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-white/10">
        <span className="text-[10px] text-muted flex items-center space-x-1">
          <Sparkles className="w-3 h-3 text-coral" />
          <span>
            or type <code className="text-slate-200 font-mono font-medium">/proceed</code> in chat
          </span>
        </span>

        <Button
          id="btn-approve-build"
          data-testid="approve-plan-build-btn"
          type="button"
          variant={isReverted ? "ghost" : isApproved ? "success" : "inverted"}
          size="md"
          onClick={() => onApprove(turn)}
          isLoading={isApproving}
          disabled={isApproving || isApproved || isReverted}
          icon={
            isReverted ? (
              <RotateCcw className="w-3 h-3 text-muted" />
            ) : isApproved ? (
              <CheckCircle2 className="w-3 h-3 text-deep-green" />
            ) : (
              <Play className="w-3 h-3 fill-current" />
            )
          }
          className={
            isReverted
              ? "bg-white/10 border border-white/10 text-muted cursor-not-allowed"
              : isApproved
              ? "cursor-default"
              : "font-semibold"
          }
        >
          {isReverted ? "Plan Reverted" : isApproved ? "Plan Approved" : "Approve Plan & Build"}
        </Button>
      </div>
    </div>
  );
};
