import React, { useState, useMemo, useEffect } from "react";
import { RotateCcw, AlertTriangle, Send } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { GrillTurnResult } from "../../types";

export interface GrillRoundCardProps {
  grillTurn: GrillTurnResult;
  onSubmitAnswers?: (formattedAnswers: string) => void;
  isExecutingTurn?: boolean;
  isAnswered?: boolean;
}

export const GrillRoundCard: React.FC<GrillRoundCardProps> = ({
  grillTurn,
  onSubmitAnswers,
  isExecutingTurn = false,
  isAnswered = false,
}) => {
  // Compute initial selections matching recommended options
  const defaultSelections = useMemo(() => {
    const selections: Record<string, string> = {};
    if (!grillTurn.questions) return selections;
    for (const q of grillTurn.questions) {
      if (q.options && q.options.length > 0) {
        const cleanRec = (q.recommended || "").toLowerCase().trim();
        const matched = q.options.find((opt) => {
          const cleanOpt = opt.toLowerCase().trim();
          return (
            cleanOpt.includes("(recommended)") ||
            (cleanRec && cleanOpt.includes(cleanRec)) ||
            (cleanRec && cleanRec.includes(cleanOpt.replace(/^[a-z0-9][.)]\s*/i, "")))
          );
        });
        selections[q.id] = matched || q.options[0];
      }
    }
    return selections;
  }, [grillTurn.questions]);

  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>(defaultSelections);
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});

  useEffect(() => {
    setSelectedOptions(defaultSelections);
  }, [defaultSelections]);

  const isDisabled = isAnswered || isExecutingTurn;

  const handleSelectOption = (questionId: string, optionValue: string) => {
    if (isDisabled) return;
    setSelectedOptions((prev) => ({ ...prev, [questionId]: optionValue }));
  };

  const handleCustomInputChange = (questionId: string, value: string) => {
    if (isDisabled) return;
    setCustomInputs((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleSubmit = () => {
    if (isDisabled || !onSubmitAnswers || !grillTurn.questions) return;
    const formattedAnswers = grillTurn.questions
      .map((q) => {
        const selected = selectedOptions[q.id];
        if (selected === "__custom__") {
          const customVal = (customInputs[q.id] || "").trim();
          return `${q.id}: Other - ${customVal || "Custom preference"}`;
        }
        return `${q.id}: ${selected || q.recommended}`;
      })
      .join("\n");
    onSubmitAnswers(formattedAnswers);
  };

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
        <div data-testid="grilling-questions-list" className="space-y-3 pt-1">
          {grillTurn.questions.map((q) => {
            const hasOptions = q.options && q.options.length > 0;
            const currentSelected = selectedOptions[q.id];
            const isCustomSelected = currentSelected === "__custom__";

            return (
              <div
                key={q.id}
                data-testid={`grill-question-${q.id}`}
                className="p-3.5 rounded-lg bg-white border border-hairline space-y-2.5 shadow-2xs"
              >
                <div className="flex items-center space-x-1.5 text-xs">
                  <span className="text-coral font-bold font-mono">❓ {q.id}</span>
                  <span className="text-muted">—</span>
                  <span className="font-display text-sm font-semibold text-ink">{q.title}</span>
                </div>
                <p className="text-body-muted text-xs leading-relaxed">{q.question}</p>

                {hasOptions && (
                  <div
                    data-testid={`grill-options-${q.id}`}
                    className="space-y-1.5 pt-1"
                  >
                    {q.options!.map((opt, i) => {
                      const isChecked = currentSelected === opt;
                      const radioId = `radio-${q.id}-${i}`;
                      return (
                        <label
                          key={i}
                          htmlFor={radioId}
                          className={`flex items-start space-x-2 text-xs p-1.5 rounded-md transition-colors ${
                            isChecked
                              ? "bg-soft-stone/60 font-medium text-ink"
                              : "text-body-muted hover:bg-soft-stone/30"
                          } ${isDisabled ? "cursor-not-allowed opacity-75" : "cursor-pointer"}`}
                        >
                          <input
                            id={radioId}
                            type="radio"
                            name={`grill-group-${q.id}`}
                            value={opt}
                            checked={isChecked}
                            disabled={isDisabled}
                            onChange={() => handleSelectOption(q.id, opt)}
                            data-testid={`grill-option-radio-${q.id}-${i}`}
                            className="mt-0.5 text-coral focus:ring-coral accent-coral h-3.5 w-3.5 border-hairline shrink-0"
                          />
                          <span className="leading-tight">{opt}</span>
                        </label>
                      );
                    })}

                    {/* Dedicated 'Other / Custom' Radio Option */}
                    <div className="space-y-1.5 pt-0.5">
                      <label
                        htmlFor={`radio-${q.id}-custom`}
                        className={`flex items-start space-x-2 text-xs p-1.5 rounded-md transition-colors ${
                          isCustomSelected
                            ? "bg-soft-stone/60 font-medium text-ink"
                            : "text-body-muted hover:bg-soft-stone/30"
                        } ${isDisabled ? "cursor-not-allowed opacity-75" : "cursor-pointer"}`}
                      >
                        <input
                          id={`radio-${q.id}-custom`}
                          type="radio"
                          name={`grill-group-${q.id}`}
                          value="__custom__"
                          checked={isCustomSelected}
                          disabled={isDisabled}
                          onChange={() => handleSelectOption(q.id, "__custom__")}
                          data-testid={`grill-option-radio-${q.id}-custom`}
                          className="mt-0.5 text-coral focus:ring-coral accent-coral h-3.5 w-3.5 border-hairline shrink-0"
                        />
                        <span className="leading-tight">Other (specify custom preference)</span>
                      </label>

                      {isCustomSelected && (
                        <div className="pl-6 pt-0.5" data-testid={`custom-input-wrapper-${q.id}`}>
                          <Input
                            data-testid={`grill-custom-input-${q.id}`}
                            placeholder="Enter custom preference for this question..."
                            value={customInputs[q.id] || ""}
                            disabled={isDisabled}
                            onChange={(e) => handleCustomInputChange(q.id, e.target.value)}
                            className="text-xs py-1.5"
                            autoFocus={!isDisabled}
                          />
                        </div>
                      )}
                    </div>
                  </div>
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
            );
          })}
        </div>
      )}

      {onSubmitAnswers && grillTurn.questions && grillTurn.questions.length > 0 && !isAnswered && (
        <div className="flex items-center justify-end pt-2 border-t border-hairline">
          <Button
            data-testid="grilling-submit-answers-btn"
            type="button"
            variant="primary"
            size="sm"
            disabled={isDisabled}
            isLoading={isExecutingTurn}
            onClick={handleSubmit}
            icon={<Send className="w-3.5 h-3.5" />}
            className="bg-coral hover:bg-coral-hover text-white text-xs px-3.5 py-1.5 shadow-2xs"
          >
            Submit Answers
          </Button>
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
