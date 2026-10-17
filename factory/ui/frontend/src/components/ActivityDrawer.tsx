import React, { useState, useEffect } from "react";
import { X, Copy, Check, Terminal, History, Activity, Eye, XCircle, AlertTriangle, Timer } from "lucide-react";
import { AgentEvent, JobStage, Job, DrawerTab, DrawerTabParam } from "../types";
import { copyToClipboard, formatRelativeTime } from "../utils";
import { extractFailedCommands } from "../utils/failedCommands";
import { ThinkingAccordion } from "./ThinkingAccordion";
import { CommandCard } from "./CommandCard";
import { ToolChip } from "./ToolChip";
import { DiffViewer } from "./DiffViewer";
import { AttemptDividerCard, ReviewerRejectionCard } from "./SelfCorrectionCards";
import { FailedCommandsTab } from "./activity-drawer/FailedCommandsTab";
import { Badge } from "./ui/Badge";
import { BottlenecksViewer } from "./BottlenecksViewer";

export interface ActivityDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  jobId?: string;
  stage?: JobStage | string;
  events?: AgentEvent[];
  logs?: string[];
  jobs?: Job[];
  selectedRepo?: string;
  onSelectJob?: (job: Job) => void;
  onCancelJob?: (jobId: string) => void;
  initialTab?: DrawerTabParam;
}

export const ActivityDrawer: React.FC<ActivityDrawerProps> = ({
  isOpen,
  onClose,
  jobId,
  stage,
  events = [],
  logs = [],
  jobs = [],
  selectedRepo,
  onSelectJob,
  onCancelJob,
  initialTab = "timeline",
}) => {
  const normalizedInitialTab = initialTab === "failed_commands" ? "failed-commands" : (initialTab || "timeline");
  const [activeTab, setActiveTab] = useState<DrawerTab>(normalizedInitialTab);
  const [copied, setCopied] = useState<boolean>(false);

  const failedCommands = React.useMemo(() => {
    return extractFailedCommands(events);
  }, [events]);

  const displayedJobs = React.useMemo(() => {
    if (!selectedRepo) return jobs;
    return jobs.filter((j) => !j.repo || j.repo === selectedRepo);
  }, [jobs, selectedRepo]);

  useEffect(() => {
    if (isOpen && initialTab) {
      setActiveTab(initialTab === "failed_commands" ? "failed-commands" : initialTab);
    }
  }, [isOpen, initialTab]);

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
      {/* Backdrop */}
      <div
        data-testid="activity-drawer-backdrop"
        onClick={onClose}
        className="fixed inset-0 bg-cohere-black/50 backdrop-blur-2xs transition-opacity duration-300 -z-10"
      />

      {/* Slide-over panel */}
      <div className="w-screen max-w-xl bg-soft-stone border-l border-hairline shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-hairline bg-white">
          <div className="flex items-center space-x-2.5">
            <h2 id="slide-over-title" className="text-sm font-semibold text-ink font-sans">
              Agent Activity
            </h2>
            {stage && (
              <span
                id="studio-drawer-stage-badge"
                className="px-2.5 py-0.5 rounded-pill text-[10px] font-mono font-bold bg-primary text-white border border-primary"
              >
                {stage}
              </span>
            )}
            {jobId && (
              <span
                id="studio-drawer-job-id"
                className="text-[11px] font-mono text-muted"
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
            className="p-1.5 rounded-pill text-muted hover:text-ink hover:bg-soft-stone transition-colors focus:outline-none cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Buttons */}
        <div className="flex items-center justify-between px-5 py-2.5 bg-soft-stone border-b border-hairline">
          <div className="flex items-center space-x-2">
            <button
              id="btn-drawer-tab-timeline"
              type="button"
              onClick={() => setActiveTab("timeline")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "timeline"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-ink hover:bg-white"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Timeline</span>
            </button>
            <button
              id="btn-drawer-tab-logs"
              type="button"
              onClick={() => setActiveTab("logs")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "logs"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-ink hover:bg-white"
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Terminal Logs</span>
            </button>
            <button
              id="btn-drawer-tab-bottlenecks"
              type="button"
              onClick={() => setActiveTab("bottlenecks")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "bottlenecks"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-ink hover:bg-white"
              }`}
            >
              <Timer className="w-3.5 h-3.5" />
              <span>Bottlenecks</span>
            </button>
            <button
              id="btn-drawer-tab-failed-commands"
              type="button"
              onClick={() => setActiveTab("failed-commands")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "failed-commands"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-ink hover:bg-white"
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Failed Commands</span>
              {failedCommands.length > 0 && (
                <span
                  id="failed-commands-counter-badge"
                  className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-coral text-white"
                >
                  {failedCommands.length}
                </span>
              )}
            </button>
            <button
              id="btn-drawer-tab-history"
              type="button"
              onClick={() => setActiveTab("history")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "history"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-ink hover:bg-white"
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>History</span>
            </button>
          </div>

          {activeTab === "logs" && (
            <button
              id="btn-drawer-copy-logs"
              type="button"
              onClick={handleCopyLogs}
              className="flex items-center space-x-1 px-3 py-1 rounded-pill text-xs text-muted hover:text-ink bg-white border border-hairline hover:bg-soft-stone transition-colors font-mono cursor-pointer shadow-2xs"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-deep-green" />
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
        <div className="flex-1 overflow-y-auto p-4 bg-canvas">
          {activeTab === "bottlenecks" ? (
            <div id="studio-drawer-bottlenecks" className="space-y-4">
              <BottlenecksViewer events={events} repo={selectedRepo} />
            </div>
          ) : activeTab === "timeline" ? (
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
          ) : activeTab === "logs" ? (
            <div
              id="studio-drawer-logs"
              className="font-mono text-xs text-slate-300 bg-primary border border-white/10 rounded-xl p-4 whitespace-pre-wrap leading-relaxed select-text shadow-sm"
            >
              {logs.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  No terminal logs available.
                </div>
              ) : (
                logs.join("")
              )}
            </div>
          ) : activeTab === "history" ? (
            <div id="studio-drawer-history" className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-ink font-sans">
                  Job History
                </span>
                <span id="drawer-history-count" className="text-xs font-mono text-muted">
                  {displayedJobs.length} {displayedJobs.length === 1 ? "job" : "jobs"}
                </span>
              </div>

              <div className="overflow-x-auto bg-white rounded-lg border border-hairline shadow-2xs">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-hairline text-[11px] font-mono text-muted bg-soft-stone/40">
                    <tr>
                      <th className="py-2.5 px-3">Job ID</th>
                      <th className="py-2.5 px-3">Repo</th>
                      <th className="py-2.5 px-3">Feature</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Stage</th>
                      <th className="py-2.5 px-3">Created</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody id="drawer-history-table-body" className="divide-y divide-hairline font-mono">
                    {displayedJobs.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-muted italic">
                          No jobs recorded.
                        </td>
                      </tr>
                    ) : (
                      displayedJobs.map((j) => (
                        <tr key={j.id} className="hover:bg-soft-stone/30 transition-colors">
                          <td className="py-2.5 px-3 font-semibold text-primary">{j.id}</td>
                          <td className="py-2.5 px-3 text-ink">{j.repo}</td>
                          <td className="py-2.5 px-3 text-muted">{j.feature || "—"}</td>
                          <td className="py-2.5 px-3">
                            <Badge
                              variant={
                                j.status === "SUCCESS"
                                  ? "success"
                                  : j.status === "FAILED"
                                  ? "danger"
                                  : j.status === "RUNNING"
                                  ? "console"
                                  : "neutral"
                              }
                            >
                              {j.status}
                            </Badge>
                          </td>
                          <td className="py-2.5 px-3 text-muted">{j.stage}</td>
                          <td className="py-2.5 px-3 text-muted">
                            {formatRelativeTime(j.created_at)}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <div className="flex items-center justify-end space-x-1.5">
                              <button
                                type="button"
                                data-testid={`inspect-job-logs-${j.id}`}
                                onClick={() => {
                                  onSelectJob?.(j);
                                  setActiveTab("logs");
                                }}
                                className="p-1 rounded-pill text-muted hover:text-ink hover:bg-soft-stone transition-colors cursor-pointer"
                                title="Inspect terminal logs in place"
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </button>
                              {j.status === "RUNNING" && onCancelJob && (
                                <button
                                  type="button"
                                  data-testid={`cancel-job-${j.id}`}
                                  onClick={() => onCancelJob(j.id)}
                                  className="p-1 rounded-pill text-coral hover:text-white hover:bg-coral transition-colors cursor-pointer"
                                  title="Cancel running job"
                                >
                                  <XCircle className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <FailedCommandsTab
              failedCommands={failedCommands}
              activeJobId={jobId}
              jobs={jobs}
              selectedRepo={selectedRepo}
            />
          )}
        </div>
      </div>
    </div>
  );
};
