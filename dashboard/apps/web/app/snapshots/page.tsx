"use client";

import { useMemo } from "react";
import { Copy, Play, Trash2 } from "lucide-react";
import { useDashboard } from "@/components/dashboard-provider";
import { copyToClipboard, formatDate } from "@/lib/format";

export default function SnapshotsPage() {
  const {
    snapshots,
    searchQuery,
    openLaunchFromSnapshotModal,
    deleteSnapshotRecord,
    showToast,
  } = useDashboard();

  const filteredSnapshots = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return snapshots;
    return snapshots.filter(
      (s) =>
        s.image_id.toLowerCase().includes(q) ||
        (s.name?.toLowerCase().includes(q) ?? false) ||
        (s.sandbox_id?.toLowerCase().includes(q) ?? false) ||
        (s.profile?.toLowerCase().includes(q) ?? false),
    );
  }, [snapshots, searchQuery]);

  return (
    <div className="space-y-4">
      <div className="md:hidden space-y-3">
        {filteredSnapshots.map((snap) => (
          <div
            key={snap.image_id}
            className="bg-surface-soft border border-hairline rounded-xl p-4 space-y-3 shadow-2xs"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 space-y-1">
                <div className="font-semibold text-ink text-sm break-words">
                  {snap.name || "Unnamed Snapshot"}
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`px-1.5 py-0.5 text-[10px] rounded font-mono ${
                      snap.is_vm
                        ? "bg-accent-amber/20 text-ink"
                        : "bg-accent-teal/20 text-ink"
                    }`}
                  >
                    {snap.is_vm ? "Linux VM" : "Container"}
                  </span>
                </div>
              </div>
              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-surface-card text-primary-active border border-hairline font-mono flex-shrink-0">
                {snap.profile || "any"}
              </span>
            </div>

            <div className="bg-canvas border border-hairline rounded-lg p-2.5 space-y-1.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted flex-shrink-0">Image ID</span>
                <div className="flex items-center gap-1.5 min-w-0 font-mono text-ink">
                  <span className="truncate">{snap.image_id}</span>
                  <button
                    type="button"
                    onClick={async () => {
                      await copyToClipboard(snap.image_id);
                      showToast("Image ID copied!");
                    }}
                    title="Copy Image ID"
                    className="text-muted hover:text-ink p-1 flex-shrink-0"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted flex-shrink-0">Source</span>
                <span className="font-mono text-body truncate">
                  {snap.sandbox_id || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-body">
                <span className="text-muted flex-shrink-0">Created</span>
                <span className="text-right break-words">
                  {formatDate(snap.created_at)}
                  {snap.ttl_days ? ` · ${snap.ttl_days}d TTL` : ""}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => openLaunchFromSnapshotModal(snap)}
                className="flex-1 inline-flex items-center justify-center px-3 py-2.5 rounded-lg bg-primary hover:bg-primary-active text-on-primary text-xs font-semibold transition-colors shadow-2xs"
              >
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Launch Sandbox
              </button>

              <button
                type="button"
                onClick={() => void deleteSnapshotRecord(snap)}
                title="Delete Snapshot Record"
                aria-label={`Delete snapshot ${snap.image_id}`}
                className="inline-flex items-center justify-center px-3 py-2.5 rounded-lg bg-canvas hover:bg-error/15 text-muted hover:text-error border border-hairline text-xs transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {filteredSnapshots.length === 0 && (
          <div className="bg-surface-soft rounded-xl border border-hairline px-4 py-10 text-center text-sm text-muted">
            No saved snapshots found in the registry.
          </div>
        )}
      </div>

      <div className="hidden md:block bg-surface-soft rounded-xl border border-hairline overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-hairline text-left text-sm">
            <thead className="bg-surface-card/60 text-xs font-semibold text-muted uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-6 py-4">
                  Snapshot Label
                </th>
                <th scope="col" className="px-6 py-4">
                  Profile
                </th>
                <th scope="col" className="px-6 py-4">
                  Image ID
                </th>
                <th scope="col" className="px-6 py-4">
                  Source Sandbox
                </th>
                <th scope="col" className="px-6 py-4">
                  Created / TTL
                </th>
                <th scope="col" className="px-6 py-4 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline font-mono bg-canvas">
              {filteredSnapshots.map((snap) => (
                <tr
                  key={snap.image_id}
                  className="hover:bg-surface-soft/70 transition-colors"
                >
                  <td className="px-6 py-4 whitespace-nowrap font-sans">
                    <div className="font-medium text-ink">
                      {snap.name || "Unnamed Snapshot"}
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span
                        className={`px-1.5 py-0.5 text-[10px] rounded font-mono ${
                          snap.is_vm
                            ? "bg-accent-amber/20 text-ink"
                            : "bg-accent-teal/20 text-ink"
                        }`}
                      >
                        {snap.is_vm ? "Linux VM" : "Container"}
                      </span>
                    </div>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-surface-soft text-primary-active border border-hairline">
                      {snap.profile || "any"}
                    </span>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-body">
                    <div className="flex items-center gap-2">
                      <span>{snap.image_id}</span>
                      <button
                        type="button"
                        onClick={async () => {
                          await copyToClipboard(snap.image_id);
                          showToast("Image ID copied!");
                        }}
                        title="Copy Image ID"
                        className="text-muted hover:text-ink"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-muted text-xs">
                    {snap.sandbox_id || "—"}
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap font-sans text-xs text-body">
                    <div>{formatDate(snap.created_at)}</div>
                    <div className="text-muted">
                      {snap.ttl_days ? `${snap.ttl_days} days retention` : ""}
                    </div>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-right font-sans space-x-2">
                    <button
                      type="button"
                      onClick={() => openLaunchFromSnapshotModal(snap)}
                      className="inline-flex items-center px-3 py-1.5 rounded-md bg-primary hover:bg-primary-active text-on-primary text-xs font-medium transition-colors shadow-2xs"
                    >
                      <Play className="w-3.5 h-3.5 mr-1" />
                      Launch Sandbox
                    </button>

                    <button
                      type="button"
                      onClick={() => void deleteSnapshotRecord(snap)}
                      aria-label={`Delete snapshot ${snap.image_id}`}
                      className="inline-flex items-center px-2.5 py-1.5 rounded-md bg-surface-soft hover:bg-error/15 text-muted hover:text-error border border-hairline text-xs transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}

              {filteredSnapshots.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-muted font-sans"
                  >
                    No saved snapshots found in the registry.
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
