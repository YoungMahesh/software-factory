import React, { useState, useEffect, useCallback } from "react";
import { Job, ChatMessage, PreviewState } from "./types";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { StudioView } from "./views/StudioView";
import { TestingConsoleView } from "./views/TestingConsoleView";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { AppNavigation } from "./components/AppNavigation";
import { useAppTelemetry } from "./hooks/useAppTelemetry";
import { usePreviewStream } from "./hooks/usePreviewStream";
import { useStudioActions } from "./hooks/useStudioActions";
import { useConsoleJobs } from "./hooks/useConsoleJobs";
import {
  StudioProvider,
  StudioContextValue,
} from "./context/StudioContext";
import {
  useStudioRepos,
  usePreviewQuery,
  useChatMessagesQuery,
  useRepoBranchesQuery,
  studioQueryKeys,
} from "./hooks/useStudioQueries";
import { convertDbMessageToChatMessage } from "./utils";

const getInitialTab = (): "studio" | "console" => {
  if (typeof window !== "undefined" && window.location.pathname.includes("/console")) {
    return "console";
  }
  return "studio";
};

export const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"studio" | "console">(getInitialTab);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [isIssueDrawerOpen, setIsIssueDrawerOpen] = useState<boolean>(false);
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const [previewRefreshKey, setPreviewRefreshKey] = useState<number>(0);
  const [isChatCleared, setIsChatCleared] = useState<boolean>(false);

  // Queries
  const queryClient = useQueryClient();
  const reposQuery = useStudioRepos();
  const repos = reposQuery.data?.repos || [];

  const previewQuery = usePreviewQuery(selectedRepo);
  const messagesQuery = useChatMessagesQuery(selectedRepo);
  const branchesQuery = useRepoBranchesQuery(selectedRepo);

  const handlePreviewRefresh = useCallback(() => {
    setPreviewRefreshKey((prev) => prev + 1);
  }, []);

  // Telemetry & Job Stream
  const { logs, events, clearLogs } = useAppTelemetry({
    activeJobId,
    activeJob,
    setActiveJob,
    setJobs,
    setMessages,
    onPreviewRefresh: handlePreviewRefresh,
  });

  // Preview SSE Stream
  usePreviewStream({
    selectedRepo,
    previewState,
    setPreviewState,
    onPreviewRefresh: handlePreviewRefresh,
  });

  // Studio Actions & Mutations
  const {
    handleCreateRepo,
    handleLaunchPreview,
    handleReconnectPreview,
    handleStopPreview,
    handleApprovePlan,
    handleClearChat,
    handleSendPrompt,
    handleInstantDispatch,
    handleSelectBranch,
    isLaunchingPreview,
    isSendingPrompt,
    isApproving,
    isClearingChat,
    isDispatching,
    isSwitchingBranch,
  } = useStudioActions({
    selectedRepo,
    setSelectedRepo,
    messages,
    setMessages,
    activeJob,
    setActiveJob,
    setActiveJobId,
    setJobs,
    previewState,
    setPreviewState,
    setPreviewRefreshKey,
    setIsChatCleared,
    clearLogs,
  });

  // Console Job Handlers
  const { handleLaunchJob, handleCancelJob, handleSelectJob } = useConsoleJobs({
    setActiveJobId,
    setActiveJob,
    activeJob,
    setJobs,
    clearLogs,
  });

  // Revalidate issues and branches query on job completion
  useEffect(() => {
    if (activeJob?.status === "SUCCESS" && selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(selectedRepo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [activeJob?.status, selectedRepo, queryClient]);

  // Reset chat cleared state and revalidate issues and branches query when selected repo changes
  useEffect(() => {
    setIsChatCleared(false);
    if (selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(selectedRepo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [selectedRepo, queryClient]);

  // Rehydrate chat messages from the database when query data arrives
  useEffect(() => {
    if (messagesQuery.data?.messages) {
      setMessages(messagesQuery.data.messages.map(convertDbMessageToChatMessage));
      if (messagesQuery.data.messages.length > 0) {
        setIsChatCleared(false);
      }
    } else {
      setMessages([]);
    }
  }, [messagesQuery.data]);

  // Select initial repo when repos load
  useEffect(() => {
    if (!selectedRepo && repos.length > 0) {
      setSelectedRepo(repos[0].name);
    }
  }, [repos, selectedRepo]);

  // Sync preview query data into preview state
  useEffect(() => {
    if (previewQuery.data !== undefined) {
      setPreviewState(previewQuery.data);
    }
  }, [previewQuery.data]);

  // Synchronize activeTab with URL history
  const switchTab = (tab: "studio" | "console") => {
    setActiveTab(tab);
    if (typeof window !== "undefined") {
      const targetPath = tab === "console" ? "/console" : "/";
      if (window.location.pathname !== targetPath) {
        window.history.pushState(null, "", targetPath);
      }
    }
  };

  useEffect(() => {
    const onPopState = () => {
      setActiveTab(getInitialTab());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const studioContextValue: StudioContextValue = {
    repos,
    selectedRepo,
    onSelectRepo: setSelectedRepo,
    onCreateRepo: handleCreateRepo,
    activeJob,
    messages,
    onSendPrompt: handleSendPrompt,
    onRetryTurn: (prompt: string) => handleSendPrompt(prompt, true),
    onApprovePlan: handleApprovePlan,
    isApproving,
    onCancelJob: handleCancelJob,
    onSwitchToConsole: () => switchTab("console"),
    onOpenDrawer: () => setIsDrawerOpen(true),
    isSending: isSendingPrompt || isApproving,
    previewState,
    onLaunchPreview: handleLaunchPreview,
    onStopPreview: handleStopPreview,
    onRetryPreview: handleLaunchPreview,
    onReconnectPreview: handleReconnectPreview,
    refreshKey: previewRefreshKey,
    isLaunchingPreview,
    onClearChat: handleClearChat,
    isClearingChat,
    isChatCleared,
    onOpenIssueDrawer: () => setIsIssueDrawerOpen(true),
    onCloseIssueDrawer: () => setIsIssueDrawerOpen(false),
    isIssueDrawerOpen,
    onInstantDispatch: handleInstantDispatch,
    isDispatching,
    onMergeSuccess: () => {
      setPreviewState((prev) => {
        if (!prev || prev.status === "IDLE") return prev;
        return { ...prev, branch: "main" };
      });
      setPreviewRefreshKey((prev) => prev + 1);
    },
    branches: branchesQuery.data?.branches || [],
    onSelectBranch: handleSelectBranch,
    isSwitchingBranch,
  };

  return (
    <StudioProvider value={studioContextValue}>
      <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
        <AppNavigation
          activeTab={activeTab}
          onTabChange={switchTab}
          activeJob={activeJob}
          selectedRepo={selectedRepo}
        />

        <main className="flex-1 overflow-auto">
          {activeTab === "studio" ? (
            <StudioView />
          ) : (
            <TestingConsoleView
              repos={repos}
              selectedRepo={selectedRepo}
              onSelectRepo={setSelectedRepo}
              onRefreshRepos={() => reposQuery.refetch()}
              activeJob={activeJob}
              logs={logs}
              jobs={jobs}
              onLaunch={handleLaunchJob}
              onCancel={handleCancelJob}
              onSelectJob={handleSelectJob}
              onClearLogs={clearLogs}
            />
          )}
        </main>

        <ActivityDrawer
          isOpen={isDrawerOpen}
          onClose={() => setIsDrawerOpen(false)}
          jobId={activeJob?.id}
          stage={activeJob?.stage}
          events={events}
          logs={logs}
        />
      </div>
    </StudioProvider>
  );
};

export const App: React.FC = () => {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
};

export default App;
