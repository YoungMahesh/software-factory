import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../api";
import { LaunchJobParams, Repo, PreviewState } from "../types";

export const studioQueryKeys = {
  repos: ["studio", "repos"] as const,
  preview: (repo: string) => ["studio", "preview", repo] as const,
  scratch: (repo: string) => ["studio", "scratch", repo] as const,
  milestones: (repo: string) => ["studio", "milestones", repo] as const,
  jobs: ["studio", "jobs"] as const,
};

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

export function useJobsQuery() {
  return useQuery({
    queryKey: studioQueryKeys.jobs,
    queryFn: () => api.listJobs(),
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
        (prev) =>
          prev
            ? {
                ...prev,
                status: "STOPPED",
                branch: prev.branch || "main",
                preview_url: null,
                error_message: null,
              }
            : null
      );
    },
  });
}

export function useSendStudioPromptMutation() {
  return useMutation({
    mutationFn: (params: { repo: string; prompt: string; model: string; vm: boolean }) =>
      api.sendStudioPrompt(params),
  });
}

export function useLaunchJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: LaunchJobParams) => api.launchJob(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.jobs });
    },
  });
}

export function useCancelJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studioQueryKeys.jobs });
    },
  });
}
