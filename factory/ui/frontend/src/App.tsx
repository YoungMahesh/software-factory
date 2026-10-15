import React, { useState, useEffect } from "react";
import {
  Boxes,
  Sparkles,
  Terminal,
  GitBranch,
} from "lucide-react";
import { Job, ChatMessage, LaunchJobParams, PreviewState, GrillTurnResult, DbChatMessage } from "./types";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { StudioView } from "./views/StudioView";
import { TestingConsoleView } from "./views/TestingConsoleView";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { useJobStream } from "./hooks/useJobStream";
import { foldTelemetryEvents } from "./utils/telemetryEvents";
import { StudioProvider, StudioContextValue } from "./context/StudioContext";
import {
  useStudioRepos,
  usePreviewQuery,
  useCreateRepoMutation,
  useLaunchPreviewMutation,
  useStopPreviewMutation,
  useSendStudioPromptMutation,
  useApprovePlanMutation,
  useChatMessagesQuery,
  useClearChatMessagesMutation,
  useDispatchStudioMutation,
  useRepoBranchesQuery,
  useUpdatePreviewBranchMutation,
  studioQueryKeys,
  createStoppedPreviewState,
} from "./hooks/useStudioQueries";
import { convertDbMessageToChatMessage } from "./utils";
import * as api from "./api";

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

  // Queries & Mutations
  const queryClient = useQueryClient();
  const reposQuery = useStudioRepos();
  const repos = reposQuery.data?.repos || [];

  const previewQuery = usePreviewQuery(selectedRepo);
  const messagesQuery = useChatMessagesQuery(selectedRepo);
  const branchesQuery = useRepoBranchesQuery(selectedRepo);

  const createRepoMutation = useCreateRepoMutation();
  const launchPreviewMutation = useLaunchPreviewMutation();
  const stopPreviewMutation = useStopPreviewMutation();
  const sendPromptMutation = useSendStudioPromptMutation();
  const approvePlanMutation = useApprovePlanMutation();
  const clearChatMutation = useClearChatMessagesMutation();
  const dispatchStudioMutation = useDispatchStudioMutation();
  const updateBranchMutation = useUpdatePreviewBranchMutation();

  const isLaunchingPreview = launchPreviewMutation.isPending;
  const isSendingPrompt = sendPromptMutation.isPending;
  const isApproving = approvePlanMutation.isPending;

  // Revalidate issues and branches query on job completion
  useEffect(() => {
    if (activeJob?.status === "SUCCESS" && selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(selectedRepo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [activeJob?.status, selectedRepo]);

  // Reset chat cleared state and revalidate issues and branches query when selected repo changes
  useEffect(() => {
    setIsChatCleared(false);
    if (selectedRepo) {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(selectedRepo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(selectedRepo) });
    }
  }, [selectedRepo]);

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

  // Real-time telemetry & logs stream
  const { job: streamedJob, logs, events, clearLogs, previewRefreshCount } = useJobStream(activeJobId);

  useEffect(() => {
    if (previewRefreshCount > 0) {
      setPreviewRefreshKey((prev) => prev + 1);
    }
  }, [previewRefreshCount]);

  // Sync streamed job state to activeJob and jobs list
  useEffect(() => {
    if (streamedJob) {
      setActiveJob(streamedJob);
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.id === streamedJob.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = streamedJob;
          return next;
        }
        return [streamedJob, ...prev];
      });
    }
  }, [streamedJob]);

  // Rehydrate & sync assistant turn in chat history from telemetry events
  useEffect(() => {
    if (events.length === 0 || !activeJobId) return;
    setMessages((prev) => foldTelemetryEvents(prev, events, activeJobId, activeJob));
  }, [events, activeJobId, activeJob]);

  // Load jobs on mount
  const loadJobs = async () => {
    try {
      const data = await api.listJobs();
      setJobs(data.jobs || []);
    } catch (err) {
      console.error("Failed to list jobs:", err);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  // Live SSE stream for preview logs and stage transitions
  useEffect(() => {
    if (!selectedRepo) return;
    if (
      !previewState ||
      (previewState.status !== "PROVISIONING" && previewState.status !== "SERVING")
    ) {
      return;
    }

    const streamUrl = api.getPreviewStreamUrl(selectedRepo);
    let es: EventSource | null = null;
    try {
      es = new EventSource(streamUrl);
    } catch (err) {
      return;
    }

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === "init") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              ...payload.preview,
              status: payload.status || prev.status,
              preview_url: payload.preview_url !== undefined ? payload.preview_url : prev.preview_url,
              logs: payload.backlog || prev.logs || [],
            } as PreviewState;
          });
        } else if (payload.event === "log") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              logs: [...(prev.logs || []), payload.data],
            } as PreviewState;
          });
        } else if (payload.event === "stage") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            if (prev.status === "PROVISIONING") {
              return {
                ...prev,
                stage: payload.stage,
              };
            }
            return prev;
          });
        } else if (payload.event === "status") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            if (payload.status === "SERVING") {
              return {
                status: "SERVING",
                branch: prev.branch || "main",
                preview_url: payload.preview_url || (prev.status === "SERVING" ? prev.preview_url : ""),
                logs: prev.logs || [],
                error_message: null,
              };
            } else if (payload.status === "STOPPED") {
              return createStoppedPreviewState(prev);
            } else if (payload.status === "FAILED") {
              return {
                status: "FAILED",
                branch: prev.branch,
                preview_url: null,
                logs: prev.logs || [],
                error_message: payload.error || "Preview failed",
              };
            } else if (payload.status === "PROVISIONING") {
              return {
                status: "PROVISIONING",
                stage: "PROVISIONING",
                branch: prev.branch || "main",
                preview_url: null,
                logs: prev.logs || [],
                error_message: null,
              };
            }
            return prev;
          });
          if (payload.status === "STOPPED" || payload.status === "FAILED") {
            es?.close();
          }
        } else if (payload.event === "preview_refresh") {
          setPreviewRefreshKey((prev) => prev + 1);
        }
      } catch (e) {
        // ignore parse error or ping
      }
    };

    es.onerror = () => {
      // Reconnects automatically unless closed
    };

    return () => {
      es?.close();
    };
  }, [selectedRepo, previewState?.status === "PROVISIONING" || previewState?.status === "SERVING"]);

  const handleLaunchPreview = async (branch?: string) => {
    if (!selectedRepo || isLaunchingPreview) return;
    try {
      const data = await launchPreviewMutation.mutateAsync({ repo: selectedRepo, branch });
      setPreviewState(data);
    } catch (err) {
      console.error("Failed to launch preview:", err);
    }
  };

  const handleReconnectPreview = async () => {
    if (!selectedRepo || isLaunchingPreview) return;
    const targetBranch = previewState?.branch || (activeJob?.feature ? `factory/${activeJob.feature}` : undefined);
    await handleLaunchPreview(targetBranch);
  };

  const handleStopPreview = async () => {
    if (!selectedRepo || stopPreviewMutation.isPending) return;
    try {
      await stopPreviewMutation.mutateAsync(selectedRepo);
      setPreviewState((prev) => (prev ? createStoppedPreviewState(prev) : null));
    } catch (err) {
      console.error("Failed to stop preview:", err);
    }
  };

  // Handle Create Repo
  const handleCreateRepo = async (params: { name: string; description?: string; private?: boolean }) => {
    const newRepo = await createRepoMutation.mutateAsync(params);
    setSelectedRepo(newRepo.name);
  };

  // Handle Launch Job from Testing Console
  const handleLaunchJob = async (params: LaunchJobParams) => {
    clearLogs();
    const createdJob = await api.launchJob(params);
    setActiveJobId(createdJob.id);
    setActiveJob(createdJob);
    setJobs((prev) => [createdJob, ...prev]);
  };

  // Handle Cancel Job
  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
      if (activeJob && activeJob.id === jobId) {
        setActiveJob({ ...activeJob, status: "CANCELLED" });
      }
      loadJobs();
    } catch (err) {
      console.error("Failed to cancel job:", err);
    }
  };

  // Handle Select Job from History
  const handleSelectJob = (job: Job) => {
    clearLogs();
    setActiveJobId(job.id);
    setActiveJob(job);
  };

  // Handle Plan Approval (commit ADR, create issue, and dispatch Assembly Line)
  const handleApprovePlan = async (turn: GrillTurnResult) => {
    if (!selectedRepo || isApproving) return;

    const prompt = turn.plan
      ? `${turn.summary ? `${turn.summary}\n\n` : ""}${turn.plan}`.trim()
      : (turn.summary || "Approved implementation plan");

    try {
      const res = await approvePlanMutation.mutateAsync({
        repo: selectedRepo,
        prompt,
        milestone_title: turn.draft_adr?.title?.replace(/^\d+:\s*/, "") || undefined,
        draft_adr: turn.draft_adr,
        context_update: turn.context_update || null,
        model: "deepseek-v4.1-flash",
        vm: false,
      });

      if (res.job) {
        clearLogs();
        setActiveJobId(res.job.id);
        setActiveJob(res.job);
        setJobs((prev) => [res.job!, ...prev]);

        const assistantMessage: ChatMessage = {
          id: `assistant-${res.job.id}`,
          role: "assistant",
          timestamp: Date.now(),
          jobId: res.job.id,
          stage: res.job.stage,
          text: `Plan approved! Dispatched assembly line targeting ${res.job.feature || res.job.repo}`,
          thinking: {
            text: "Initializing autonomous agent harness...",
            done: false,
          },
          stepChips: [],
        };
        setMessages((prev) => [...prev, assistantMessage]);

        queryClient.setQueryData<{ repo: string; messages: DbChatMessage[] }>(
          studioQueryKeys.messages(selectedRepo),
          (old) => ({
            repo: selectedRepo,
            messages: [
              ...(old?.messages || []),
              {
                id: assistantMessage.id,
                repo: selectedRepo,
                role: "assistant",
                content: assistantMessage.text || "",
                turn_data: { status: "approved", job_id: res.job!.id, draft_adr: turn.draft_adr },
                created_at: assistantMessage.timestamp / 1000,
              },
            ],
          })
        );

        if (res.preview) {
          setPreviewState(res.preview);
        }
      }
    } catch (err: any) {
      console.error("Failed to approve plan:", err);
      const errorMessage: ChatMessage = {
        id: `assistant-error-${Date.now()}`,
        role: "assistant",
        text: `Error approving plan: ${err.message || "Network request failed"}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  // Handle Clear Chat
  const handleClearChat = async () => {
    if (!selectedRepo || clearChatMutation.isPending) return;
    try {
      await clearChatMutation.mutateAsync(selectedRepo);
      setMessages([]);
      setIsChatCleared(true);
    } catch (err) {
      console.error("Failed to clear chat:", err);
    }
  };

  // Handle Prompt Submission from Factory Studio
  const handleSendPrompt = async (promptText: string, grill: boolean = true) => {
    if (!selectedRepo || isSendingPrompt || isApproving) return;

    // Support text shortcuts (e.g. /proceed or approve) to trigger build approval directly
    const trimmedLower = promptText.trim().toLowerCase();
    const isShortcut =
      trimmedLower === "/proceed" ||
      trimmedLower === "approve" ||
      trimmedLower === "/approve" ||
      trimmedLower === "proceed";

    if (isShortcut) {
      const readyAssistantMsg = [...messages].reverse().find(
        (m) => m.role === "assistant" && m.grillTurn?.type === "ready_for_approval"
      );
      if (readyAssistantMsg?.grillTurn) {
        const userShortcutMessage: ChatMessage = {
          id: `user-${Date.now()}`,
          role: "user",
          text: promptText,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userShortcutMessage]);
        await handleApprovePlan(readyAssistantMsg.grillTurn);
        return;
      }
    }

    // 1. Append user prompt optimistically
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: promptText,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsChatCleared(false);

    // Sync query cache optimistically
    queryClient.setQueryData<{ repo: string; messages: DbChatMessage[] }>(
      studioQueryKeys.messages(selectedRepo),
      (old) => {
        const oldMsgs = old?.messages || [];
        const newDbMsg: DbChatMessage = {
          id: userMessage.id,
          repo: selectedRepo,
          role: "user",
          content: promptText,
          created_at: userMessage.timestamp / 1000,
        };
        return {
          repo: selectedRepo,
          messages: [...oldMsgs, newDbMsg],
        };
      }
    );

    try {
      const history = messages
        .filter((m) => !m.grillTurn || m.grillTurn.type !== "error")
        .map((m) => ({
          role: m.role,
          text: m.text || m.grillTurn?.formatted_text || m.grillTurn?.summary || "",
        }));

      const res = await sendPromptMutation.mutateAsync({
        repo: selectedRepo,
        prompt: promptText,
        model: "deepseek-v4.1-flash",
        vm: false,
        grill,
        history,
      });

      if (!res.accepted) {
        // Refusal
        const refusalMessage: ChatMessage = {
          id: `assistant-refusal-${Date.now()}`,
          role: "assistant",
          timestamp: Date.now(),
          refusal: {
            message: res.refusal || "Prompt was not accepted by Intent Guard.",
            reason: res.reason || undefined,
            category: res.category || undefined,
          },
        };
        setMessages((prev) => [...prev, refusalMessage]);
        queryClient.setQueryData<{ repo: string; messages: DbChatMessage[] }>(
          studioQueryKeys.messages(selectedRepo),
          (old) => ({
            repo: selectedRepo,
            messages: [
              ...(old?.messages || []),
              {
                id: refusalMessage.id,
                repo: selectedRepo,
                role: "assistant",
                content: refusalMessage.refusal!.message,
                turn_data: { refusal: true, reason: res.reason, category: res.category },
                created_at: refusalMessage.timestamp / 1000,
              },
            ],
          })
        );
      } else if (res.turn) {
        // Conversational Grilling Turn
        const assistantMessage: ChatMessage = {
          id: `assistant-grill-${Date.now()}`,
          role: "assistant",
          timestamp: Date.now(),
          text: res.turn.formatted_text || res.turn.summary || "",
          grillTurn: res.turn,
        };
        setMessages((prev) => [...prev, assistantMessage]);
        queryClient.setQueryData<{ repo: string; messages: DbChatMessage[] }>(
          studioQueryKeys.messages(selectedRepo),
          (old) => ({
            repo: selectedRepo,
            messages: [
              ...(old?.messages || []),
              {
                id: assistantMessage.id,
                repo: selectedRepo,
                role: "assistant",
                content: assistantMessage.text || "",
                turn_data: res.turn,
                created_at: assistantMessage.timestamp / 1000,
              },
            ],
          })
        );
      } else if (res.job) {
        // Accepted & job created (fast build mode)
        clearLogs();
        setActiveJobId(res.job.id);
        setActiveJob(res.job);
        setJobs((prev) => [res.job!, ...prev]);

        const assistantMessage: ChatMessage = {
          id: `assistant-${res.job.id}`,
          role: "assistant",
          timestamp: Date.now(),
          jobId: res.job.id,
          stage: res.job.stage,
          text: `Dispatched assembly line targeting ${res.job.feature || res.job.repo}`,
          thinking: {
            text: "Initializing autonomous agent harness...",
            done: false,
          },
          stepChips: [],
        };
        setMessages((prev) => [...prev, assistantMessage]);
        queryClient.setQueryData<{ repo: string; messages: DbChatMessage[] }>(
          studioQueryKeys.messages(selectedRepo),
          (old) => ({
            repo: selectedRepo,
            messages: [
              ...(old?.messages || []),
              {
                id: assistantMessage.id,
                repo: selectedRepo,
                role: "assistant",
                content: assistantMessage.text || "",
                turn_data: { job_id: res.job!.id },
                created_at: assistantMessage.timestamp / 1000,
              },
            ],
          })
        );

        if (res.preview) {
          setPreviewState(res.preview);
        }
      }
    } catch (err: any) {
      console.error("Failed to send studio prompt:", err);
      const errorMessage: ChatMessage = {
        id: `assistant-error-${Date.now()}`,
        role: "assistant",
        text: `Error dispatching turn: ${err.message || "Network request failed"}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  // Handle Instant Dispatch from Issue Drawer
  const handleInstantDispatch = async (params: {
    repo?: string;
    issue_number?: number | string;
    milestone_slug?: string;
    milestone_title?: string;
    milestone?: string;
  }) => {
    const repo = params.repo || selectedRepo;
    if (!repo || dispatchStudioMutation.isPending) return;

    try {
      const res = await dispatchStudioMutation.mutateAsync({
        repo,
        issue_number: params.issue_number,
        milestone_slug: params.milestone_slug,
        milestone_title: params.milestone_title,
        model: "deepseek-v4.1-flash",
        vm: false,
      });

      if (res.job) {
        clearLogs();
        setActiveJobId(res.job.id);
        setActiveJob(res.job);
        setJobs((prev) => [res.job, ...prev]);

        if (res.preview) {
          setPreviewState(res.preview);
        } else if (res.preview_url) {
          setPreviewState((prev) => ({
            status: "SERVING",
            branch: res.target_branch || res.branch || "main",
            preview_url: res.preview_url!,
            logs: prev?.logs || [],
            error_message: null,
          }));
        }
      }
      return res;
    } catch (err: any) {
      console.error("Failed to dispatch studio job:", err);
      throw err;
    }
  };

  const handleSelectBranch = async (branch: string) => {
    if (!selectedRepo || updateBranchMutation.isPending) return;
    try {
      const res = await updateBranchMutation.mutateAsync({ repo: selectedRepo, branch });
      setPreviewState((prev) =>
        prev
          ? ({
              ...prev,
              branch: res.branch,
              preview_url: res.preview_url !== undefined ? res.preview_url : prev.preview_url,
            } as PreviewState)
          : null
      );
      setPreviewRefreshKey((prev) => prev + 1);
    } catch (err) {
      console.error("Failed to switch preview branch:", err);
      throw err;
    }
  };

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
    isClearingChat: clearChatMutation.isPending,
    isChatCleared,
    onOpenIssueDrawer: () => setIsIssueDrawerOpen(true),
    onCloseIssueDrawer: () => setIsIssueDrawerOpen(false),
    isIssueDrawerOpen,
    onInstantDispatch: handleInstantDispatch,
    isDispatching: dispatchStudioMutation.isPending,
    onMergeSuccess: () => {
      setPreviewState((prev) => {
        if (!prev || prev.status === "IDLE") return prev;
        return { ...prev, branch: "main" };
      });
      setPreviewRefreshKey((prev) => prev + 1);
    },
    branches: branchesQuery.data?.branches || [],
    onSelectBranch: handleSelectBranch,
    isSwitchingBranch: updateBranchMutation.isPending,
  };

  return (
    <StudioProvider value={studioContextValue}>
      <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
        {/* Top Application Header */}
        <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-6 flex items-center justify-between z-30 shrink-0">
          <div className="flex items-center space-x-6">
            {/* Logo & Product Title */}
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-md">
                <Boxes className="w-4 h-4" />
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-sm text-slate-100 tracking-tight leading-none">
                  Software Factory
                </span>
                <span className="text-[10px] text-slate-400 font-mono">v0.9.0-modal</span>
              </div>
            </div>

            {/* Navigation Switcher Tabs */}
            <nav className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                id="nav-tab-studio"
                onClick={() => switchTab("studio")}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  activeTab === "studio"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Factory Studio</span>
              </button>
              <button
                id="nav-tab-console"
                onClick={() => switchTab("console")}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  activeTab === "console"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>Factory Testing Console</span>
              </button>
            </nav>
          </div>

          {/* Header Right Status Indicator */}
          <div className="flex items-center space-x-3 text-xs">
            {activeJob && (
              <div className="flex items-center space-x-2 bg-slate-800/80 px-3 py-1 rounded-full border border-slate-700">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-slate-300 font-mono text-[11px]">{activeJob.stage}</span>
                <span className="text-slate-500">•</span>
                <span className="text-slate-400 truncate max-w-[120px]">
                  {activeJob.feature || activeJob.repo}
                </span>
              </div>
            )}
            <div className="flex items-center space-x-1.5 text-slate-400 font-mono text-[11px] bg-slate-900 px-2.5 py-1 rounded border border-slate-800">
              <GitBranch className="w-3 h-3 text-indigo-400" />
              <span>{selectedRepo || "no-repo"}</span>
            </div>
          </div>
        </header>

        {/* Main Active View */}
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

        {/* Slide-over Agent Activity Drawer */}
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
