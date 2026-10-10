import React from "react";
import { Check, Loader2 } from "lucide-react";
import { JobStage } from "../types";

interface StageStepperProps {
  currentStage: JobStage | string;
}

const STAGES: { id: JobStage; label: string }[] = [
  { id: "PREFLIGHT", label: "Preflight" },
  { id: "PLANNER", label: "Planner" },
  { id: "CODER", label: "Coder" },
  { id: "VERIFIER", label: "Verifier" },
  { id: "REVIEWER", label: "Reviewer" },
  { id: "COMPLETED", label: "Completed" },
];

export const StageStepper: React.FC<StageStepperProps> = ({ currentStage }) => {
  const normalizedStage = (currentStage || "").toUpperCase();

  const getStageIndex = (stage: string): number => {
    switch (stage) {
      case "PREFLIGHT":
        return 0;
      case "PLANNER":
        return 1;
      case "CODER":
        return 2;
      case "VERIFIER":
        return 3;
      case "REVIEWER":
        return 4;
      case "COMPLETED":
      case "SERVING":
        return 5;
      default:
        return -1;
    }
  };

  const currentIndex = getStageIndex(normalizedStage);

  return (
    <div id="stage-stepper" className="w-full flex items-center justify-between py-2.5 px-3 bg-slate-900/60 rounded-lg border border-slate-800">
      {STAGES.map((s, idx) => {
        const isCompleted = currentIndex > idx || (currentIndex === 5 && idx === 5);
        const isActive = currentIndex === idx && currentIndex !== 5;

        return (
          <React.Fragment key={s.id}>
            <div className="stage-step flex items-center space-x-1.5 shrink-0">
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-200 ${
                  isCompleted
                    ? "bg-emerald-500 text-slate-950 font-black"
                    : isActive
                    ? "bg-indigo-600 text-white animate-pulse ring-2 ring-indigo-400/40"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {isCompleted ? (
                  <Check className="w-3 h-3 stroke-[3]" />
                ) : isActive ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>
              <span
                className={`text-xs font-medium ${
                  isActive
                    ? "text-indigo-300 font-semibold"
                    : isCompleted
                    ? "text-slate-200"
                    : "text-slate-500"
                }`}
              >
                {s.label}
              </span>
            </div>

            {idx < STAGES.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-2 rounded transition-colors duration-200 ${
                  currentIndex > idx ? "bg-emerald-500/70" : "bg-slate-800"
                }`}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
