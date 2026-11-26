"use client";

import { useState } from "react";
import type { LaunchResponse } from "@dashboard/types";
import { CheckCircle2, ChevronDown, ChevronRight, Copy, X } from "lucide-react";
import { copyToClipboard, getLaunchSshCommand, getLaunchSshConfig } from "@/lib/format";

export interface LaunchResultModalProps {
  result: LaunchResponse | null;
  logs: string[];
  onClose: () => void;
  onViewSandboxes: () => void;
  onToast: (message: string, type?: "info" | "error" | "success") => void;
}

export function LaunchResultModal({
  result,
  logs,
  onClose,
  onViewSandboxes,
  onToast,
}: LaunchResultModalProps) {
  const [sshMode, setSshMode] = useState<"config" | "command">("config");
  const [showLogs, setShowLogs] = useState(false);

  if (!result) return null;

  const sshConfigText = getLaunchSshConfig(result);
  const sshCommandText = getLaunchSshCommand(result);
  const hostAlias =
    result.t3_ssh_host || result.sandbox_name || result.app_name || "sandbox";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sandbox Launched Successfully"
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-2 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-canvas border border-hairline rounded-2xl max-w-xl w-full p-4 sm:p-6 shadow-2xl flex flex-col max-h-[92dvh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-hairline pb-3 sm:pb-4 flex-shrink-0">
          <h3 className="text-base font-semibold text-success flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <span>Sandbox Launched Successfully!</span>
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 -mr-1 text-muted hover:text-ink"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4 text-sm flex-1 min-h-0 overflow-y-auto py-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="bg-surface-soft p-2.5 rounded-lg border border-hairline min-w-0">
              <div className="text-muted">Sandbox ID</div>
              <div className="font-mono text-ink mt-0.5 break-all">{result.sandbox_id}</div>
            </div>
            <div className="bg-surface-soft p-2.5 rounded-lg border border-hairline min-w-0">
              <div className="text-muted">App Name</div>
              <div className="font-mono text-ink mt-0.5 break-all">{result.app_name}</div>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted font-medium">SSH Connection</span>
              <div className="flex items-center gap-1 bg-surface-soft p-0.5 rounded border border-hairline text-[11px]">
                <button
                  type="button"
                  onClick={() => setSshMode("config")}
                  className={`px-2 py-1 sm:py-0.5 rounded transition-colors ${
                    sshMode === "config"
                      ? "bg-primary text-on-primary font-medium"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  ~/.ssh/config
                </button>
                <button
                  type="button"
                  onClick={() => setSshMode("command")}
                  className={`px-2 py-1 sm:py-0.5 rounded transition-colors ${
                    sshMode === "command"
                      ? "bg-primary text-on-primary font-medium"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  Direct Command
                </button>
              </div>
            </div>

            {sshMode === "config" ? (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] text-muted bg-surface-soft px-2.5 py-1.5 rounded border border-hairline">
                  <span>
                    Append to <code className="text-ink">~/.ssh/config</code>, then connect:
                  </span>
                  <span className="font-mono text-primary break-all">ssh {hostAlias}</span>
                </div>
                <div className="relative bg-surface-dark text-on-dark p-3 rounded-lg border border-surface-dark-elevated font-mono text-xs">
                  <button
                    type="button"
                    onClick={async () => {
                      await copyToClipboard(sshConfigText);
                      onToast("SSH config snippet copied! Append to ~/.ssh/config");
                    }}
                    className="absolute top-2.5 right-2.5 p-1.5 rounded bg-surface-dark-elevated hover:bg-body-strong text-on-dark flex items-center gap-1 text-[11px]"
                    title="Copy SSH config snippet"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </button>
                  <pre className="overflow-x-auto whitespace-pre pr-16 select-all">
                    {sshConfigText}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="bg-surface-dark text-on-dark p-3 rounded-lg border border-surface-dark-elevated font-mono text-xs flex items-center justify-between gap-2">
                <span className="truncate min-w-0 select-all">{sshCommandText}</span>
                <button
                  type="button"
                  onClick={async () => {
                    await copyToClipboard(sshCommandText);
                    onToast("SSH command copied!");
                  }}
                  className="text-on-dark-soft hover:text-on-dark flex-shrink-0 p-1"
                  title="Copy SSH command"
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {result.t3_pair_url && (
            <div className="space-y-1">
              <div className="text-xs text-muted font-medium">T3 Code Server</div>
              <div className="bg-surface-soft p-3 rounded-lg border border-hairline text-xs">
                <a
                  href={result.t3_pair_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline break-all block font-mono"
                >
                  {result.t3_pair_url}
                </a>
              </div>
            </div>
          )}

          {result.t3_port && (
            <p className="text-xs text-muted">
              Codex profile{" "}
              <span className="text-ink font-medium">
                {result.codex_profile || "none (manual sign-in)"}
              </span>
            </p>
          )}

          {logs.length > 0 && (
            <div className="pt-2 border-t border-hairline">
              <button
                type="button"
                onClick={() => setShowLogs((v) => !v)}
                className="text-xs text-primary hover:text-primary-active flex items-center gap-1 font-medium"
              >
                {showLogs ? (
                  <ChevronDown className="w-3.5 h-3.5" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5" />
                )}
                <span>{showLogs ? "Hide Launch Transcript" : "View Launch Transcript"}</span>
              </button>
              {showLogs && (
                <div className="mt-2 bg-surface-dark text-on-dark p-2.5 rounded-lg border border-surface-dark-elevated font-mono text-[11px] max-h-40 overflow-y-auto space-y-0.5 select-text break-words">
                  {logs.map((line, idx) => (
                    <div key={idx}>{line}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end pt-3 sm:pt-4 border-t border-hairline flex-shrink-0">
          <button
            type="button"
            onClick={onViewSandboxes}
            className="w-full sm:w-auto px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-sm font-medium text-on-primary shadow-sm"
          >
            View in Sandboxes Table
          </button>
        </div>
      </div>
    </div>
  );
}
