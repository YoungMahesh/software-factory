"use client";

import { useEffect, useRef, useState } from "react";
import type { LaunchResponse, ProfileInfo } from "@dashboard/types";
import { Box, Code2, Loader2, Plus, X } from "lucide-react";
import { consumeSseStream, copyToClipboard, extractApiError } from "@/lib/format";

export interface FreshSandboxModalProps {
  open: boolean;
  profiles: ProfileInfo[];
  selectedProfile: string;
  onClose: () => void;
  onToast: (message: string, type?: "info" | "error" | "success") => void;
  onLaunched: (result: LaunchResponse, logs: string[]) => void;
}

export function FreshSandboxModal(props: FreshSandboxModalProps) {
  if (!props.open) return null;
  return <FreshSandboxModalContent {...props} />;
}

function FreshSandboxModalContent({
  profiles,
  selectedProfile,
  onClose,
  onToast,
  onLaunched,
}: FreshSandboxModalProps) {
  const activeProf = profiles.find((p) => p.active)?.name || profiles[0]?.name || "";
  const defaultProfile = selectedProfile !== "all" ? selectedProfile : activeProf;

  const [mode, setMode] = useState<"repo" | "standalone">("repo");
  const [profile, setProfile] = useState(defaultProfile);
  const [repo, setRepo] = useState("software-factory");
  const [githubBranch, setGithubBranch] = useState("main");
  const [name, setName] = useState("");
  const [testing, setTesting] = useState(false);
  const [fullClone, setFullClone] = useState(false);
  const [vm, setVm] = useState(true);
  const [memory, setMemory] = useState<number | null>(1);
  const [t3, setT3] = useState(true);
  const [modalSdk, setModalSdk] = useState(true);
  const [sops, setSops] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const logBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs]);

  async function handleLaunch() {
    if (mode === "repo" && !repo.trim()) {
      onToast("Target repository is required in repository mode.", "error");
      return;
    }
    if (mode === "standalone" && !name.trim()) {
      onToast("Sandbox App Name is required in standalone mode.", "error");
      return;
    }

    setSubmitting(true);
    const streamLogs: string[] = ["Initiating sandbox launch pipeline..."];
    setLogs(streamLogs);

    try {
      const res = await fetch("/api/sandboxes/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          repo: mode === "repo" ? repo.trim() : null,
          github_branch: githubBranch.trim() || "main",
          testing,
          full_clone: fullClone,
          name: name.trim() || null,
          profile: profile || null,
          vm,
          memory: vm ? memory : null,
          no_cloudflare: false,
          t3,
          modal: modalSdk,
          sops,
        }),
      });

      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }

      let completed = false;
      await consumeSseStream(res, (evt) => {
        if (evt.type === "log") {
          streamLogs.push(evt.message);
          setLogs([...streamLogs]);
        } else if (evt.type === "done") {
          completed = true;
          onLaunched(evt.response, [...streamLogs]);
        } else if (evt.type === "error") {
          throw new Error(evt.detail || "Fresh sandbox launch failed");
        }
      });

      if (!completed) {
        throw new Error("Connection closed before provisioning completed.");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      streamLogs.push(`❌ ${msg}`);
      setLogs([...streamLogs]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Launch Fresh Sandbox"
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
            <Plus className="w-5 h-5 text-primary" />
            Launch Fresh Sandbox
          </h3>
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 -mr-1 text-muted hover:text-ink disabled:opacity-40"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto py-4 space-y-4">
          <div className="grid grid-cols-2 gap-2 bg-surface-soft p-1 rounded-xl border border-hairline text-xs font-medium">
            <button
              type="button"
              onClick={() => setMode("repo")}
              className={`py-2 px-2 rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
                mode === "repo"
                  ? "bg-primary text-on-primary shadow-xs"
                  : "text-muted hover:text-ink"
              }`}
            >
              <Code2 className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">Repository Sandbox</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("standalone")}
              className={`py-2 px-2 rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
                mode === "standalone"
                  ? "bg-primary text-on-primary shadow-xs"
                  : "text-muted hover:text-ink"
              }`}
            >
              <Box className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">Standalone Sandbox</span>
            </button>
          </div>

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

          {mode === "repo" ? (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted mb-1">
                  Target Repository (-r / --repo) <span className="text-error">*</span>
                </label>
                <input
                  type="text"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  placeholder="software-factory"
                  className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink font-mono focus:outline-none focus:border-primary"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">Git Branch</label>
                  <input
                    type="text"
                    value={githubBranch}
                    onChange={(e) => setGithubBranch(e.target.value)}
                    placeholder="main"
                    className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink font-mono focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">
                    App Name (optional)
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Derived from repo"
                    className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="space-y-2 pt-1">
                <label className="flex items-center gap-2 text-xs text-body cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={testing}
                    onChange={(e) => setTesting(e.target.checked)}
                    className="rounded border-hairline text-primary focus:ring-0"
                  />
                  <span>Target repository with test- prefix in default org</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-body cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={fullClone}
                    onChange={(e) => setFullClone(e.target.checked)}
                    className="rounded border-hairline text-primary focus:ring-0"
                  />
                  <span>Full Git clone (bypass depth 50 limit)</span>
                </label>
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Sandbox App Name (--name) <span className="text-error">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. dev-sandbox"
                className="w-full bg-surface-soft border border-hairline rounded-lg px-3 py-2 text-base sm:text-sm text-ink focus:outline-none focus:border-primary"
              />
              <p className="text-[11px] text-muted mt-1">
                Initializes clean environment with empty git repository at /root/&lt;name&gt;
              </p>
            </div>
          )}

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

          {(logs.length > 0 || submitting) && (
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-xs text-muted">
                <span className="flex items-center gap-1.5 font-medium">
                  {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />}
                  <span>Launch Progress &amp; Logs</span>
                </span>
                {logs.length > 0 && (
                  <button
                    type="button"
                    onClick={async () => {
                      await copyToClipboard(logs.join("\n"));
                      onToast("Launch logs copied!");
                    }}
                    className="text-xs text-primary hover:text-primary-active font-medium"
                  >
                    Copy Logs
                  </button>
                )}
              </div>
              <div
                id="fresh-launch-log-box"
                ref={logBoxRef}
                className="bg-surface-dark text-on-dark rounded-lg p-3 font-mono text-xs h-36 overflow-y-auto border border-surface-dark-elevated space-y-1 select-text break-words"
              >
                {logs.map((line, idx) => (
                  <div
                    key={idx}
                    className={
                      line.includes("❌") || line.toLowerCase().includes("error")
                        ? "text-error font-semibold"
                        : line.includes("✓") || line.includes("✨")
                          ? "text-success"
                          : "text-on-dark"
                    }
                  >
                    {line}
                  </div>
                ))}
                {submitting && (
                  <div className="text-accent-amber animate-pulse text-[11px]">
                    Provisioning sandbox in background...
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-end gap-2 sm:gap-3 pt-3 sm:pt-4 border-t border-hairline flex-shrink-0">
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2.5 sm:py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm text-ink disabled:opacity-50"
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
            <span>Launch Sandbox</span>
          </button>
        </div>
      </div>
    </div>
  );
}
