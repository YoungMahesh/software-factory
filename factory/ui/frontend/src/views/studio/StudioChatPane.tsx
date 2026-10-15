import React from "react";
import {
  Box,
  Check,
  RotateCcw,
  ShieldAlert,
  AlertTriangle,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { ThinkingAccordion } from "../../components/ThinkingAccordion";
import { ToolChip } from "../../components/ToolChip";
import { ApprovalCard } from "../../components/ApprovalCard";
import { DeliveryGateCard } from "../../components/DeliveryGateCard";
import { PromptComposer } from "../../components/PromptComposer";
import { getLastUserPromptBefore } from "../../utils";
import { ChatMessage, RollbackTarget, PreviewState } from "../../types";

export interface StudioChatPaneProps {
  messages: ChatMessage[];
  isChatCleared: boolean;
  selectedRepo: string;
  isExecutingTurn: boolean;
  isDisconnected: boolean;
  activeJob: any;
  previewState: PreviewState | null;
  latestRollbackableMessageId: string | null;
  latestRollbackInfo: { target: RollbackTarget | null; isMerged: boolean };
  isRollingBack: boolean;
  isLatestTurnMerged: boolean;
  onSendPrompt: (prompt: string, grill?: boolean) => void;
  onClearChat?: () => void;
  isClearingChat?: boolean;
  onRetryTurn?: (prompt: string) => void;
  onApprovePlan?: (turn: any) => void;
  isApproving?: boolean;
  onOpenDrawer?: (toolCallId?: string) => void;
  onMergeSuccess?: (res?: any) => void;
  onOpenRollback: (turnInfo?: RollbackTarget) => void;
}

export const StudioChatPane: React.FC<StudioChatPaneProps> = ({
  messages,
  isChatCleared,
  selectedRepo,
  isExecutingTurn,
  isDisconnected,
  activeJob,
  previewState,
  latestRollbackableMessageId,
  latestRollbackInfo,
  isRollingBack,
  isLatestTurnMerged,
  onSendPrompt,
  onClearChat,
  isClearingChat,
  onRetryTurn,
  onApprovePlan,
  isApproving,
  onOpenDrawer,
  onMergeSuccess,
  onOpenRollback,
}) => {
  return (
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
              ) : msg.turn_data?.type === "turn_rollback" ? (
                /* Dedicated TurnRollbackCard */
                <div
                  data-testid="turn-rollback-card"
                  className="w-full bg-slate-900/60 border border-indigo-900/60 rounded-xl p-3.5 space-y-2.5 shadow-sm text-xs"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2 text-indigo-400 font-semibold">
                      <RotateCcw className="w-4 h-4 text-indigo-400 shrink-0" />
                      <span>Turn Rolled Back</span>
                    </div>
                    {msg.turn_data.branch && (
                      <Badge variant="stage" className="font-mono text-[10px]">
                        {msg.turn_data.branch}
                      </Badge>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 p-2 rounded bg-slate-950/80 border border-slate-800 font-mono text-[11px] text-slate-300">
                    <span className="text-slate-500 font-sans text-xs">Commit Reversion:</span>
                    <span className="text-rose-400 font-mono">
                      {msg.turn_data.original_commit_sha?.slice(0, 7) || "unknown"}
                    </span>
                    <span className="text-slate-500 font-sans">➔</span>
                    <span className="text-emerald-400 font-mono">
                      {msg.turn_data.revert_commit_sha?.slice(0, 7) || "unknown"}
                    </span>
                    {msg.turn_data.issue_number && (
                      <>
                        <span className="text-slate-600">•</span>
                        <span className="text-indigo-300 font-sans">Issue #{msg.turn_data.issue_number}</span>
                      </>
                    )}
                  </div>

                  <p className="text-slate-300 text-xs leading-relaxed">
                    {msg.text || "Live Preview restored to previous version."}
                  </p>
                </div>
              ) : (
                /* Assistant Response Card */
                <div className={`w-full ${
                  msg.turn_data?.reverted
                    ? "bg-slate-950/40 border-slate-800/80 opacity-70"
                    : "bg-slate-900/60 border-slate-800"
                } rounded-xl p-3.5 space-y-2.5 shadow-sm text-xs`}>
                  {/* Reverted Status Badge on superseded card */}
                  {msg.turn_data?.reverted && (
                    <div className="flex items-center justify-between pb-1 border-b border-slate-800/60">
                      <Badge
                        data-testid="turn-reverted-badge"
                        variant="neutral"
                        className="bg-slate-800 text-slate-400 border-slate-700"
                      >
                        Reverted
                      </Badge>
                      {msg.turn_data.revert_commit && (
                        <span className="text-[10px] font-mono text-slate-500">
                          Revert SHA: {msg.turn_data.revert_commit.slice(0, 7)}
                        </span>
                      )}
                    </div>
                  )}
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
                    ) : msg.grillTurn.type === "error" ? (
                      <div
                        data-testid="grilling-error-banner"
                        className="p-3.5 rounded-xl border border-rose-800/80 bg-rose-950/40 text-xs space-y-2.5 shadow-sm"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2 text-rose-400 font-semibold">
                            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                            <span>Inference Service Error</span>
                          </div>
                          <Badge variant="danger" className="font-mono text-[10px]">
                            ERROR
                          </Badge>
                        </div>

                        <p
                          data-testid="grilling-error-reason"
                          className="text-rose-200 text-xs font-medium leading-relaxed"
                        >
                          {msg.grillTurn.error_message ||
                            msg.grillTurn.summary ||
                            "Remote inference request failed."}
                        </p>

                        {msg.grillTurn.error_details && (
                          <div
                            data-testid="grilling-error-details"
                            className="p-2.5 rounded bg-slate-950/80 border border-slate-800 text-[11px] font-mono text-slate-400 whitespace-pre-wrap max-h-36 overflow-y-auto"
                          >
                            {msg.grillTurn.error_details}
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-1 border-t border-rose-900/40">
                          <span className="text-[11px] text-slate-400">
                            Verify network connectivity and OpenCode Credentials, then retry.
                          </span>
                          <Button
                            data-testid="grilling-retry-btn"
                            type="button"
                            variant="secondary"
                            size="sm"
                            disabled={isExecutingTurn}
                            onClick={() => {
                              const userPrompt = getLastUserPromptBefore(messages, msg.id);
                              if (userPrompt) {
                                if (onRetryTurn) {
                                  onRetryTurn(userPrompt);
                                } else {
                                  onSendPrompt(userPrompt, true);
                                }
                              }
                            }}
                            icon={<RotateCcw className="w-3.5 h-3.5" />}
                            className="bg-rose-900/40 hover:bg-rose-900/70 border-rose-800 text-rose-200"
                          >
                            Retry
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <ApprovalCard
                        turn={msg.grillTurn}
                        onApprove={(turn) => onApprovePlan && onApprovePlan(turn)}
                        isApproving={isApproving}
                        isReverted={Boolean(msg.turn_data?.reverted)}
                        isApproved={Boolean(
                          activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED")
                        )}
                      />
                    )
                  ) : msg.deliveryGate || msg.turn_data?.type === "delivery_gate" ? (
                    <DeliveryGateCard
                      repo={selectedRepo}
                      data={{
                        ...(msg.deliveryGate || msg.turn_data),
                        reverted: Boolean(msg.turn_data?.reverted || msg.deliveryGate?.reverted),
                      }}
                      activeJobRunning={Boolean(
                        activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED")
                      )}
                      onMergeSuccess={onMergeSuccess}
                      onRollbackTurn={
                        msg.id === latestRollbackableMessageId
                          ? () =>
                              onOpenRollback({
                                messageId: msg.id,
                                branch: (msg.deliveryGate || msg.turn_data)?.branch || previewState?.branch,
                                commitSha: (msg.deliveryGate || msg.turn_data)?.sha,
                                issueNumber: (msg.deliveryGate || msg.turn_data)?.resolved_issues?.[0],
                                issueTitle: (msg.deliveryGate || msg.turn_data)?.pull_request?.title,
                              })
                          : undefined
                      }
                      isRollingBack={isRollingBack}
                      isReverted={Boolean(msg.turn_data?.reverted)}
                    />
                  ) : (
                    /* Text content if present */
                    <div className="space-y-2">
                      {msg.text && (
                        <div className="text-slate-200 text-xs leading-relaxed whitespace-pre-wrap">
                          {msg.text}
                        </div>
                      )}
                      {!msg.turn_data?.reverted &&
                        (msg.turn_data?.commit_sha || msg.turn_data?.sha) &&
                        msg.id === latestRollbackableMessageId && (
                          <div className="flex items-center justify-end pt-1 border-t border-slate-800/60">
                            <Button
                              data-testid="assistant-card-rollback-btn"
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={isExecutingTurn || isRollingBack}
                              isLoading={isRollingBack}
                              onClick={() =>
                                onOpenRollback({
                                  messageId: msg.id,
                                  branch: msg.turn_data?.branch || previewState?.branch,
                                  commitSha: msg.turn_data?.commit_sha || msg.turn_data?.sha,
                                  issueNumber: msg.turn_data?.issue_number,
                                  issueTitle: msg.turn_data?.issue?.title,
                                })
                              }
                              icon={<RotateCcw className="w-3.5 h-3.5 text-slate-400" />}
                              className="text-xs text-slate-400 hover:text-indigo-300 hover:bg-indigo-950/40 px-2 py-1"
                              title="Roll back this turn"
                            >
                              Roll Back Turn
                            </Button>
                          </div>
                        )}
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
        onClearChat={onClearChat}
        isClearingChat={isClearingChat}
        isChatCleared={isChatCleared}
        onRollbackLastTurn={latestRollbackInfo.target ? () => onOpenRollback() : undefined}
        isRollingBack={isRollingBack}
        isRollbackDisabled={isLatestTurnMerged}
        rollbackDisabledReason={isLatestTurnMerged ? "Cannot roll back turn for a merged pull request" : undefined}
      />
    </div>
  );
};
