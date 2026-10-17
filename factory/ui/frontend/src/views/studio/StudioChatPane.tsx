import React from "react";
import {
  Box,
  Check,
  RotateCcw,
  ShieldAlert,
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
import { GrillRoundCard, GrillErrorCard } from "./StudioGrillCards";

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
    <div className="w-full md:w-[480px] lg:w-[520px] flex flex-col border-r border-hairline bg-white shrink-0">
      {/* Chat Timeline */}
      <div
        id="studio-chat-history"
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {isChatCleared && (
          <div
            data-testid="chat-cleared-banner"
            className="flex items-center space-x-2 p-3 rounded-pill bg-pale-green border border-deep-green/20 text-deep-green text-xs font-medium"
          >
            <Check className="w-4 h-4 shrink-0 text-deep-green" />
            <span>Chat history cleared for {selectedRepo}.</span>
          </div>
        )}
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 text-muted">
            <Box className="w-8 h-8 mb-2 text-muted" />
            <h3 className="text-xs font-semibold text-ink mb-1 font-display">
              Factory Studio Workspace
            </h3>
            <p className="text-[11px] max-w-xs text-muted leading-relaxed">
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
              {/* User Bubble: Soft Stone Card with Ink Text */}
              {msg.role === "user" ? (
                <div className="max-w-[85%] bg-soft-stone text-ink border border-hairline rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs shadow-2xs leading-relaxed whitespace-pre-wrap font-sans">
                  {msg.text}
                </div>
              ) : msg.turn_data?.type === "turn_rollback" ? (
                /* Dedicated TurnRollbackCard */
                <div
                  data-testid="turn-rollback-card"
                  className="w-full bg-soft-stone border border-hairline rounded-xl p-3.5 space-y-2.5 shadow-2xs text-xs text-ink"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2 text-coral font-semibold">
                      <RotateCcw className="w-4 h-4 text-coral shrink-0" />
                      <span>Turn Rolled Back</span>
                    </div>
                    {msg.turn_data.branch && (
                      <Badge variant="stage" className="font-mono text-[10px]">
                        {msg.turn_data.branch}
                      </Badge>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 p-2 rounded-lg bg-white border border-hairline font-mono text-[11px] text-ink">
                    <span className="text-muted font-sans text-xs">Commit Reversion:</span>
                    <span className="text-coral font-mono">
                      {msg.turn_data.original_commit_sha?.slice(0, 7) || "unknown"}
                    </span>
                    <span className="text-muted font-sans">➔</span>
                    <span className="text-deep-green font-mono">
                      {msg.turn_data.revert_commit_sha?.slice(0, 7) || "unknown"}
                    </span>
                    {msg.turn_data.issue_number && (
                      <>
                        <span className="text-hairline">•</span>
                        <span className="text-ink font-sans">Issue #{msg.turn_data.issue_number}</span>
                      </>
                    )}
                  </div>

                  <p className="text-body-muted text-xs leading-relaxed">
                    {msg.text || "Live Preview restored to previous version."}
                  </p>
                </div>
              ) : (
                /* Assistant Response Card: Crisp White or Dark Console Card */
                <div
                  className={`w-full ${
                    msg.turn_data?.reverted
                      ? "bg-soft-stone/40 border-hairline/60 opacity-70"
                      : msg.grillTurn?.type === "grill_round"
                      ? "bg-white border-hairline shadow-2xs"
                      : "bg-soft-stone border-hairline shadow-2xs"
                  } rounded-xl p-3.5 space-y-2.5 text-xs border`}
                >
                  {/* Reverted Status Badge on superseded card */}
                  {msg.turn_data?.reverted && (
                    <div className="flex items-center justify-between pb-1 border-b border-hairline">
                      <Badge
                        data-testid="turn-reverted-badge"
                        variant="neutral"
                      >
                        Reverted
                      </Badge>
                      {msg.turn_data.revert_commit && (
                        <span className="text-[10px] font-mono text-muted">
                          Revert SHA: {msg.turn_data.revert_commit.slice(0, 7)}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Intent Guard Refusal Banner (if rejected) */}
                  {msg.refusal && (
                    <div className="p-3 rounded-lg border border-coral/30 bg-coral/10 text-xs">
                      <div className="flex items-center space-x-2 text-coral font-semibold mb-1">
                        <ShieldAlert className="w-4 h-4 shrink-0" />
                        <span>Request Refused</span>
                        {msg.refusal.category && (
                          <Badge variant="danger" className="font-mono">
                            {msg.refusal.category}
                          </Badge>
                        )}
                      </div>
                      <p className="text-ink text-xs mb-1 font-medium">
                        {msg.refusal.message}
                      </p>
                      {msg.refusal.reason && (
                        <p className="text-[11px] text-muted">
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

                  {/* Grilling Turn: Interview Round, Error, or Approval */}
                  {msg.grillTurn ? (
                    msg.grillTurn.type === "grill_round" ? (
                      <GrillRoundCard
                        grillTurn={msg.grillTurn}
                        onSubmitAnswers={(answers) => onSendPrompt(answers, false)}
                        isExecutingTurn={isExecutingTurn}
                        isAnswered={
                          Boolean(msg.turn_data?.reverted) ||
                          isExecutingTurn ||
                          messages.slice(messages.findIndex((m) => m.id === msg.id) + 1).some(
                            (m) => m.role === "user" || m.grillTurn || m.deliveryGate
                          )
                        }
                      />
                    ) : msg.grillTurn.type === "error" ? (
                      <GrillErrorCard
                        grillTurn={msg.grillTurn}
                        isExecutingTurn={isExecutingTurn}
                        onRetry={() => {
                          const userPrompt = getLastUserPromptBefore(messages, msg.id);
                          if (userPrompt) {
                            if (onRetryTurn) {
                              onRetryTurn(userPrompt);
                            } else {
                              onSendPrompt(userPrompt, true);
                            }
                          }
                        }}
                      />
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
                        <div className="text-ink text-xs leading-relaxed whitespace-pre-wrap">
                          {msg.text}
                        </div>
                      )}
                      {!msg.turn_data?.reverted &&
                        (msg.turn_data?.commit_sha || msg.turn_data?.sha) &&
                        msg.id === latestRollbackableMessageId && (
                          <div className="flex items-center justify-end pt-1 border-t border-hairline">
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
                              icon={<RotateCcw className="w-3.5 h-3.5 text-coral" />}
                              className="text-xs text-coral hover:text-ink px-2 py-1"
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

              <span className="text-[10px] text-muted mt-1 px-1">
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
