"use client";

import type { LaunchStatusResponse } from "@dashboard/types";
import { Check, Circle, Dot, X } from "lucide-react";

export function LaunchProgressCard({
  launch,
  onDismiss,
  onRetry,
}: {
  launch: LaunchStatusResponse;
  onDismiss: () => void;
  onRetry: (appId: string) => void;
}) {
  const { request, app } = launch;
  const steps = request.steps ?? [];
  const logs = request.logs ?? [];

  return (
    <section className="bg-surface-soft border border-primary/40 rounded-2xl p-4 sm:p-6 shadow-sm space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-primary/15 text-primary-active">
              {request.status}
            </span>
            <h3 className="text-base font-semibold text-ink break-words">
              {app?.title || "Launching Factory App"}
            </h3>
          </div>
          {(app?.prompt || app?.repo) && (
            <p className="text-xs text-muted mt-1 line-clamp-2 break-words">
              {app.prompt ||
                `Opening ${app.repo}${app.branch ? ` @ ${app.branch}` : ""}`}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss active launch"
          className="text-muted hover:text-ink text-xs p-1.5 rounded bg-surface-card border border-hairline flex-shrink-0"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-2.5 text-xs">
        {steps.map((step) => {
          const style =
            step.status === "done"
              ? "bg-success/10 border-success/40 text-ink"
              : step.status === "active"
                ? "bg-primary/10 border-primary/40 text-primary-active"
                : step.status === "error"
                  ? "bg-error/10 border-error/40 text-error"
                  : "bg-canvas border-hairline text-muted";
          return (
            <div key={step.key} className={`p-2.5 sm:p-3 rounded-xl border ${style}`}>
              <div className="font-medium flex items-center gap-1.5">
                {step.status === "done" ? (
                  <Check className="w-3.5 h-3.5 text-success flex-shrink-0" />
                ) : step.status === "error" ? (
                  <X className="w-3.5 h-3.5 text-error flex-shrink-0" />
                ) : step.status === "active" ? (
                  <Dot className="w-4 h-4 text-primary animate-pulse flex-shrink-0" />
                ) : (
                  <Circle className="w-3 h-3 text-muted-soft flex-shrink-0" />
                )}
                <span className="truncate">{step.label}</span>
              </div>
            </div>
          );
        })}
      </div>

      {request.status === "failed" && (
        <div className="p-3 rounded-xl bg-error/10 border border-error/30 text-xs text-error flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <span className="break-words">{request.error || "Launch failed"}</span>
          {app?.app_id && (
            <button
              type="button"
              onClick={() => onRetry(app.app_id)}
              className="w-full sm:w-auto px-3 py-2 sm:py-1.5 rounded-lg bg-error hover:bg-error/90 text-on-primary font-medium flex-shrink-0 text-center"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {request.status === "ready" && request.handoff_url && (
        <div className="p-3 rounded-xl bg-success/10 border border-success/40 text-xs text-ink flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <span>Workspace ready — redirecting into T3 Code chat...</span>
          <a
            href={request.handoff_url}
            className="w-full sm:w-auto px-3 py-2 sm:py-1.5 rounded-lg bg-success hover:bg-success/90 text-on-primary font-semibold flex-shrink-0 text-center"
          >
            Open in T3
          </a>
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-surface-dark text-on-dark border border-surface-dark-elevated rounded-xl p-3 font-mono text-[11px] max-h-32 overflow-y-auto space-y-0.5 break-words">
          {logs.map((line, idx) => (
            <div key={idx}>{line}</div>
          ))}
        </div>
      )}
    </section>
  );
}
