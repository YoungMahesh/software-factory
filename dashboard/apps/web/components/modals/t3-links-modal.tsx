"use client";

import { useEffect, useRef, useState } from "react";
import {
  SandboxT3LinksResponseSchema,
  T3PairingLinkEntrySchema,
  type SandboxSummary,
  type T3PairingLinkEntry,
} from "@dashboard/types";
import { AlertCircle, Check, Copy, Link2, Loader2, Plus, X } from "lucide-react";
import { copyToClipboard, extractApiError } from "@/lib/format";
import {
  appendGeneratedT3Link,
  buildSandboxT3LinksPath,
  seedInitialT3Links,
} from "@/lib/t3-links";

export interface T3LinksModalProps {
  target: SandboxSummary | null;
  onClose: () => void;
  onToast: (message: string, type?: "info" | "error" | "success") => void;
  onLinkGenerated?: (sandboxId: string, url: string) => void;
}

export function T3LinksModal({
  target,
  onClose,
  onToast,
  onLinkGenerated,
}: T3LinksModalProps) {
  if (!target) return null;
  return (
    <T3LinksModalContent
      key={target.id}
      target={target}
      onClose={onClose}
      onToast={onToast}
      onLinkGenerated={onLinkGenerated}
    />
  );
}

function T3LinksModalContent({
  target,
  onClose,
  onToast,
  onLinkGenerated,
}: T3LinksModalProps & { target: SandboxSummary }) {
  const [links, setLinks] = useState<T3PairingLinkEntry[]>(() =>
    seedInitialT3Links(target.t3_pair_url),
  );
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [available, setAvailable] = useState(true);
  const [unavailableReason, setUnavailableReason] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function loadLinks() {
      try {
        const res = await fetch(buildSandboxT3LinksPath(target.id, target.profile), {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!res.ok) {
          const err = await extractApiError(res, "Failed loading pairing links");
          throw new Error(err.message);
        }
        const parsed = SandboxT3LinksResponseSchema.parse(await res.json());
        if (cancelled) return;
        setAvailable(parsed.available);
        setUnavailableReason(parsed.reason ?? null);
        setLinks(parsed.links);
        setLoadError(null);
      } catch (err) {
        if (cancelled || (err instanceof Error && err.name === "AbortError")) return;
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadLinks();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [target.id, target.profile]);

  async function handleCopy(entry: T3PairingLinkEntry, key: string) {
    const copied = await copyToClipboard(entry.url);
    if (!copied) {
      onToast("Could not copy pairing link to clipboard.", "error");
      return;
    }
    setCopiedKey(key);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => {
      setCopiedKey((cur) => (cur === key ? null : cur));
    }, 1500);
    onToast("Pairing link copied!");
  }

  async function handleGenerate() {
    if (generating || loading || !available) return;
    setGenerating(true);
    try {
      const res = await fetch(buildSandboxT3LinksPath(target.id, target.profile), {
        method: "POST",
      });
      if (!res.ok) {
        const err = await extractApiError(res, "Failed generating pairing link");
        throw new Error(err.message);
      }
      const created = T3PairingLinkEntrySchema.parse(await res.json());
      setLinks((prev) => appendGeneratedT3Link(prev, created));
      onLinkGenerated?.(target.id, created.url);
      onToast("New pairing link generated", "success");
      requestAnimationFrame(() => {
        if (listRef.current) {
          listRef.current.scrollTop = listRef.current.scrollHeight;
        }
      });
    } catch (err) {
      onToast(
        `Could not generate pairing link: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="T3Code Pairing Links"
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-2 sm:p-4"
      onClick={() => {
        if (!generating) onClose();
      }}
    >
      <div
        className="bg-canvas border border-hairline rounded-2xl max-w-lg w-full p-4 sm:p-6 shadow-2xl flex flex-col max-h-[90dvh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-hairline pb-3 sm:pb-4 flex-shrink-0">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-ink flex items-center gap-2">
              <Link2 className="w-4 h-4 text-primary flex-shrink-0" />
              <span>T3Code Pairing Links</span>
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted font-mono">
              <span className="truncate max-w-xs">{target.name || target.id}</span>
              {target.profile && (
                <span className="px-1.5 py-0.5 rounded bg-primary/10 text-primary-active border border-primary/25 text-[11px]">
                  {target.profile}
                </span>
              )}
              {loading && (
                <span className="inline-flex items-center gap-1 font-sans text-[11px] text-muted">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Syncing
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            disabled={generating}
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 -mr-1 text-muted hover:text-ink disabled:opacity-40"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto py-4 space-y-2.5">
          {loadError && (
            <div className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2.5 text-xs text-error">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{loadError}</span>
            </div>
          )}

          {loading && links.length === 0 ? (
            <div className="py-8 flex flex-col items-center justify-center gap-2 text-xs text-muted">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              <span>Loading pairing links...</span>
            </div>
          ) : !loading && !available ? (
            <div className="flex items-start gap-2 rounded-lg border border-hairline bg-surface-soft px-3 py-3 text-xs text-muted">
              <AlertCircle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
              <span>
                {unavailableReason ||
                  "T3 Code Server is not running or tunnel unavailable on this sandbox."}
              </span>
            </div>
          ) : links.length === 0 ? (
            <div className="rounded-lg border border-dashed border-hairline bg-surface-soft px-4 py-6 text-center text-xs text-muted">
              No pairing links recorded yet. Click Generate to create one.
            </div>
          ) : (
            <div className="space-y-2">
              {links.map((entry, idx) => {
                const key = entry.id || `${entry.url}-${idx}`;
                const isCopied = copiedKey === key;
                const isActive = entry.status === "active";

                return (
                  <div
                    key={key}
                    className={`flex items-center justify-between gap-2.5 rounded-lg border px-3 py-2.5 text-xs ${
                      isActive
                        ? "bg-surface-soft border-hairline"
                        : "bg-surface-card/40 border-hairline-soft"
                    }`}
                  >
                    <code
                      className={`min-w-0 flex-1 font-mono break-all ${
                        isActive ? "text-ink select-all" : "text-muted"
                      }`}
                    >
                      {entry.url}
                    </code>

                    <div className="flex-shrink-0">
                      {entry.status === "active" ? (
                        <button
                          type="button"
                          onClick={() => void handleCopy(entry, key)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-canvas hover:bg-surface-card text-ink border border-hairline font-medium transition-colors"
                          title="Copy pairing link"
                        >
                          {isCopied ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-success" />
                              <span>Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      ) : entry.status === "used" ? (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-surface-card text-muted border border-hairline text-[11px] font-medium">
                          Used
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-warning/10 text-body border border-warning/30 text-[11px] font-medium">
                          Expired
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-end gap-2 sm:gap-3 pt-3 sm:pt-4 border-t border-hairline flex-shrink-0">
          <button
            type="button"
            disabled={generating}
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2.5 sm:py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm text-ink disabled:opacity-50"
          >
            Close
          </button>
          <button
            type="button"
            disabled={loading || generating || !available || Boolean(loadError)}
            onClick={() => void handleGenerate()}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-sm font-medium text-on-primary shadow-sm disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            <span>{generating ? "Generating..." : "Generate"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
