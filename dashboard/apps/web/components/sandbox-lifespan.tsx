"use client";

import { useEffect, useState } from "react";

/**
 * Compute elapsed seconds, remaining seconds, and progress fraction
 * from a sandbox's created_at and timeout_secs.
 */
function computeLifespan(createdAt: string, timeoutSecs: number, now: Date) {
  const start = new Date(createdAt).getTime();
  const elapsedMs = now.getTime() - start;
  const elapsedSecs = Math.max(0, Math.floor(elapsedMs / 1000));
  const remainingSecs = Math.max(0, timeoutSecs - elapsedSecs);
  const progress = Math.min(1, Math.max(0, elapsedSecs / timeoutSecs));
  const terminatesAt = new Date(start + timeoutSecs * 1000);
  return { elapsedSecs, remainingSecs, progress, terminatesAt };
}

/** Format seconds into compact human-readable duration: "4h 23m" / "17h 37m 12s" */
function formatCountdown(totalSecs: number, includeSeconds = false): string {
  if (totalSecs <= 0) return "0m";
  const hours = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (mins > 0) parts.push(`${mins}m`);
  if (includeSeconds && secs > 0) parts.push(`${secs}s`);
  return parts.join(" ") || "<1m";
}

/** Format a Date to a readable timestamp like "27 Nov 2026 08:15 AM" */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function formatTimestamp(d: Date): string {
  const day = String(d.getDate()).padStart(2, "0");
  const month = MONTHS[d.getMonth()];
  const year = d.getFullYear();
  let hours = d.getHours();
  const minutes = String(d.getMinutes()).padStart(2, "0");
  const ampm = hours >= 12 ? "PM" : "AM";
  hours = hours % 12 || 12;
  return `${day} ${month} ${year} ${String(hours).padStart(2, "0")}:${minutes} ${ampm}`;
}

/** Choose a color for the progress bar based on remaining time fraction */
function barColor(progress: number): string {
  if (progress >= 0.9) return "bg-error";
  if (progress >= 0.75) return "bg-warning";
  return "bg-success";
}

/**
 * SandboxLifespan — replaces the static "Created / Timeout" cell for running
 * sandboxes with a progress bar, start time, and termination countdown.
 *
 * Re-renders every 30 s to keep the countdown current without excessive ticking.
 */
export function SandboxLifespan({
  createdAt,
  timeoutSecs,
  compact = false,
}: {
  createdAt: string;
  timeoutSecs: number;
  compact?: boolean;
}) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const { elapsedSecs, remainingSecs, progress, terminatesAt } =
    computeLifespan(createdAt, timeoutSecs, now);

  const startDate = new Date(createdAt);
  const elapsed = formatCountdown(elapsedSecs);
  const remaining = formatCountdown(remainingSecs);
  const totalLabel = formatCountdown(timeoutSecs);
  const terminatesAtLabel = formatTimestamp(terminatesAt);

  return (
    <div className={`flex flex-col gap-1.5 font-sans text-xs ${compact ? "min-w-0" : "min-w-[180px]"}`}>
      {/* Progress bar */}
      <div
        className="relative h-1.5 w-full rounded-full bg-hairline overflow-hidden"
        title={`${elapsed} elapsed / ${remaining} remaining of ${totalLabel}`}
      >
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ${barColor(progress)}`}
          style={{ width: `${Math.max(1, progress * 100)}%` }}
        />
      </div>

      {/* Started + elapsed */}
      <div className="flex items-center justify-between gap-2 text-body leading-tight">
        <span className="text-muted">Started</span>
        <span className="text-right tabular-nums">
          {formatTimestamp(startDate)}
          <span className="text-muted ml-1">({elapsed})</span>
        </span>
      </div>

      {/* Terminates at + countdown */}
      <div className="flex items-center justify-between gap-2 text-body leading-tight">
        <span className="text-muted">Ends</span>
        <span className="text-right tabular-nums">
          {terminatesAtLabel}
          <span className={`ml-1 font-medium ${progress >= 0.9 ? "text-error" : progress >= 0.75 ? "text-warning" : "text-muted"}`}>
            ({remaining})
          </span>
        </span>
      </div>
    </div>
  );
}
