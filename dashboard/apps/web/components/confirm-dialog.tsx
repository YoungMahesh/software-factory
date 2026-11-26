"use client";

import { AlertTriangle, X } from "lucide-react";

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

export function ConfirmDialog({
  options,
  onConfirm,
  onCancel,
}: {
  options: ConfirmOptions | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!options) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-2 sm:p-4"
      onClick={onCancel}
    >
      <div
        className="bg-canvas border border-hairline rounded-2xl max-w-md w-full p-4 sm:p-6 shadow-2xl space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            {options.destructive && (
              <span className="p-2 rounded-lg bg-error/10 text-error flex-shrink-0">
                <AlertTriangle className="w-4 h-4" />
              </span>
            )}
            <h3 id="confirm-dialog-title" className="text-base font-semibold text-ink">
              {options.title}
            </h3>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close confirmation"
            className="p-1 text-muted hover:text-ink rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-sm text-body break-words">{options.message}</p>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-end gap-2 pt-2 border-t border-hairline">
          <button
            type="button"
            onClick={onCancel}
            className="w-full sm:w-auto px-4 py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm font-medium text-ink"
          >
            {options.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`w-full sm:w-auto px-4 py-2 rounded-lg text-sm font-semibold text-on-primary ${
              options.destructive
                ? "bg-error hover:bg-error/90"
                : "bg-primary hover:bg-primary-active"
            }`}
          >
            {options.confirmLabel ?? "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
