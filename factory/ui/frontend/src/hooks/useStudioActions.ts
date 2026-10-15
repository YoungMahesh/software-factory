import { useQueryClient } from "@tanstack/react-query";
import {
  Job,
  ChatMessage,
  PreviewState,
  GrillTurnResult,
  DbChatMessage,
} from "../types";
import {
  useCreateRepoMutation,
  useLaunchPreviewMutation,
  useStopPreviewMutation,
  useSendStudioPromptMutation,
  useApprovePlanMutation,
  useClearChatMessagesMutation,
  useDispatchStudioMutation,
  useUpdatePreviewBranchMutation,
  studioQueryKeys,
  createStoppedPreviewState,
} from "./useStudioQueries";

export interface UseStudioActionsParams {
  selectedRepo: string;
  setSelectedRepo: React.Dispatch<React.SetStateAction<string>>;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  activeJob: Job | null;
  setActiveJob: React.Dispatch<React.SetStateAction<Job | null>>;
  setActiveJobId: React.Dispatch<React.SetStateAction<string | null>>;
  setJobs: React.Dispatch<React.SetStateAction<Job[]>>;
  previewState: PreviewState | null;
  setPreviewState: React.Dispatch<React.SetStateAction<PreviewState | null>>;
  setPreviewRefreshKey: React.Dispatch<React.SetStateAction<number>>;
  setIsChatCleared: React.Dispatch<React.SetStateAction<boolean>>;
  clearLogs: () => void;
}

export function useStudioActions({
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
}: UseStudioActionsParams) {
  const queryClient = useQueryClient();

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
  const isClearingChat = clearChatMutation.isPending;
  const isDispatching = dispatchStudioMutation.isPending;
  const isSwitchingBranch = updateBranchMutation.isPending;

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

  const handleCreateRepo = async (params: { name: string; description?: string; private?: boolean }) => {
    const newRepo = await createRepoMutation.mutateAsync(params);
    setSelectedRepo(newRepo.name);
  };

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

  return {
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
  };
}
