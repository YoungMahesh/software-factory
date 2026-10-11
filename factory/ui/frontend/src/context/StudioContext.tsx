import React, { createContext, useContext } from "react";
import { Repo, Job, ChatMessage, PreviewState } from "../types";

export interface StudioContextValue {
  repos: Repo[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  onCreateRepo: (params: { name: string; description?: string }) => Promise<void>;
  activeJob: Job | null;
  messages: ChatMessage[];
  onSendPrompt: (prompt: string) => void;
  onCancelJob: (jobId: string) => void;
  onSwitchToConsole: () => void;
  onOpenDrawer?: (targetToolCallId?: string) => void;
  isSending?: boolean;
  previewState?: PreviewState | null;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview?: () => void;
  refreshKey?: number;
  isLaunchingPreview?: boolean;
}

const StudioContext = createContext<StudioContextValue | undefined>(undefined);

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

export function useStudioOptional(): StudioContextValue | undefined {
  return useContext(StudioContext);
}
