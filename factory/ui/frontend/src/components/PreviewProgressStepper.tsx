import React from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";
import { PreviewStage, PreviewStatus } from "../types";

export interface PreviewProgressStepperProps {
  currentStage?: PreviewStage | string;
  status?: PreviewStatus;
  errorMessage?: string | null;
}

interface StepConfig {
  id: "provisioning" | "installing_deps" | "starting_dev";
  stage: PreviewStage;
  label: string;
}

const PREVIEW_STEPS: StepConfig[] = [
  { id: "provisioning", stage: "PROVISIONING", label: "Provisioning sandbox" },
  { id: "installing_deps", stage: "INSTALLING_DEPS", label: "Installing dependencies" },
  { id: "starting_dev", stage: "STARTING_DEV", label: "Starting dev server" },
];

const STAGE_ORDER: Record<string, number> = {
  PROVISIONING: 0,
  INSTALLING_DEPS: 1,
  STARTING_DEV: 2,
  SERVING: 3,
};

export const PreviewProgressStepper: React.FC<PreviewProgressStepperProps> = ({
  currentStage = "PROVISIONING",
  status = "PROVISIONING",
  errorMessage = null,
}) => {
  const activeIndex = STAGE_ORDER[(currentStage || "PROVISIONING").toUpperCase()] ?? 0;
  const isFailed = status === "FAILED";
  const isServing = currentStage === "SERVING" || status === "SERVING";

  return (
    <div
      id="preview-progress-stepper"
      data-testid="preview-progress-stepper"
      className="w-full max-w-xl mx-auto flex flex-col items-center space-y-4"
    >
      <div className="w-full flex items-center justify-between py-3 px-4 bg-primary text-slate-200 rounded-xl border border-white/10 shadow-sm">
        {PREVIEW_STEPS.map((step, idx) => {
          let state: "completed" | "active" | "failed" | "pending";
          if (isServing) {
            state = "completed";
          } else if (isFailed && idx === Math.min(activeIndex, 2)) {
            state = "failed";
          } else if (idx < activeIndex) {
            state = "completed";
          } else if (idx === activeIndex) {
            state = "active";
          } else {
            state = "pending";
          }

          return (
            <React.Fragment key={step.id}>
              <div
                data-testid={`preview-step-${step.id}`}
                data-state={state}
                className="preview-step flex items-center space-x-2 shrink-0"
              >
                <div
                  className={`w-6 h-6 rounded-pill flex items-center justify-center text-[11px] font-bold transition-all duration-200 ${
                    state === "completed"
                      ? "bg-pale-green text-deep-green shadow-xs"
                      : state === "failed"
                      ? "bg-coral text-white shadow-xs"
                      : state === "active"
                      ? "bg-white text-primary ring-2 ring-white/40"
                      : "bg-white/10 text-slate-400 border border-white/10"
                  }`}
                >
                  {state === "completed" ? (
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  ) : state === "failed" ? (
                    <AlertCircle className="w-3.5 h-3.5" />
                  ) : state === "active" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>
                <span
                  className={`text-xs ${
                    state === "active"
                      ? "text-white font-semibold"
                      : state === "failed"
                      ? "text-coral font-semibold"
                      : state === "completed"
                      ? "text-pale-green font-medium"
                      : "text-slate-400"
                  }`}
                >
                  {step.label}
                </span>
              </div>

              {idx < PREVIEW_STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-3 rounded transition-colors duration-200 ${
                    isServing || idx < activeIndex
                      ? "bg-pale-green/70"
                      : isFailed && idx === activeIndex
                      ? "bg-coral/50"
                      : "bg-white/10"
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {isFailed && errorMessage && (
        <div
          data-testid="preview-stepper-error-banner"
          className="w-full flex items-start space-x-2.5 p-3 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs"
        >
          <AlertCircle className="w-4 h-4 text-coral shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block text-coral mb-0.5 font-sans">Preview Boot Failed</span>
            <span className="text-[11px] font-mono break-all text-ink">{errorMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
};
