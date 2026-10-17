import React, { createContext, useContext } from "react";
import {
  Repo,
  Job,
  ChatMessage,
  PreviewState,
  GrillTurnResult,
  StudioDispatchParams,
  StudioDispatchResponse,
} from "../types";

export interface StudioContextValue {
  repos: Repo[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  onCreateRepo: (params: { name: string; description?: string; private?: boolean }) => Promise<void>;
  activeJob: Job | null;
  messages: ChatMessage[];
  onSendPrompt: (prompt: string, grill?: boolean) => void;
  onRetryTurn?: (prompt: string) => void;
  onApprovePlan?: (turn: GrillTurnResult) => Promise<void> | void;
  isApproving?: boolean;
  onCancelJob: (jobId: string) => void;
  onSwitchToConsole: () => void;
  onOpenDrawer?: (
    targetToolCallId?: string,
    tab?: "timeline" | "logs" | "history" | "failed-commands" | "failed_commands"
  ) => void;
  failedCommandCount?: number;
  isSending?: boolean;
  previewState?: PreviewState | null;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview?: () => void;
  refreshKey?: number;
  isLaunchingPreview?: boolean;
  onClearChat?: () => Promise<void> | void;
  isClearingChat?: boolean;
  isChatCleared?: boolean;
  onOpenIssueDrawer?: () => void;
  onCloseIssueDrawer?: () => void;
  isIssueDrawerOpen?: boolean;
  onInstantDispatch?: (params: StudioDispatchParams) => Promise<StudioDispatchResponse | void>;
  isDispatching?: boolean;
  onMergeSuccess?: (result?: any) => void;
  branches?: string[];
  onSelectBranch?: (branch: string) => Promise<void> | void;
  isSwitchingBranch?: boolean;
}

export const StudioContext = createContext<StudioContextValue | undefined>(undefined);

export interface StudioProviderProps {
  value: StudioContextValue;
  children: React.ReactNode;
}

export const StudioProvider: React.FC<StudioProviderProps> = ({
  value,
  children,
}) => {
  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
};

export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (!context) {
    throw new Error("useStudio must be used within a StudioProvider");
  }
  return context;
}
