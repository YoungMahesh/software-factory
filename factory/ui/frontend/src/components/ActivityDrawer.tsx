import React, { useState } from "react";
import { X, Copy, Check, Terminal, History } from "lucide-react";
import { AgentEvent, JobStage } from "../types";
import { copyToClipboard } from "../utils";
import { ThinkingAccordion } from "./ThinkingAccordion";
import { CommandCard } from "./CommandCard";
import { ToolChip } from "./ToolChip";
import { DiffViewer } from "./DiffViewer";
import { AttemptDividerCard, ReviewerRejectionCard } from "./SelfCorrectionCards";

interface ActivityDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  jobId?: string;
  stage?: JobStage | string;
  events?: AgentEvent[];
  logs?: string[];
}

export const ActivityDrawer: React.FC<ActivityDrawerProps> = ({
  isOpen,
  onClose,
  jobId,
  stage,
  events = [],
  logs = [],
}) => {
  const [activeTab, setActiveTab] = useState<"timeline" | "logs">("timeline");
  const [copied, setCopied] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleCopyLogs = async () => {
    const text = logs.join("");
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      id="studio-activity-drawer"
      className="fixed inset-y-0 right-0 z-50 flex max-w-full pl-10"
      aria-labelledby="slide-over-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Slide-over panel */}
      <div className="w-screen max-w-xl bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-950/70">
          <div className="flex items-center space-x-2.5">
            <h2 id="slide-over-title" className="text-sm font-semibold text-slate-100">
              Agent Activity
            </h2>
            {stage && (
              <span
                id="studio-drawer-stage-badge"
                className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-800"
              >
                {stage}
              </span>
            )}
            {jobId && (
              <span
                id="studio-drawer-job-id"
                className="text-[11px] font-mono text-slate-400"
              >
                {jobId}
              </span>
            )}
          </div>

          <button
            data-testid="close-drawer-btn"
            id="btn-close-activity-drawer"
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors focus:outline-none"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Buttons */}
        <div className="flex items-center justify-between px-5 py-2.5 bg-slate-950/40 border-b border-slate-800/80">
          <div className="flex items-center space-x-2">
            <button
              id="btn-drawer-tab-timeline"
              type="button"
              onClick={() => setActiveTab("timeline")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === "timeline"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>Timeline</span>
            </button>
            <button
              id="btn-drawer-tab-logs"
              type="button"
              onClick={() => setActiveTab("logs")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === "logs"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Terminal Logs</span>
            </button>
          </div>

          {activeTab === "logs" && (
            <button
              id="btn-drawer-copy-logs"
              type="button"
              onClick={handleCopyLogs}
              className="flex items-center space-x-1 px-2.5 py-1 rounded text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 transition-colors font-mono"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy</span>
                </>
              )}
            </button>
          )}
        </div>

        {/* Drawer Body */}
        <div className="flex-1 overflow-y-auto p-4 bg-slate-950/80">
          {activeTab === "timeline" ? (
            <div id="studio-drawer-timeline" className="space-y-3">
              {events.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs font-mono">
                  No activity events recorded yet.
                </div>
              ) : (
                (() => {
                  const groupedEvents: AgentEvent[] = [];
                  events.forEach((evt) => {
                    if (evt.type === "thinking") {
                      const last = groupedEvents[groupedEvents.length - 1];
                      if (last && last.type === "thinking" && last.stage === evt.stage) {
                        const delta = evt.data?.delta || "";
                        const prevText = last.data?.text || "";
                        last.data = {
                          ...last.data,
                          text: delta ? prevText + delta : prevText,
                          durationMs: evt.data?.durationMs || last.data?.durationMs,
                          done: Boolean(evt.data?.done) || Boolean(last.data?.done),
                        };
                        return;
                      }
                    }
                    groupedEvents.push({
                      ...evt,
                      data: {
                        ...evt.data,
                        text: evt.data?.delta || evt.data?.text || "",
                      },
                    });
                  });

                  return groupedEvents.map((evt, idx) => {
                    const key = `evt-${idx}-${evt.type}`;
                    if (evt.type === "thinking") {
                      return (
                        <ThinkingAccordion
                          key={key}
                          stage={evt.stage}
                          text={evt.data?.text || ""}
                          durationMs={evt.data?.durationMs}
                          done={Boolean(evt.data?.done)}
                        />
                      );
                    }

                  if (evt.type === "tool_start" || evt.type === "tool_result") {
                    const toolName = (evt.data?.toolName || "").toLowerCase();
                    if (toolName === "bash") {
                      return (
                        <CommandCard
                          key={key}
                          id={`drawer-${evt.data?.toolCallId || idx}`}
                          command={evt.data?.command || evt.data?.args?.command || "bash"}
                          cwd={evt.data?.cwd || evt.data?.args?.cwd}
                          stage={evt.stage}
                          exitCode={evt.data?.exitCode}
                          isError={evt.data?.isError}
                          running={evt.type === "tool_start"}
                          durationMs={evt.data?.durationMs}
                          output={evt.data?.output || evt.data?.stdout || ""}
                          stderr={evt.data?.stderr}
                        />
                      );
                    }

                    if (toolName === "edit" || toolName === "diff") {
                      if (evt.data?.diff || evt.data?.patch) {
                        return (
                          <DiffViewer
                            key={key}
                            id={`drawer-${evt.data?.toolCallId || idx}`}
                            path={evt.data?.path || evt.data?.args?.path || "diff"}
                            diff={evt.data?.diff || evt.data?.patch || ""}
                            stage={evt.stage}
                          />
                        );
                      }
                    }

                    return (
                      <div key={key} className="my-1">
                        <ToolChip
                          toolName={evt.data?.toolName || "tool"}
                          toolCallId={evt.data?.toolCallId}
                          stage={evt.stage}
                          data={evt.data}
                        />
                      </div>
                    );
                  }

                  if (evt.type === "attempt_start") {
                    return (
                      <AttemptDividerCard
                        key={key}
                        attempt={evt.data?.attempt || 1}
                        maxAttempts={evt.data?.maxAttempts || 3}
                        reason={evt.data?.reason}
                        summary={evt.data?.summary}
                      />
                    );
                  }

                  if (evt.type === "reviewer_rejection") {
                    return (
                      <ReviewerRejectionCard
                        key={key}
                        verdict={evt.data?.verdict}
                        summary={evt.data?.summary || "Reviewer rejected changes"}
                        remediation={evt.data?.remediation}
                      />
                    );
                  }

                  return null;
                });
              })())}
            </div>
          ) : (
            <div
              id="studio-drawer-logs"
              className="font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed select-text"
            >
              {logs.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  No terminal logs available.
                </div>
              ) : (
                logs.join("")
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
