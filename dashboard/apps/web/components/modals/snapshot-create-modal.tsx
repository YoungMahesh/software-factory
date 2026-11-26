"use client";

import { useState } from "react";
import { Camera, Loader2, X } from "lucide-react";
import { extractApiError } from "@/lib/format";

export interface SnapshotTarget {
  id: string;
  name?: string | null;
  profile?: string | null;
}

export interface SnapshotCreateModalProps {
  target: SnapshotTarget | null;
  onClose: () => void;
  onToast: (message: string, type?: "info" | "error" | "success") => void;
  onCaptured: () => Promise<void>;
}

export function SnapshotCreateModal({
  target,
  onClose,
  onToast,
  onCaptured,
}: SnapshotCreateModalProps) {
  if (!target) return null;
  return (
    <SnapshotCreateModalContent
      key={target.id}
      target={target}
      onClose={onClose}
      onToast={onToast}
      onCaptured={onCaptured}
    />
  );
}

function SnapshotCreateModalContent({
  target,
  onClose,
  onToast,
  onCaptured,
}: SnapshotCreateModalProps & { target: SnapshotTarget }) {
  const [name, setName] = useState(`${target.name || target.id}-snapshot`);
  const [ttlDays, setTtlDays] = useState(30);
  const [timeout, setTimeoutSecs] = useState(180);
  const [terminate, setTerminate] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const res = await fetch(`/api/sandboxes/${encodeURIComponent(target.id)}/snapshot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          ttl_days: ttlDays,
          terminate,
          timeout,
          profile: target.profile || null,
        }),
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as { image_id: string };
      onToast(`Snapshot captured: ${data.image_id}`, "success");
      onClose();
      await onCaptured();
    } catch (err) {
      onToast(
        `Snapshot failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Capture Filesystem Snapshot"
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-2 sm:p-4"
      onClick={() => {
        if (!submitting) onClose();
      }}
    >
      <div
        className="bg-canvas border border-hairline rounded-2xl max-w-lg w-full p-4 sm:p-6 shadow-2xl flex flex-col max-h-[92dvh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-hairline pb-3 sm:pb-4 flex-shrink-0">
          <h3 className="text-base font-semibold text-ink flex items-center gap-2">
            <Camera className="w-5 h-5 text-primary" />
            Capture Filesystem Snapshot
          </h3>
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 -mr-1 text-muted hover:text-ink"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4 flex-1 min-h-0 overflow-y-auto py-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">Target Sandbox</label>
              <input
                type="text"
                value={target.id}
                disabled
                className="w-full bg-surface-card border border-hairline rounded-lg px-3 py-2 text-base sm:text-xs text-body font-mono cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Workspace Profile
              </label>
              <input
                type="text"
                value={target.profile || "default"}
                disabled
                className="w-full bg-surface-card border border-hairline rounded-lg px-3 py-2 text-base sm:text-xs text-primary font-mono cursor-not-allowed"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Snapshot Label / Description
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. dev-checkpoint-v1"
              className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Retention TTL (Days)
              </label>
              <input
                type="number"
                min={1}
                max={365}
                value={ttlDays}
                onChange={(e) => setTtlDays(Number.parseInt(e.target.value || "30", 10))}
                className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Timeout (Seconds)
              </label>
              <input
                type="number"
                min={10}
                max={600}
                value={timeout}
                onChange={(e) => setTimeoutSecs(Number.parseInt(e.target.value || "180", 10))}
                className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs text-body cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              checked={terminate}
              onChange={(e) => setTerminate(e.target.checked)}
              className="rounded border-hairline text-primary focus:ring-0"
            />
            <span>Terminate target sandbox immediately after snapshot</span>
          </label>
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-end gap-2 sm:gap-3 pt-3 sm:pt-4 border-t border-hairline flex-shrink-0">
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2.5 sm:py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm text-ink"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void handleSubmit()}
            className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-sm font-medium text-on-primary shadow-sm disabled:opacity-50"
          >
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Capture Snapshot
          </button>
        </div>
      </div>
    </div>
  );
}
