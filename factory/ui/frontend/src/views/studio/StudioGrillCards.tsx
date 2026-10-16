import React from "react";
import { RotateCcw, AlertTriangle } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { GrillTurnResult } from "../../types";

export interface GrillRoundCardProps {
  grillTurn: GrillTurnResult;
}

export const GrillRoundCard: React.FC<GrillRoundCardProps> = ({ grillTurn }) => {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Badge variant="stage" data-testid="grilling-round-badge">
          Grill &amp; Align (Round {grillTurn.round})
        </Badge>
      </div>

      {grillTurn.sharpened_terms && grillTurn.sharpened_terms.length > 0 && (
        <div
          data-testid="sharpened-terms-banner"
          className="p-3 rounded-lg bg-soft-stone border border-hairline space-y-1.5 text-xs shadow-2xs"
        >
          <div className="font-semibold text-ink text-[11px] uppercase tracking-wider font-mono">
            Sharpened Domain Concepts
          </div>
          {grillTurn.sharpened_terms.map((t, idx) => (
            <div key={idx} className="text-[11px] text-ink leading-relaxed">
              • <span className="line-through text-muted">{t.fuzzy_term}</span> ➔{" "}
              <span className="font-semibold text-coral">{t.canonical_term}</span>:{" "}
              <span className="text-body-muted">{t.explanation}</span>
            </div>
          ))}
        </div>
      )}

      {grillTurn.summary && (
        <p
          data-testid="grilling-round-summary"
          className="text-ink text-xs font-medium leading-relaxed"
        >
          {grillTurn.summary}
        </p>
      )}

      {grillTurn.questions && grillTurn.questions.length > 0 && (
        <div data-testid="grilling-questions-list" className="space-y-2.5 pt-1">
          {grillTurn.questions.map((q) => (
            <div
              key={q.id}
              data-testid={`grill-question-${q.id}`}
              className="p-3.5 rounded-lg bg-white border border-hairline space-y-2 shadow-2xs"
            >
              <div className="flex items-center space-x-1.5 text-xs">
                <span className="text-coral font-bold font-mono">❓ {q.id}</span>
                <span className="text-muted">—</span>
                <span className="font-display text-sm font-semibold text-ink">{q.title}</span>
              </div>
              <p className="text-body-muted text-xs leading-relaxed">{q.question}</p>
              {q.options && q.options.length > 0 && (
                <ul className="list-disc list-inside space-y-0.5 text-[11px] text-muted pl-1">
                  {q.options.map((opt, i) => (
                    <li key={i}>{opt}</li>
                  ))}
                </ul>
              )}
              <div
                data-testid={`recommended-answer-${q.id}`}
                className="flex items-center space-x-1.5 text-[11px] text-deep-green bg-pale-green border border-deep-green/20 px-2.5 py-1.5 rounded-pill"
              >
                <span className="shrink-0 font-bold">➡️</span>
                <span className="font-medium shrink-0">Recommended:</span>
                <span className="text-deep-green">{q.recommended}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export interface GrillErrorCardProps {
  grillTurn: GrillTurnResult;
  isExecutingTurn: boolean;
  onRetry: () => void;
}

export const GrillErrorCard: React.FC<GrillErrorCardProps> = ({
  grillTurn,
  isExecutingTurn,
  onRetry,
}) => {
  return (
    <div
      data-testid="grilling-error-banner"
      className="p-3.5 rounded-xl border border-coral/30 bg-coral/5 text-xs space-y-2.5 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-coral font-semibold">
          <AlertTriangle className="w-4 h-4 shrink-0 text-coral" />
          <span>Inference Service Error</span>
        </div>
        <Badge variant="danger" className="font-mono text-[10px]">
          ERROR
        </Badge>
      </div>

      <p
        data-testid="grilling-error-reason"
        className="text-coral text-xs font-medium leading-relaxed"
      >
        {grillTurn.error_message ||
          grillTurn.summary ||
          "Remote inference request failed."}
      </p>

      {grillTurn.error_details && (
        <div
          data-testid="grilling-error-details"
          className="p-2.5 rounded-lg bg-white border border-hairline text-[11px] font-mono text-muted whitespace-pre-wrap max-h-36 overflow-y-auto"
        >
          {grillTurn.error_details}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-coral/20">
        <span className="text-[11px] text-muted">
          Verify network connectivity and OpenCode Credentials, then retry.
        </span>
        <Button
          data-testid="grilling-retry-btn"
          type="button"
          variant="pill-outline"
          size="sm"
          disabled={isExecutingTurn}
          onClick={onRetry}
          icon={<RotateCcw className="w-3.5 h-3.5" />}
          className="bg-white border-coral text-coral hover:bg-coral/10"
        >
          Retry
        </Button>
      </div>
    </div>
  );
};
