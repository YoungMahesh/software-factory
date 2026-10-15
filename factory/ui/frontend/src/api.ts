import {
  Repo,
  ScratchMetadata,
  Milestone,
  Issue,
  Job,
  LaunchJobParams,
  PreviewState,
  GrillTurnResult,
  DraftADR,
  DbChatMessage,
  StudioDispatchParams,
  StudioDispatchResponse,
} from "./types";

export type { StudioDispatchParams, StudioDispatchResponse } from "./types";

export interface StudioPromptResponse {
  accepted: boolean;
  refusal?: string | null;
  reason?: string | null;
  category?: string | null;
  turn?: GrillTurnResult | null;
  job?: Job | null;
  issue?: any | null;
  milestone?: any | null;
  stage?: string | null;
  preview_url?: string | null;
  preview?: PreviewState | null;
  branch?: string | null;
  draft_adr?: DraftADR | null;
}

export async function fetchRepos(): Promise<{ org: string; repos: Repo[] }> {
  const res = await fetch("/api/repos");
  if (!res.ok) throw new Error(`Failed to fetch repos: ${res.statusText}`);
  return res.json();
}

export async function fetchStudioRepos(): Promise<{ org: string; repos: Repo[] }> {
  const res = await fetch("/api/studio/repos");
  if (!res.ok) throw new Error(`Failed to fetch studio repos: ${res.statusText}`);
  return res.json();
}

export async function createRepo(params: {
  name: string;
  description?: string;
  private?: boolean;
}): Promise<Repo> {
  const res = await fetch("/api/studio/repos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create repo: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchScratch(repo: string): Promise<ScratchMetadata> {
  const res = await fetch(`/api/repos/${encodeURIComponent(repo)}/scratch`);
  if (!res.ok) throw new Error(`Failed to fetch scratch: ${res.statusText}`);
  return res.json();
}

export async function fetchMilestones(
  repo: string
): Promise<{ repo: string; milestones: Milestone[] }> {
  const res = await fetch(`/api/repos/${encodeURIComponent(repo)}/milestones`);
  if (!res.ok) throw new Error(`Failed to fetch milestones: ${res.statusText}`);
  return res.json();
}

export async function fetchIssues(
  repo: string,
  milestoneNumber?: number,
  state: string = "all"
): Promise<{ repo: string; org?: string; issues: Issue[] }> {
  const params = new URLSearchParams();
  if (milestoneNumber !== undefined) {
    params.set("milestone", String(milestoneNumber));
  }
  if (state) {
    params.set("state", state);
  }
  const queryStr = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/repos/${encodeURIComponent(repo)}/issues${queryStr}`);
  if (!res.ok) throw new Error(`Failed to fetch issues: ${res.statusText}`);
  return res.json();
}

export async function dispatchStudio(
  params: StudioDispatchParams
): Promise<StudioDispatchResponse> {
  const payload = {
    model: "deepseek-v4.1-flash",
    vm: false,
    ...params,
  };
  const res = await fetch("/api/studio/dispatch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to dispatch: ${res.statusText}`);
  }
  return res.json();
}

export async function launchJob(params: LaunchJobParams): Promise<Job> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to launch job: ${res.statusText}`);
  }
  return res.json();
}

export interface SendStudioPromptParams {
  repo: string;
  prompt: string;
  model?: string;
  vm?: boolean;
  grill?: boolean;
  history?: Array<{ role: string; text?: string }>;
  milestone_title?: string;
}

export async function sendStudioPrompt(
  params: SendStudioPromptParams
): Promise<StudioPromptResponse> {
  const payload = {
    model: "deepseek-v4.1-flash",
    vm: false,
    grill: true,
    history: [],
    ...params,
  };
  const res = await fetch("/api/studio/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to submit prompt: ${res.statusText}`);
  }
  return res.json();
}

export interface ApprovePlanParams {
  repo: string;
  prompt: string;
  milestone_title?: string;
  draft_adr?: DraftADR | null;
  context_update?: string | null;
  model?: string;
  vm?: boolean;
}

export async function approvePlan(
  params: ApprovePlanParams
): Promise<StudioPromptResponse> {
  const payload = {
    model: "deepseek-v4.1-flash",
    vm: false,
    ...params,
  };
  const res = await fetch("/api/studio/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to approve plan: ${res.statusText}`);
  }
  return res.json();
}

export async function listJobs(): Promise<{ jobs: Job[] }> {
  const res = await fetch("/api/jobs");
  if (!res.ok) throw new Error(`Failed to list jobs: ${res.statusText}`);
  return res.json();
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) throw new Error(`Failed to fetch job ${jobId}: ${res.statusText}`);
  return res.json();
}

export async function cancelJob(jobId: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel job: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchPreview(repo: string): Promise<PreviewState> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/preview`);
  if (!res.ok) throw new Error(`Failed to fetch preview: ${res.statusText}`);
  return res.json();
}

export async function launchPreview(
  repo: string,
  branch?: string
): Promise<PreviewState> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to launch preview: ${res.statusText}`);
  }
  return res.json();
}

export async function stopPreview(
  repo: string
): Promise<{ success: boolean; message: string; repo?: string }> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/preview`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to stop preview: ${res.statusText}`);
  }
  return res.json();
}

export function getPreviewStreamUrl(repo: string): string {
  return `/api/studio/repos/${encodeURIComponent(repo)}/preview/stream`;
}

export interface PreviewSyncResult {
  success: boolean;
  branch: string;
  commit?: string | null;
  updated: boolean;
  message?: string;
}

export async function syncPreview(
  repo: string,
  branch?: string
): Promise<PreviewSyncResult> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/preview/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to synchronize preview: ${res.statusText}`);
  }
  return res.json();
}

export interface PreviewBranchResult {
  success: boolean;
  branch: string;
  commit?: string | null;
  updated: boolean;
}

export async function switchPreviewBranch(
  repo: string,
  branch: string
): Promise<PreviewBranchResult> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/preview/branch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to switch preview branch: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchRepoBranches(
  repo: string
): Promise<{ repo: string; branches: string[] }> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/branches`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch branches: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchChatMessages(
  repo: string
): Promise<{ repo: string; messages: DbChatMessage[] }> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/messages`);
  if (!res.ok) throw new Error(`Failed to fetch chat messages: ${res.statusText}`);
  return res.json();
}

export async function clearChatMessages(
  repo: string
): Promise<{ repo: string; deleted: number; success: boolean }> {
  const res = await fetch(`/api/studio/repos/${encodeURIComponent(repo)}/messages`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to clear chat messages: ${res.statusText}`);
  }
  return res.json();
}

