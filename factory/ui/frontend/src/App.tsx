import React, { useState, useEffect, useCallback } from "react";
import { Job, ChatMessage, PreviewState, DrawerTab, DrawerTabParam } from "./types";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { StudioView } from "./views/StudioView";
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
import { extractFailedCommands } from "./utils/failedCommands";

export const STORAGE_KEY_SELECTED_REPO = "factory_studio_selected_repo";

export const redirectConsolePath = (): void => {
  if (typeof window !== "undefined" && (window.location.pathname === "/console" || window.location.pathname.startsWith("/console/"))) {
    const currentUrl = new URL(window.location.href);
    currentUrl.pathname = "/";
    window.history.replaceState(null, "", currentUrl.pathname + currentUrl.search);
  }
};

export const getInitialRepo = (): string => {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const repoFromUrl = params.get("repo");
    if (repoFromUrl && repoFromUrl.trim()) {
      return repoFromUrl.trim();
    }
    try {
      const repoFromStorage = localStorage.getItem(STORAGE_KEY_SELECTED_REPO);
      if (repoFromStorage && repoFromStorage.trim()) {
        return repoFromStorage.trim();
      }
    } catch {
      // Ignore localStorage access failures
    }
  }
  return "";
};

export const AppContent: React.FC = () => {
  redirectConsolePath();

  const [selectedRepo, setSelectedRepo] = useState<string>(getInitialRepo);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("timeline");
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

  // Helper to synchronize URL query param and localStorage
  const updateUrlAndStorage = useCallback((repo: string, mode: "push" | "replace" = "push") => {
    if (typeof window === "undefined") return;
    try {
      if (repo) {
        localStorage.setItem(STORAGE_KEY_SELECTED_REPO, repo);
      } else {
        localStorage.removeItem(STORAGE_KEY_SELECTED_REPO);
      }
    } catch {
      // Ignore localStorage errors
    }

    const currentUrl = new URL(window.location.href);
    if (repo) {
      currentUrl.searchParams.set("repo", repo);
    } else {
      currentUrl.searchParams.delete("repo");
    }
    const target = currentUrl.pathname + currentUrl.search;
    if (window.location.pathname + window.location.search !== target) {
      if (mode === "push") {
        window.history.pushState(null, "", target);
      } else {
        window.history.replaceState(null, "", target);
      }
    }
  }, []);

  const handleSelectRepo: React.Dispatch<React.SetStateAction<string>> = useCallback((value) => {
    setSelectedRepo((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      updateUrlAndStorage(next, "push");
      return next;
    });
  }, [updateUrlAndStorage]);

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
    setSelectedRepo: handleSelectRepo,
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
  const { handleCancelJob, handleSelectJob } = useConsoleJobs({
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

  // Validate and synchronize selectedRepo when repos load
  useEffect(() => {
    if (repos.length === 0) return;
    if (reposQuery.isFetching || reposQuery.isLoading) return;

    const repoExists = repos.some((r) => r.name === selectedRepo);
    if (!selectedRepo || !repoExists) {
      const fallbackRepo = repos[0].name;
      setSelectedRepo(fallbackRepo);
      updateUrlAndStorage(fallbackRepo, "replace");
    } else {
      updateUrlAndStorage(selectedRepo, "replace");
    }
  }, [repos, selectedRepo, reposQuery.isFetching, reposQuery.isLoading, updateUrlAndStorage]);

  // Sync preview query data into preview state
  useEffect(() => {
    if (previewQuery.data !== undefined) {
      setPreviewState(previewQuery.data);
    }
  }, [previewQuery.data]);

  // Redirect /console paths to / while preserving search parameters
  useEffect(() => {
    redirectConsolePath();
  }, []);

  useEffect(() => {
    const onPopState = () => {
      redirectConsolePath();
      const params = new URLSearchParams(window.location.search);
      const repoFromUrl = params.get("repo");
      if (repoFromUrl && repoFromUrl.trim()) {
        const clean = repoFromUrl.trim();
        setSelectedRepo(clean);
        try {
          localStorage.setItem(STORAGE_KEY_SELECTED_REPO, clean);
        } catch {
          // Ignore localStorage errors
        }
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const failedCommands = React.useMemo(() => {
    return activeJob ? extractFailedCommands(events) : [];
  }, [activeJob, events]);

  const studioContextValue: StudioContextValue = {
    repos,
    selectedRepo,
    onSelectRepo: handleSelectRepo,
    onCreateRepo: handleCreateRepo,
    activeJob,
    messages,
    onSendPrompt: handleSendPrompt,
    onRetryTurn: (prompt: string) => handleSendPrompt(prompt, true),
    onApprovePlan: handleApprovePlan,
    isApproving,
    onCancelJob: handleCancelJob,
    onSwitchToConsole: () => {
      setDrawerTab("logs");
      setIsDrawerOpen(true);
    },
    onOpenDrawer: (_targetToolCallId?: string, tab?: DrawerTabParam) => {
      if (tab) {
        setDrawerTab(tab === "failed_commands" ? "failed-commands" : tab);
      }
      setIsDrawerOpen(true);
    },
    failedCommandCount: failedCommands.length,
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
      <div className="flex flex-col min-h-screen bg-white text-ink font-sans">
        <AppNavigation
          activeJob={activeJob}
          selectedRepo={selectedRepo}
          onOpenDrawer={studioContextValue.onOpenDrawer}
          failedCommandCount={failedCommands.length}
        />

        <main className="flex-1 overflow-auto">
          <StudioView />
        </main>

        <ActivityDrawer
          isOpen={isDrawerOpen}
          onClose={() => setIsDrawerOpen(false)}
          jobId={activeJob?.id}
          stage={activeJob?.stage}
          events={events}
          logs={logs}
          jobs={jobs}
          selectedRepo={selectedRepo}
          onSelectJob={handleSelectJob}
          onCancelJob={handleCancelJob}
          initialTab={drawerTab}
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
