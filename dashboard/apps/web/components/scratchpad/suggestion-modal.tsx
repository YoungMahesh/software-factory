"use client";

import { useMemo } from "react";
import type { ScratchpadNoteSummaryView } from "@dashboard/types";
import { Loader2, X } from "lucide-react";
import { previewScratchpadTargetPath } from "@/lib/format";

export interface ScratchpadSuggestionModalProps {
  open: boolean;
  title: string;
  content: string;
  model: string;
  error: string;
  saving: boolean;
  existingIdeas: ScratchpadNoteSummaryView[];
  configRepo: string;
  onChangeTitle: (value: string) => void;
  onChangeContent: (value: string) => void;
  onReject: () => void;
  onAccept: () => void;
}

export function ScratchpadSuggestionModal({
  open,
  title,
  content,
  model,
  error,
  saving,
  existingIdeas,
  configRepo,
  onChangeTitle,
  onChangeContent,
  onReject,
  onAccept,
}: ScratchpadSuggestionModalProps) {
  const targetPathPreview = useMemo(
    () => previewScratchpadTargetPath(title, existingIdeas, configRepo),
    [title, existingIdeas, configRepo],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Review Suggested Note"
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-2 sm:p-4"
      onClick={() => {
        if (!saving) onReject();
      }}
    >
      <div
        id="scratchpad-suggestion-modal"
        className="bg-canvas border border-hairline rounded-2xl shadow-2xl w-full max-w-2xl p-4 sm:p-6 flex flex-col max-h-[92dvh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-hairline pb-3 flex-shrink-0">
          <div className="min-w-0">
            <h3 className="text-base sm:text-lg font-bold text-ink">
              Review Suggested Note
            </h3>
            <p className="text-xs text-muted">
              Generated with free model{" "}
              <span className="font-mono text-primary-active break-all">
                {model || "opencode"}
              </span>
              . Edit before committing or reject to keep your draft.
            </p>
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={onReject}
            aria-label="Close modal"
            className="text-muted hover:text-ink px-2 py-1 flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3 flex-1 min-h-0 overflow-y-auto py-4">
          <div>
            <label
              htmlFor="scratchpad-modal-title"
              className="block text-xs font-medium text-body mb-1"
            >
              Note Title
            </label>
            <input
              id="scratchpad-modal-title"
              type="text"
              value={title}
              onChange={(e) => onChangeTitle(e.target.value)}
              className="w-full bg-surface-soft border border-hairline focus:border-primary rounded-lg px-3.5 py-2 text-base sm:text-sm text-ink focus:outline-none"
            />
            <div className="mt-1.5 text-xs text-muted break-words">
              Target file:{" "}
              <span
                id="scratchpad-target-path-preview"
                className="font-mono text-primary-active break-all"
              >
                {targetPathPreview}
              </span>
            </div>
          </div>

          <div>
            <label
              htmlFor="scratchpad-modal-content"
              className="block text-xs font-medium text-body mb-1"
            >
              Markdown Body (committed below <code># Title</code>)
            </label>
            <textarea
              id="scratchpad-modal-content"
              rows={8}
              value={content}
              onChange={(e) => onChangeContent(e.target.value)}
              className="w-full bg-surface-soft border border-hairline focus:border-primary rounded-lg px-3.5 py-2.5 text-base sm:text-sm font-mono text-ink focus:outline-none resize-y"
            />
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-error/10 border border-error/30 text-xs text-error break-words">
            {error}
          </div>
        )}

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between gap-2.5 pt-3 border-t border-hairline flex-shrink-0">
          <button
            id="scratchpad-reject-btn"
            type="button"
            disabled={saving}
            onClick={onReject}
            className="w-full sm:w-auto px-4 py-2.5 sm:py-2 rounded-lg bg-surface-soft hover:bg-surface-card text-ink border border-hairline text-sm font-medium disabled:opacity-50"
          >
            Reject
          </button>
          <button
            id="scratchpad-accept-btn"
            type="button"
            disabled={saving || !title.trim() || !content.trim()}
            onClick={onAccept}
            className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-on-primary text-sm font-semibold shadow-sm disabled:opacity-50"
          >
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            <span>{saving ? "Committing..." : "Accept & Commit"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
