import React, { useState } from "react";
import {
  Plus,
  Activity,
  Terminal,
  XCircle,
  ShieldAlert,
  Loader2,
  Box,
  Play,
  Square,
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
  } = useStudio();

  const [isNewAppModalOpen, setIsNewAppModalOpen] = useState<boolean>(false);

  const [isDismissedDisconnected, setIsDismissedDisconnected] = useState<boolean>(false);

  const isDisconnected = previewState?.status === "STOPPED";
  const isExecutingTurn = Boolean(
    isSending || (activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED"))
  );

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
              <button
                id="btn-studio-preview-app"
                data-testid="preview-app-btn"
                type="button"
                onClick={() => {
                  if (previewState?.status === "SERVING" && onStopPreview) {
                    onStopPreview();
                  } else if (onLaunchPreview) {
                    onLaunchPreview();
                  }
                }}
                disabled={isLaunchingPreview || previewState?.status === "PROVISIONING"}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shadow-sm cursor-pointer ${
                  previewState?.status === "SERVING"
                    ? "bg-emerald-950/80 border border-emerald-800 text-emerald-300 hover:bg-emerald-900/80"
                    : previewState?.status === "PROVISIONING" || isLaunchingPreview
                    ? "bg-slate-800 text-slate-400 cursor-wait"
                    : "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                }`}
                title={
                  previewState?.status === "SERVING"
                    ? "Preview active (click to stop)"
                    : "Launch Dedicated Preview Sandbox"
                }
              >
                {isLaunchingPreview || previewState?.status === "PROVISIONING" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                ) : previewState?.status === "SERVING" ? (
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-0.5" />
                ) : (
                  <Play className="w-3.5 h-3.5 text-indigo-400 fill-current" />
                )}
                <span>Preview App</span>
              </button>

              {(previewState?.status === "SERVING" || previewState?.status === "PROVISIONING") && onStopPreview && (
                <button
                  id="btn-studio-preview-stop"
                  data-testid="studio-stop-preview-btn"
                  type="button"
                  onClick={onStopPreview}
                  className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-rose-600/90 hover:bg-rose-600 text-white shadow-sm transition-colors cursor-pointer"
                  title="Stop preview sandbox"
                >
                  <Square className="w-3 h-3 fill-current" />
                  <span>Stop</span>
                </button>
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
              <button
                id="btn-studio-activity"
                type="button"
                onClick={() => onOpenDrawer()}
                className="flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] text-indigo-300 hover:text-white bg-indigo-900/40 hover:bg-indigo-800 transition-colors cursor-pointer"
                title="Open Agent Activity Drawer"
              >
                <Activity className="w-3 h-3" />
                <span>Activity</span>
              </button>
            )}

            <button
              id="btn-inspect-logs"
              type="button"
              onClick={onSwitchToConsole}
              className="flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] text-slate-400 hover:text-slate-200 bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer"
              title="Inspect terminal logs in Console"
            >
              <Terminal className="w-3 h-3" />
              <span>Logs</span>
            </button>

            {activeJob.status === "RUNNING" && (
              <button
                id="btn-studio-cancel"
                type="button"
                onClick={() => onCancelJob(activeJob.id)}
                className="p-1 rounded text-red-400 hover:text-red-200 hover:bg-red-950 transition-colors cursor-pointer"
                title="Cancel running assembly line"
              >
                <XCircle className="w-3.5 h-3.5" />
              </button>
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

                      {/* Text content if present */}
                      {msg.text && (
                        <div className="text-slate-200 text-xs leading-relaxed whitespace-pre-wrap">
                          {msg.text}
                        </div>
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
