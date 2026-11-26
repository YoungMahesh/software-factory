"use client";

import { useState } from "react";
import type { LaunchResponse, ProfileInfo } from "@dashboard/types";
import { Loader2, Play, X } from "lucide-react";
import { extractApiError } from "@/lib/format";

export interface SnapshotLaunchTarget {
  image_id: string;
  name?: string | null;
  profile?: string | null;
  is_vm?: boolean;
}

export interface SnapshotLaunchModalProps {
  target: SnapshotLaunchTarget | null;
  profiles: ProfileInfo[];
  selectedProfile: string;
  onClose: () => void;
  onToast: (message: string, type?: "info" | "error" | "success") => void;
  onLaunched: (result: LaunchResponse) => void;
}

function deriveResumedName(target: SnapshotLaunchTarget): string {
  let baseName = "";
  if (target.name && target.name.trim() && target.name.trim() !== "Unnamed Snapshot") {
    baseName = target.name
      .trim()
      .replace(/[-_ ]*snapshot$/i, "")
      .replace(/[-_ ]+$/, "")
      .trim();
  }
  if (!baseName) {
    baseName = target.image_id.replace(/^im-/, "").slice(0, 8);
  }
  return `resumed-${baseName}`;
}

export function SnapshotLaunchModal({
  target,
  profiles,
  selectedProfile,
  onClose,
  onToast,
  onLaunched,
}: SnapshotLaunchModalProps) {
  if (!target) return null;
  return (
    <SnapshotLaunchModalContent
      key={target.image_id}
      target={target}
      profiles={profiles}
      selectedProfile={selectedProfile}
      onClose={onClose}
      onToast={onToast}
      onLaunched={onLaunched}
    />
  );
}

function SnapshotLaunchModalContent({
  target,
  profiles,
  selectedProfile,
  onClose,
  onToast,
  onLaunched,
}: SnapshotLaunchModalProps & { target: SnapshotLaunchTarget }) {
  const activeProf = profiles.find((p) => p.active)?.name || profiles[0]?.name || "";
  const isVm = Boolean(target.is_vm);

  const [profile, setProfile] = useState(
    target.profile || (selectedProfile !== "all" ? selectedProfile : activeProf),
  );
  const [name, setName] = useState(deriveResumedName(target));
  const [vm, setVm] = useState(isVm);
  const [memory, setMemory] = useState<number | null>(isVm ? 1 : null);
  const [t3, setT3] = useState(true);
  const [modalSdk, setModalSdk] = useState(true);
  const [sops, setSops] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  async function handleLaunch() {
    setSubmitting(true);
    try {
      const res = await fetch(`/api/snapshots/${encodeURIComponent(target.image_id)}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: profile || null,
          name: name.trim() || "resumed-sandbox",
          vm,
          memory: vm ? memory : null,
          sops,
          t3,
          modal: modalSdk,
        }),
      });
      if (!res.ok) {
        const err = await extractApiError(res, "Launch failed");
        throw new Error(err.message);
      }
      const data = (await res.json()) as LaunchResponse;
      onLaunched(data);
    } catch (err) {
      onToast(
        `Error launching sandbox: ${err instanceof Error ? err.message : String(err)}`,
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
      aria-label="Launch Sandbox from Snapshot"
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
            <Play className="w-5 h-5 text-primary" />
            Launch Sandbox from Snapshot
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
          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Target Modal Profile Workspace
            </label>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
            >
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                  {p.active ? " (active)" : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Snapshot Image ID
            </label>
            <input
              type="text"
              value={target.image_id}
              disabled
              className="w-full bg-surface-card border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-body font-mono cursor-not-allowed"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Sandbox App Name (--name)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="resumed-sandbox"
              className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
            />
          </div>

          <div className="p-3 bg-surface-soft border border-hairline rounded-xl space-y-2">
            <label className="flex items-center justify-between gap-3 text-xs text-ink cursor-pointer select-none">
              <div>
                <div className="font-medium">Linux VM Sandbox Mode</div>
                <div className="text-muted text-[11px]">
                  Enables virtualized hardware and Docker daemon
                </div>
              </div>
              <input
                type="checkbox"
                checked={vm}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setVm(checked);
                  if (checked && !memory) setMemory(1);
                }}
                className="rounded border-hairline text-primary focus:ring-0 flex-shrink-0"
              />
            </label>
            {vm && (
              <div className="pt-2 border-t border-hairline">
                <label className="block text-[11px] font-medium text-muted mb-1">
                  RAM Memory (GB)
                </label>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={memory ?? ""}
                  onChange={(e) =>
                    setMemory(e.target.value ? Number.parseInt(e.target.value, 10) : null)
                  }
                  placeholder="1"
                  className="w-full sm:w-24 bg-canvas border border-hairline rounded px-2.5 py-1.5 sm:py-1 text-base sm:text-xs text-ink"
                />
              </div>
            )}
          </div>

          <div className="space-y-2">
            <span className="block text-xs font-medium text-muted">Integrated Tooling</span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-ink">
              <label className="flex items-center gap-2 bg-surface-soft p-2.5 rounded-lg border border-hairline cursor-pointer">
                <input
                  type="checkbox"
                  checked={t3}
                  onChange={(e) => setT3(e.target.checked)}
                  className="rounded border-hairline text-primary focus:ring-0"
                />
                <span>T3 Code Server</span>
              </label>
              <label className="flex items-center gap-2 bg-surface-soft p-2.5 rounded-lg border border-hairline cursor-pointer">
                <input
                  type="checkbox"
                  checked={modalSdk}
                  onChange={(e) => setModalSdk(e.target.checked)}
                  className="rounded border-hairline text-primary focus:ring-0"
                />
                <span>Modal SDK</span>
              </label>
              <label className="flex items-center gap-2 bg-surface-soft p-2.5 rounded-lg border border-hairline cursor-pointer">
                <input
                  type="checkbox"
                  checked={sops}
                  onChange={(e) => setSops(e.target.checked)}
                  className="rounded border-hairline text-primary focus:ring-0"
                />
                <span>SOPS</span>
              </label>
            </div>
          </div>
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
            onClick={() => void handleLaunch()}
            className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-sm font-medium text-on-primary shadow-sm disabled:opacity-50"
          >
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Launch Sandbox
          </button>
        </div>
      </div>
    </div>
  );
}
