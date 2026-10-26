import React from "react";
import { ShieldCheck, AlertTriangle, Clock } from "lucide-react";
import { Badge } from "./ui/Badge";
import { VisualQaTelemetry } from "../types";

export interface VisualQABadgeProps {
  telemetry?: VisualQaTelemetry | null;
  isLoading?: boolean;
  className?: string;
}

export const VisualQABadge: React.FC<VisualQABadgeProps> = ({
  telemetry,
  isLoading = false,
  className = "",
}) => {
  if (isLoading) {
    return (
      <Badge
        data-testid="visual-qa-status-badge"
        variant="neutral"
        className={`bg-white/5 text-slate-400 border-white/10 ${className}`}
      >
        <Clock className="w-3 h-3 mr-1 animate-spin shrink-0 text-slate-400" />
        Visual QA Pending
      </Badge>
    );
  }

  const isPassed =
    telemetry?.passed === true ||
    telemetry?.status === "passed" ||
    telemetry?.status === "verified";

  const isFailed =
    telemetry?.passed === false &&
    (telemetry?.status === "failed" ||
      (telemetry?.errors && telemetry.errors.length > 0) ||
      telemetry?.cleanCanvas === false);

  if (isPassed) {
    return (
      <Badge
        data-testid="visual-qa-status-badge"
        variant="success"
        className={`bg-emerald-500/15 text-emerald-400 border-emerald-500/30 ${className}`}
      >
        <ShieldCheck className="w-3 h-3 mr-1 shrink-0 text-emerald-400" />
        Visual QA Verified
      </Badge>
    );
  }

  if (isFailed) {
    return (
      <Badge
        data-testid="visual-qa-status-badge"
        variant="danger"
        className={`bg-coral/15 text-coral border-coral/30 ${className}`}
      >
        <AlertTriangle className="w-3 h-3 mr-1 shrink-0 text-coral" />
        Visual QA Failed
      </Badge>
    );
  }

  return (
    <Badge
      data-testid="visual-qa-status-badge"
      variant="neutral"
      className={`bg-white/5 text-slate-400 border-white/10 ${className}`}
    >
      <Clock className="w-3 h-3 mr-1 shrink-0 text-slate-400" />
      Visual QA Pending
    </Badge>
  );
};
