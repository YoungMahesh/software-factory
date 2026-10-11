import React, { useState, useEffect } from "react";
import {
  Plus,
  Activity,
  Terminal,
  XCircle,
  ShieldAlert,
  Box,
  Play,
  Square,
  Check,
} from "lucide-react";
import { LivePreview } from "../components/LivePreview";
import { ThinkingAccordion } from "../components/ThinkingAccordion";
import { ToolChip } from "../components/ToolChip";
import { useStudio } from "../context/StudioContext";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { NewAppModal } from "../components/NewAppModal";
import { DisconnectedModal } from "../components/DisconnectedModal";
import { PromptComposer } from "../components/PromptComposer";
import { ApprovalCard } from "../components/ApprovalCard";

export interface StudioViewProps {
  className?: string;
}

export const StudioView: React.FC<StudioViewProps> = ({ className = "" }) => {
  const {
    repos,
    selectedRepo,
    onSelectRepo,
    onCreateRepo,
    activeJob,
    messages,
    onSendPrompt,
    onApprovePlan,
    isApproving = false,
    onCancelJob,
    onSwitchToConsole,
    onOpenDrawer,
    isSending = false,
    previewState = null,
    onLaunchPreview,
    onStopPreview,
    onRetryPreview,
    onReconnectPreview,
    refreshKey,
    isLaunchingPreview = false,
    onClearChat,
    isClearingChat = false,
    isChatCleared = false,
  } = useStudio();

  const [isNewAppModalOpen, setIsNewAppModalOpen] = useState<boolean>(false);

  const [isDismissedDisconnected, setIsDismissedDisconnected] = useState<boolean>(false);

  useEffect(() => {
    if (previewState?.status !== "STOPPED") {
      setIsDismissedDisconnected(false);
    }
  }, [previewState?.status, selectedRepo]);

  const isDisconnected = previewState?.status === "STOPPED";
  const isExecutingTurn = Boolean(
    isSending || (activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED"))
  );
  const isServing = previewState?.status === "SERVING";
  const isProvisioning = previewState?.status === "PROVISIONING";

  const handleReconnect = () => {
    if (onReconnectPreview) {
      onReconnectPreview();
    } else if (onLaunchPreview) {
      onLaunchPreview();
    }
  };

  return (
    <div id="studio-view" className={`flex flex-col h-[calc(100vh-4.25rem)] overflow-hidden ${className}`}>
      {/* Studio Top Control Bar */}
      <div className="flex items-center justify-between px-6 py-2.5 bg-slate-900 border-b border-slate-800 shrink-0">
        <div className="flex items-center space-x-3">
          <Box className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">Current App:</span>
          <select
            id="studio-select-repo"
            value={selectedRepo}
            onChange={(e) => onSelectRepo(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select a repository...</option>
            {repos.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name} {r.is_tanstack_compatible ? "✦" : ""}
              </option>
            ))}
          </select>

          <Button
            id="btn-studio-new-app"
            type="button"
            variant="primary"
            size="sm"
            onClick={() => setIsNewAppModalOpen(true)}
            icon={<Plus className="w-3.5 h-3.5" />}
          >
            New App
          </Button>

          {selectedRepo && (
            <div className="flex items-center space-x-2">
              <Button
                id="btn-studio-preview-app"
                data-testid="preview-app-btn"
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (isServing && onStopPreview) {
                    onStopPreview();
                  } else if (onLaunchPreview) {
                    onLaunchPreview();
                  }
                }}
                disabled={isLaunchingPreview || isProvisioning}
                isLoading={isLaunchingPreview || isProvisioning}
                icon={
                  isServing ? (
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-0.5" />
                  ) : (
                    <Play className="w-3.5 h-3.5 text-indigo-400 fill-current" />
                  )
                }
                title={
                  isServing
                    ? "Preview active (click to stop)"
                    : "Launch Unified Studio Sandbox"
                }
                className={
                  isServing
                    ? "bg-emerald-950/80 border-emerald-800 text-emerald-300 hover:bg-emerald-900/80"
                    : isProvisioning || isLaunchingPreview
                    ? "bg-slate-800 text-slate-400 cursor-wait"
                    : ""
                }
              >
                Preview App
              </Button>

              {(isServing || isProvisioning) && onStopPreview && (
                <Button
                  id="btn-studio-preview-stop"
                  data-testid="studio-stop-preview-btn"
                  type="button"
                  variant="danger"
                  size="sm"
                  onClick={onStopPreview}
                  icon={<Square className="w-3 h-3 fill-current" />}
                  title="Stop preview sandbox"
                >
                  Stop
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Floating / Top Status Badge for Active Job */}
        {activeJob && (
          <div
            id="studio-floating-status-badge"
            className="flex items-center space-x-2 bg-slate-950 px-3 py-1.5 rounded-full border border-indigo-900/60 shadow-md text-xs"
          >
            <Badge id="studio-badge-stage-text" variant="stage">
              {activeJob.stage}
            </Badge>
            <span id="studio-badge-job-detail" className="font-mono text-slate-300 text-[11px] truncate max-w-[150px]">
              {activeJob.id}
            </span>

            {onOpenDrawer && (
              <Button
                id="btn-studio-activity"
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onOpenDrawer()}
                icon={<Activity className="w-3 h-3" />}
                className="px-2 py-0.5 text-[11px] text-indigo-300 hover:text-white bg-indigo-900/40 hover:bg-indigo-800"
                title="Open Agent Activity Drawer"
              >
                Activity
              </Button>
            )}

            <Button
              id="btn-inspect-logs"
              type="button"
              variant="secondary"
              size="sm"
              onClick={onSwitchToConsole}
              icon={<Terminal className="w-3 h-3" />}
              className="px-2 py-0.5 text-[11px] text-slate-400 hover:text-slate-200"
              title="Inspect terminal logs in Console"
            >
              Logs
            </Button>

            {activeJob.status === "RUNNING" && (
              <Button
                id="btn-studio-cancel"
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onCancelJob(activeJob.id)}
                icon={<XCircle className="w-3.5 h-3.5" />}
                className="p-1 text-red-400 hover:text-red-200 hover:bg-red-950"
                title="Cancel running assembly line"
              />
            )}
          </div>
        )}
      </div>

      {/* Main Split Layout: Chat Conversation Left, Live Preview Right */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Chat Conversation & Prompt Composer */}
        <div className="w-full md:w-[480px] lg:w-[520px] flex flex-col border-r border-slate-800 bg-slate-950 shrink-0">
          {/* Chat Timeline */}
          <div
            id="studio-chat-history"
            className="flex-1 overflow-y-auto p-4 space-y-4"
          >
            {isChatCleared && (
              <div
                data-testid="chat-cleared-banner"
                className="flex items-center space-x-2 p-3 rounded-lg bg-emerald-950/40 border border-emerald-900/50 text-emerald-300 text-xs"
              >
                <Check className="w-4 h-4 shrink-0 text-emerald-400" />
                <span>Chat history cleared for {selectedRepo}.</span>
              </div>
            )}
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-500">
                <Box className="w-8 h-8 mb-2 text-slate-600" />
                <h3 className="text-xs font-semibold text-slate-400 mb-1">
                  Factory Studio Workspace
                </h3>
                <p className="text-[11px] max-w-xs text-slate-500">
                  Select a repository and prompt the assembly line to build pages, components, and full application flows.
                </p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${
                    msg.role === "user" ? "items-end" : "items-start"
                  }`}
                >
                  {/* User Bubble */}
                  {msg.role === "user" ? (
                    <div className="max-w-[85%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs shadow-sm leading-relaxed whitespace-pre-wrap">
                      {msg.text}
                    </div>
                  ) : (
                    /* Assistant Response Card */
                    <div className="w-full bg-slate-900/60 border border-slate-800 rounded-xl p-3.5 space-y-2.5 shadow-sm text-xs">
                      {/* Intent Guard Refusal Banner (if rejected) */}
                      {msg.refusal && (
                        <div className="p-3 rounded-lg border border-rose-800/80 bg-rose-950/30 text-xs">
                          <div className="flex items-center space-x-2 text-rose-400 font-semibold mb-1">
                            <ShieldAlert className="w-4 h-4 shrink-0" />
                            <span>Request Refused</span>
                            {msg.refusal.category && (
                              <Badge variant="danger" className="font-mono">
                                {msg.refusal.category}
                              </Badge>
                            )}
                          </div>
                          <p className="text-rose-200 text-xs mb-1">
                            {msg.refusal.message}
                          </p>
                          {msg.refusal.reason && (
                            <p className="text-[11px] text-slate-400">
                              Reason: {msg.refusal.reason}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Inline Thinking Disclosure */}
                      {msg.thinking && (
                        <ThinkingAccordion
                          stage={msg.stage}
                          text={msg.thinking.text}
                          durationMs={msg.thinking.durationMs}
                          done={msg.thinking.done}
                        />
                      )}

                      {/* Inline Sequential Step Chips */}
                      {msg.stepChips && msg.stepChips.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {msg.stepChips.map((chip) => (
                            <ToolChip
                              key={chip.id}
                              toolName={chip.toolName}
                              toolCallId={chip.toolCallId}
                              stage={chip.stage}
                              data={chip.data}
                              onClick={() => onOpenDrawer && onOpenDrawer(chip.toolCallId)}
                            />
                          ))}
                        </div>
                      )}

                      {/* Grilling Turn: Interview Round or Ready for Approval */}
                      {msg.grillTurn ? (
                        msg.grillTurn.type === "grill_round" ? (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <Badge variant="stage" data-testid="grilling-round-badge">
                                Grill &amp; Align (Round {msg.grillTurn.round})
                              </Badge>
                            </div>

                            {msg.grillTurn.sharpened_terms && msg.grillTurn.sharpened_terms.length > 0 && (
                              <div
                                data-testid="sharpened-terms-banner"
                                className="p-2.5 rounded-lg bg-indigo-950/40 border border-indigo-900/50 space-y-1.5 text-xs"
                              >
                                <div className="font-semibold text-indigo-300 text-[11px] uppercase tracking-wider">
                                  Sharpened Domain Concepts
                                </div>
                                {msg.grillTurn.sharpened_terms.map((t, idx) => (
                                  <div key={idx} className="text-[11px] text-slate-300 leading-relaxed">
                                    • <span className="line-through text-slate-400">{t.fuzzy_term}</span> ➔{" "}
                                    <span className="font-semibold text-indigo-300">{t.canonical_term}</span>:{" "}
                                    <span className="text-slate-400">{t.explanation}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {msg.grillTurn.summary && (
                              <p data-testid="grilling-round-summary" className="text-slate-300 text-xs font-medium leading-relaxed">
                                {msg.grillTurn.summary}
                              </p>
                            )}

                            {msg.grillTurn.questions && msg.grillTurn.questions.length > 0 && (
                              <div data-testid="grilling-questions-list" className="space-y-2.5 pt-1">
                                {msg.grillTurn.questions.map((q) => (
                                  <div
                                    key={q.id}
                                    data-testid={`grill-question-${q.id}`}
                                    className="p-3 rounded-lg bg-slate-950/80 border border-indigo-950/80 space-y-2"
                                  >
                                    <div className="flex items-center space-x-1.5 text-xs">
                                      <span className="text-indigo-400 font-bold">❓ {q.id}</span>
                                      <span className="text-slate-500">—</span>
                                      <span className="text-slate-200 font-semibold">{q.title}</span>
                                    </div>
                                    <p className="text-slate-300 text-xs leading-relaxed">{q.question}</p>
                                    {q.options && q.options.length > 0 && (
                                      <ul className="list-disc list-inside space-y-0.5 text-[11px] text-slate-400 pl-1">
                                        {q.options.map((opt, i) => (
                                          <li key={i}>{opt}</li>
                                        ))}
                                      </ul>
                                    )}
                                    <div
                                      data-testid={`recommended-answer-${q.id}`}
                                      className="flex items-center space-x-1.5 text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-900/50 px-2.5 py-1.5 rounded"
                                    >
                                      <span className="shrink-0 font-bold">➡️</span>
                                      <span className="font-medium shrink-0">Recommended:</span>
                                      <span className="text-emerald-300">{q.recommended}</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <ApprovalCard
                            turn={msg.grillTurn}
                            onApprove={(turn) => onApprovePlan && onApprovePlan(turn)}
                            isApproving={isApproving}
                            isApproved={Boolean(activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED"))}
                          />
                        )
                      ) : (
                        /* Text content if present */
                        msg.text && (
                          <div className="text-slate-200 text-xs leading-relaxed whitespace-pre-wrap">
                            {msg.text}
                          </div>
                        )
                      )}
                    </div>
                  )}

                  <span className="text-[10px] text-slate-500 mt-1 px-1">
                    {new Date(msg.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              ))
            )}
          </div>

          {/* Prompt Composer */}
          <PromptComposer
            selectedRepo={selectedRepo}
            isExecutingTurn={isExecutingTurn}
            isDisconnected={isDisconnected}
            activeStage={activeJob?.stage}
            onSendPrompt={onSendPrompt}
            onClearChat={onClearChat}
            isClearingChat={isClearingChat}
            isChatCleared={isChatCleared}
          />
        </div>

        {/* Right: Live Preview Iframe */}
        <div className="flex-1 bg-slate-950 p-4 overflow-hidden">
          <LivePreview
            previewUrl={previewState?.preview_url || null}
            status={previewState?.status || "IDLE"}
            stage={previewState?.status === "PROVISIONING" ? previewState.stage : "IDLE"}
            branch={previewState?.branch || null}
            logs={previewState?.logs || []}
            errorMessage={previewState?.error_message || null}
            onLaunchPreview={onLaunchPreview}
            onStopPreview={onStopPreview}
            onRetryPreview={onRetryPreview || onLaunchPreview}
            onReconnectPreview={handleReconnect}
            refreshKey={refreshKey}
            isLaunching={isLaunchingPreview}
          />
        </div>
      </div>

      {/* New App Modal */}
      <NewAppModal
        isOpen={isNewAppModalOpen}
        onClose={() => setIsNewAppModalOpen(false)}
        onCreate={onCreateRepo}
      />

      {/* Sandbox Disconnected Dialog */}
      <DisconnectedModal
        isOpen={isDisconnected && !isDismissedDisconnected}
        branch={previewState?.branch}
        onReconnect={handleReconnect}
        onDismiss={() => setIsDismissedDisconnected(true)}
        isReconnecting={isLaunchingPreview}
      />
    </div>
  );
};
