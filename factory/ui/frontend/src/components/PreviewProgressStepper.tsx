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

export const PreviewProgressStepper: React.FC<PreviewProgressStepperProps> = ({
  currentStage = "PROVISIONING",
  status = "PROVISIONING",
  errorMessage = null,
}) => {
  const getStageIndex = (stage: string): number => {
    switch (stage.toUpperCase()) {
      case "PROVISIONING":
        return 0;
      case "INSTALLING_DEPS":
        return 1;
      case "STARTING_DEV":
        return 2;
      case "SERVING":
        return 3;
      default:
        return 0;
    }
  };

  const activeIndex = getStageIndex(currentStage || "PROVISIONING");
  const isFailed = status === "FAILED";
  const isServing = currentStage === "SERVING" || status === "SERVING";

  return (
    <div
      id="preview-progress-stepper"
      data-testid="preview-progress-stepper"
      className="w-full max-w-xl mx-auto flex flex-col items-center space-y-4"
    >
      <div className="w-full flex items-center justify-between py-3 px-4 bg-slate-900/80 rounded-xl border border-slate-800 shadow-sm">
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
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all duration-200 ${
                    state === "completed"
                      ? "bg-emerald-500 text-slate-950 shadow-sm shadow-emerald-500/20"
                      : state === "failed"
                      ? "bg-rose-500 text-white shadow-sm shadow-rose-500/20 ring-2 ring-rose-400/40"
                      : state === "active"
                      ? "bg-indigo-600 text-white animate-pulse ring-2 ring-indigo-400/40"
                      : "bg-slate-800 text-slate-500 border border-slate-700/60"
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
                      ? "text-indigo-300 font-semibold"
                      : state === "failed"
                      ? "text-rose-300 font-semibold"
                      : state === "completed"
                      ? "text-slate-200 font-medium"
                      : "text-slate-500"
                  }`}
                >
                  {step.label}
                </span>
              </div>

              {idx < PREVIEW_STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-3 rounded transition-colors duration-200 ${
                    isServing || idx < activeIndex
                      ? "bg-emerald-500/70"
                      : isFailed && idx === activeIndex
                      ? "bg-rose-500/50"
                      : "bg-slate-800"
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
          className="w-full flex items-start space-x-2.5 p-3 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-200 text-xs"
        >
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block text-rose-300 mb-0.5">Preview Boot Failed</span>
            <span className="text-[11px] font-mono break-all">{errorMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
};
