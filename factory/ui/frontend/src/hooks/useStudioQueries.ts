import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../api";
import { Repo, PreviewState } from "../types";

export const studioQueryKeys = {
  repos: ["studio", "repos"] as const,
  preview: (repo: string) => ["studio", "preview", repo] as const,
  branches: (repo: string) => ["studio", "branches", repo] as const,
  scratch: (repo: string) => ["studio", "scratch", repo] as const,
  milestones: (repo: string) => ["studio", "milestones", repo] as const,
  issues: (repo: string) => ["studio", "issues", repo] as const,
  messages: (repo: string) => ["studio", "messages", repo] as const,
  pullRequests: (repo: string) => ["studio", "pullRequests", repo] as const,
};

export function createStoppedPreviewState(prev: PreviewState): PreviewState {
  return {
    status: "STOPPED",
    branch: prev.branch || "main",
    preview_url: null,
    logs: prev.logs || [],
    error_message: null,
  };
}

export function useStudioRepos() {
  return useQuery({
    queryKey: studioQueryKeys.repos,
    queryFn: () => api.fetchStudioRepos(),
  });
}

export function usePreviewQuery(repo: string) {
  return useQuery({
    queryKey: studioQueryKeys.preview(repo),
    queryFn: () => api.fetchPreview(repo),
    enabled: Boolean(repo),
  });
}

export function useScratchQuery(repo: string) {
  return useQuery({
    queryKey: studioQueryKeys.scratch(repo),
    queryFn: () => api.fetchScratch(repo),
    enabled: Boolean(repo),
  });
}

export function useMilestonesQuery(repo: string) {
  return useQuery({
    queryKey: studioQueryKeys.milestones(repo),
    queryFn: () => api.fetchMilestones(repo),
    enabled: Boolean(repo),
  });
}

export function useCreateRepoMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { name: string; description?: string; private?: boolean }) =>
      api.createRepo(params),
    onSuccess: (newRepo: Repo) => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.repos });
      return newRepo;
    },
  });
}

export function useLaunchPreviewMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ repo, branch }: { repo: string; branch?: string }) =>
      api.launchPreview(repo, branch),
    onSuccess: (data: PreviewState, vars) => {
      queryClient.setQueryData(studioQueryKeys.preview(vars.repo), data);
    },
  });
}

export function useStopPreviewMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repo: string) => api.stopPreview(repo),
    onSuccess: (_, repo) => {
      queryClient.setQueryData<PreviewState | null>(
        studioQueryKeys.preview(repo),
        (prev) => (prev ? createStoppedPreviewState(prev) : null)
      );
    },
  });
}

export function useSendStudioPromptMutation() {
  return useMutation({
    mutationFn: (params: api.SendStudioPromptParams) =>
      api.sendStudioPrompt(params),
  });
}

export function useApprovePlanMutation() {
  return useMutation({
    mutationFn: (params: api.ApprovePlanParams) =>
      api.approvePlan(params),
  });
}

export function useChatMessagesQuery(repo: string) {
  return useQuery({
    queryKey: studioQueryKeys.messages(repo),
    queryFn: () => api.fetchChatMessages(repo),
    enabled: Boolean(repo),
  });
}

export function useClearChatMessagesMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repo: string) => api.clearChatMessages(repo),
    onSuccess: (_, repo) => {
      queryClient.setQueryData(studioQueryKeys.messages(repo), { repo, messages: [] });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.messages(repo) });
    },
  });
}

export function useStudioIssuesQuery(repo: string, state: string = "all") {
  return useQuery({
    queryKey: studioQueryKeys.issues(repo),
    queryFn: () => api.fetchIssues(repo, undefined, state),
    enabled: Boolean(repo),
    staleTime: 30_000,
  });
}

export function useDispatchStudioMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: api.StudioDispatchParams) => api.dispatchStudio(params),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.messages(vars.repo) });
      if (vars.repo) {
        queryClient.invalidateQueries({ queryKey: studioQueryKeys.preview(vars.repo) });
      }
    },
  });
}

export function useStudioPullRequestQuery(
  repo: string,
  branch?: string,
  state: string = "all"
) {
  return useQuery({
    queryKey: branch ? [...studioQueryKeys.pullRequests(repo), branch, state] : studioQueryKeys.pullRequests(repo),
    queryFn: () => api.fetchPullRequests(repo, branch, state),
    enabled: Boolean(repo),
  });
}

export function useMergePullRequestMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      repo,
      pullNumber,
      params,
    }: {
      repo: string;
      pullNumber: number;
      params?: api.MergePullRequestParams;
    }) => api.mergePullRequest(repo, pullNumber, params),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.pullRequests(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.messages(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.preview(vars.repo) });
    },
  });
}

export function useRepoBranchesQuery(repo: string) {
  return useQuery({
    queryKey: studioQueryKeys.branches(repo),
    queryFn: () => api.fetchRepoBranches(repo),
    enabled: Boolean(repo),
    staleTime: 30_000,
  });
}

export function useUpdatePreviewBranchMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ repo, branch }: { repo: string; branch: string }) =>
      api.updatePreviewBranch(repo, branch),
    onSuccess: (data, vars) => {
      queryClient.setQueryData<PreviewState | null>(
        studioQueryKeys.preview(vars.repo),
        (prev) => {
          if (!prev) {
            return data.status === "SERVING" && data.preview_url
              ? {
                  status: "SERVING",
                  branch: data.branch,
                  preview_url: data.preview_url,
                  logs: [],
                  error_message: null,
                }
              : {
                  status: "IDLE",
                  branch: null,
                  preview_url: null,
                  logs: [],
                  error_message: null,
                };
          }
          if (prev.status === "SERVING") {
            return {
              ...prev,
              branch: data.branch,
              preview_url: data.preview_url || prev.preview_url,
            };
          }
          return {
            ...prev,
            branch: data.branch,
          } as PreviewState;
        }
      );
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.branches(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.preview(vars.repo) });
    },
  });
}

export function useRollbackTurnMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: api.RollbackTurnParams) => api.rollbackTurn(params),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.messages(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.issues(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.pullRequests(vars.repo) });
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.preview(vars.repo) });
    },
  });
}

