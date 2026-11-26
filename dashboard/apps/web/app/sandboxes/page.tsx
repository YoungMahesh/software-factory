"use client";

import { useMemo } from "react";
import type { SandboxCost } from "@dashboard/types";
import { Camera, Copy, ExternalLink, Power, RefreshCw } from "lucide-react";
import { useDashboard } from "@/components/dashboard-provider";
import { SandboxLifespan } from "@/components/sandbox-lifespan";
import {
  copyToClipboard,
  formatCostBreakdown,
  formatDate,
  formatDurationCompact,
  formatTimeout,
  formatUsdCost,
  getSandboxCopyTarget,
  summarizeSandboxCosts,
} from "@/lib/format";

function SandboxCostDisplay({
  cost,
  loading,
  align = "right",
}: {
  cost: SandboxCost | undefined;
  loading: boolean;
  align?: "left" | "right";
}) {
  const breakdown = formatCostBreakdown(cost?.cost_by_resource_usd);
  const duration = formatDurationCompact(cost?.duration_seconds);
  const tooltipParts = [
    breakdown,
    duration ? `Billed runtime: ${duration}` : "",
    cost?.error ? `Error: ${cost.error}` : "",
    "Estimated Modal usage cost before workspace credits/adjustments",
  ].filter(Boolean);
  const alignClass = align === "right" ? "items-end text-right" : "items-start text-left";

  if (cost && cost.cost_usd !== null && cost.cost_usd !== undefined) {
    return (
      <div className={`flex flex-col ${alignClass}`} title={tooltipParts.join(" · ")}>
        <span className="font-mono font-semibold text-ink tabular-nums">
          {formatUsdCost(cost.cost_usd)}
        </span>
        {breakdown && (
          <span className="font-sans text-[11px] text-muted">{breakdown}</span>
        )}
      </div>
    );
  }

  if (loading && !cost) {
    return (
      <span className="font-mono text-xs text-muted animate-pulse" title="Fetching Modal usage cost...">
        ...
      </span>
    );
  }

  if (cost?.error) {
    return (
      <span className="font-sans text-xs text-muted" title={tooltipParts.join(" · ")}>
        Unavailable
      </span>
    );
  }

  if (cost && (cost.source === "sandbox_stats" || cost.source === "app_stats")) {
    return (
      <span
        className="font-sans text-xs text-muted"
        title="Modal has not recorded usage samples for this sandbox yet"
      >
        Pending
      </span>
    );
  }

  return <span className="font-mono text-xs text-muted">—</span>;
}

export default function SandboxesPage() {
  const {
    sandboxes,
    sandboxCosts,
    costsLoading,
    costsFetchedAt,
    searchQuery,
    openSnapshotModal,
    terminateSandbox,
    refreshSandboxCosts,
    showToast,
  } = useDashboard();

  const filteredSandboxes = useMemo(() => {
    const active = sandboxes.filter((s) => s.running);
    const q = searchQuery.toLowerCase().trim();
    if (!q) return active;
    return active.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        (s.name?.toLowerCase().includes(q) ?? false) ||
        (s.app_name?.toLowerCase().includes(q) ?? false) ||
        (s.profile?.toLowerCase().includes(q) ?? false),
    );
  }, [sandboxes, searchQuery]);

  const costSummary = useMemo(
    () => summarizeSandboxCosts(filteredSandboxes, sandboxCosts),
    [filteredSandboxes, sandboxCosts],
  );

  async function handleCopySsh(sb: (typeof sandboxes)[number]) {
    const { text, toast } = getSandboxCopyTarget(sb);
    await copyToClipboard(text);
    showToast(toast);
  }

  return (
    <div className="space-y-4">
      {filteredSandboxes.length > 0 && (
        <div className="bg-surface-soft border border-hairline rounded-xl px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs shadow-2xs">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-muted">
              Running:{" "}
              <span className="font-mono font-semibold text-ink">
                {filteredSandboxes.length}
              </span>
            </span>
            <span className="text-hairline hidden sm:inline">|</span>
            <span className="text-muted">
              Total Accrued Cost:{" "}
              <span className="font-mono font-semibold text-ink tabular-nums">
                {costsLoading && costSummary.totalUsd === null
                  ? "..."
                  : formatUsdCost(costSummary.totalUsd)}
              </span>
              {costSummary.knownCount > 0 && costSummary.pendingCount > 0 && (
                <span className="ml-1 text-[11px] text-muted">
                  ({costSummary.pendingCount} pending)
                </span>
              )}
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2.5 text-[11px] text-muted">
            <span>
              Est. compute/memory spend · lags a few min
              {costsFetchedAt ? ` · Updated ${formatDate(costsFetchedAt)}` : ""}
            </span>
            <button
              type="button"
              disabled={costsLoading}
              onClick={() => void refreshSandboxCosts(true)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-canvas hover:bg-surface-card border border-hairline text-xs font-medium text-ink transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${costsLoading ? "animate-spin text-primary" : ""}`} />
              <span>Refresh Costs</span>
            </button>
          </div>
        </div>
      )}

      <div className="md:hidden space-y-3">
        {filteredSandboxes.map((sb) => (
          <div
            key={sb.id}
            className="bg-surface-soft border border-hairline rounded-xl p-4 space-y-3 shadow-2xs"
          >
            <div className="flex items-center justify-between gap-2">
              {sb.running ? (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success/15 text-ink border border-success/40 font-mono">
                  <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-success animate-pulse" />
                  RUNNING
                </span>
              ) : (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-card text-muted border border-hairline font-mono">
                  STOPPED
                  {sb.exit_code !== null && sb.exit_code !== undefined
                    ? ` (${sb.exit_code})`
                    : ""}
                </span>
              )}
              <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-primary/10 text-primary-active border border-primary/25 font-mono truncate max-w-[50%]">
                {sb.profile || "default"}
              </span>
            </div>

            <div className="min-w-0">
              <div className="font-semibold text-ink text-sm truncate">
                {sb.name || "—"}
              </div>
              <div className="text-xs text-muted truncate">
                {sb.app_name || "default-app"}
              </div>
            </div>

            <div className="bg-canvas border border-hairline rounded-lg p-2.5 space-y-1.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted flex-shrink-0">Sandbox ID</span>
                <div className="flex items-center gap-1.5 min-w-0 font-mono text-ink">
                  <span className="truncate">{sb.id}</span>
                  <button
                    type="button"
                    onClick={async () => {
                      await copyToClipboard(sb.id);
                      showToast("Sandbox ID copied!");
                    }}
                    title="Copy Sandbox ID"
                    className="text-muted hover:text-ink p-1 flex-shrink-0"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex items-center justify-between gap-2 text-body">
                {sb.running && sb.created_at && sb.timeout_secs ? (
                  <SandboxLifespan createdAt={sb.created_at} timeoutSecs={sb.timeout_secs} compact />
                ) : (
                  <>
                    <span className="text-muted flex-shrink-0">Started</span>
                    <span className="text-right break-words">
                      {formatDate(sb.created_at)}
                      {sb.timeout_secs ? ` · ${formatTimeout(sb.timeout_secs)}` : ""}
                    </span>
                  </>
                )}
              </div>
              <div className="flex items-start justify-between gap-2 text-body">
                <span className="text-muted flex-shrink-0">Cost</span>
                <SandboxCostDisplay cost={sandboxCosts[sb.id]} loading={costsLoading} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                disabled={!sb.running}
                onClick={() => openSnapshotModal(sb)}
                className="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary-active border border-primary/25 text-xs font-medium transition-colors disabled:opacity-40"
              >
                <Camera className="w-3.5 h-3.5 mr-1.5" />
                Snapshot
              </button>

              <button
                type="button"
                disabled={!sb.running}
                onClick={() => void handleCopySsh(sb)}
                className="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-canvas hover:bg-surface-card text-ink border border-hairline text-xs font-medium transition-colors disabled:opacity-40"
              >
                Copy SSH
              </button>

              {sb.t3_pair_url ? (
                <a
                  href={sb.t3_pair_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary-active border border-primary/25 text-xs font-medium transition-colors"
                >
                  <span>T3Code</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                <button
                  type="button"
                  disabled
                  className="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-surface-card text-muted border border-hairline text-xs font-medium cursor-not-allowed opacity-50"
                >
                  T3Code
                </button>
              )}

              <button
                type="button"
                disabled={!sb.running}
                onClick={() => void terminateSandbox(sb)}
                className="inline-flex items-center justify-center px-3 py-2 rounded-lg bg-error/10 hover:bg-error/20 text-error border border-error/25 text-xs font-medium transition-colors disabled:opacity-40"
              >
                <Power className="w-3.5 h-3.5 mr-1" />
                Terminate
              </button>
            </div>
          </div>
        ))}

        {filteredSandboxes.length === 0 && (
          <div className="bg-surface-soft rounded-xl border border-hairline px-4 py-10 text-center text-sm text-muted">
            No matching sandboxes found in selected workspace profile.
          </div>
        )}
      </div>

      <div className="hidden md:block bg-surface-soft rounded-xl border border-hairline overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-hairline text-left text-sm">
            <thead className="bg-surface-card/60 text-xs font-semibold text-muted uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-6 py-4">
                  Status
                </th>
                <th scope="col" className="px-6 py-4">
                  Profile
                </th>
                <th scope="col" className="px-6 py-4">
                  Instance / App Name
                </th>
                <th scope="col" className="px-6 py-4">
                  Sandbox ID
                </th>
                <th scope="col" className="px-6 py-4">
                  Lifespan
                </th>
                <th scope="col" className="px-6 py-4 text-right">
                  Cost
                </th>
                <th scope="col" className="px-6 py-4 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline font-mono bg-canvas">
              {filteredSandboxes.map((sb) => (
                <tr key={sb.id} className="hover:bg-surface-soft/70 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap">
                    {sb.running ? (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success/15 text-ink border border-success/40">
                        <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-success animate-pulse" />
                        RUNNING
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-card text-muted border border-hairline">
                        STOPPED
                        {sb.exit_code !== null && sb.exit_code !== undefined
                          ? ` (${sb.exit_code})`
                          : ""}
                      </span>
                    )}
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-primary/10 text-primary-active border border-primary/25">
                      {sb.profile || "default"}
                    </span>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap font-sans">
                    <div className="font-medium text-ink">{sb.name || "—"}</div>
                    <div className="text-xs text-muted">
                      {sb.app_name || "default-app"}
                    </div>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-body">
                    <div className="flex items-center gap-2">
                      <span>{sb.id}</span>
                      <button
                        type="button"
                        onClick={async () => {
                          await copyToClipboard(sb.id);
                          showToast("Sandbox ID copied!");
                        }}
                        title="Copy Sandbox ID"
                        className="text-muted hover:text-ink"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>

                  <td className="px-6 py-4 font-sans text-xs text-body">
                    {sb.running && sb.created_at && sb.timeout_secs ? (
                      <SandboxLifespan createdAt={sb.created_at} timeoutSecs={sb.timeout_secs} />
                    ) : (
                      <>
                        <div>{formatDate(sb.created_at)}</div>
                        <div className="text-muted">{formatTimeout(sb.timeout_secs)}</div>
                      </>
                    )}
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <SandboxCostDisplay cost={sandboxCosts[sb.id]} loading={costsLoading} />
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-right font-sans space-x-2">
                    <button
                      type="button"
                      disabled={!sb.running}
                      onClick={() => openSnapshotModal(sb)}
                      className="inline-flex items-center px-3 py-1.5 rounded-md bg-primary/10 hover:bg-primary/20 text-primary-active border border-primary/25 text-xs font-medium transition-colors disabled:opacity-40"
                    >
                      <Camera className="w-3.5 h-3.5 mr-1" />
                      Snapshot
                    </button>

                    <button
                      type="button"
                      disabled={!sb.running}
                      onClick={() => void handleCopySsh(sb)}
                      title={
                        sb.ssh_config
                          ? "Copy ~/.ssh/config snippet"
                          : "Copy SSH command"
                      }
                      className="inline-flex items-center px-2.5 py-1.5 rounded-md bg-surface-soft hover:bg-surface-card text-ink border border-hairline text-xs font-medium transition-colors disabled:opacity-40"
                    >
                      SSH
                    </button>

                    {sb.t3_pair_url ? (
                      <a
                        href={sb.t3_pair_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center px-2.5 py-1.5 rounded-md bg-primary/10 hover:bg-primary/20 text-primary-active border border-primary/25 text-xs font-medium transition-colors"
                      >
                        T3Code
                      </a>
                    ) : (
                      <button
                        type="button"
                        disabled
                        title="T3 Code server not running or tunnel unavailable"
                        className="inline-flex items-center px-2.5 py-1.5 rounded-md bg-surface-card text-muted border border-hairline text-xs font-medium cursor-not-allowed opacity-50"
                      >
                        T3Code
                      </button>
                    )}

                    <button
                      type="button"
                      disabled={!sb.running}
                      onClick={() => void terminateSandbox(sb)}
                      className="inline-flex items-center px-2.5 py-1.5 rounded-md bg-error/10 hover:bg-error/20 text-error border border-error/25 text-xs font-medium transition-colors disabled:opacity-40"
                    >
                      Terminate
                    </button>
                  </td>
                </tr>
              ))}

              {filteredSandboxes.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-12 text-center text-muted font-sans"
                  >
                    No matching sandboxes found in selected workspace profile.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
