"use client";

import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

export type ToastKind = "info" | "error" | "success";

export interface ToastMessage {
  id: number;
  message: string;
  type: ToastKind;
}

export function ToastViewport({
  toast,
  onDismiss,
}: {
  toast: ToastMessage | null;
  onDismiss: () => void;
}) {
  if (!toast) return null;

  const isError = toast.type === "error";
  const isSuccess = toast.type === "success";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-4 left-4 right-4 sm:left-auto sm:bottom-6 sm:right-6 z-50 rounded-xl border px-4 py-3 shadow-lg flex items-center gap-3 text-sm sm:max-w-md ${
        isError
          ? "bg-surface-dark text-on-dark border-error"
          : isSuccess
            ? "bg-surface-dark text-on-dark border-success"
            : "bg-surface-dark text-on-dark border-surface-dark-elevated"
      }`}
    >
      {isError ? (
        <AlertTriangle className="w-4 h-4 text-error flex-shrink-0" />
      ) : isSuccess ? (
        <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
      ) : (
        <Info className="w-4 h-4 text-accent-teal flex-shrink-0" />
      )}
      <span className="flex-1 break-words">{toast.message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="text-on-dark-soft hover:text-on-dark p-1 rounded"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
