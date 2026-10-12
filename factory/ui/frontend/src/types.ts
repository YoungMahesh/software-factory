export type JobStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED";

export type PreviewStatus = "IDLE" | "PROVISIONING" | "SERVING" | "STOPPED" | "FAILED";

export type PreviewStage =
  | "IDLE"
  | "PROVISIONING"
  | "INSTALLING_DEPS"
  | "STARTING_DEV"
  | "SERVING";

export type PreviewState =
  | { status: "IDLE"; branch: null; preview_url: null; logs: string[]; error_message: null }
  | { status: "PROVISIONING"; stage: PreviewStage; branch: string; preview_url: null; logs: string[]; error_message: null }
  | { status: "SERVING"; preview_url: string; branch: string; logs: string[]; error_message: null }
  | { status: "STOPPED"; branch: string; preview_url: null; logs: string[]; error_message: null }
  | { status: "FAILED"; branch: string | null; preview_url: null; logs: string[]; error_message: string };

export type JobStage =
  | "IDLE"
  | "PREFLIGHT"
  | "PLANNER"
  | "CODER"
  | "VERIFIER"
  | "REVIEWER"
  | "COMPLETED"
  | "SERVING";

export interface Repo {
  name: string;
  description?: string | null;
  html_url?: string;
  is_tanstack_compatible?: boolean;
  private?: boolean;
}

export interface IssueMilestone {
  number?: number;
  title: string;
  slug?: string;
}

export interface Issue {
  id?: number | string;
  number: number | string;
  title: string;
  status: "ready-for-agent" | "claimed" | "ready-for-human" | "resolved" | string;
  blocked_by: string[];
  labels?: string[];
  body?: string;
  state?: "open" | "closed" | string;
  milestone?: IssueMilestone | null;
  html_url?: string;
}

export interface Milestone {
  number: number;
  title: string;
  description?: string;
  issues: Issue[];
}

export interface StudioDispatchParams {
  repo: string;
  issue_number?: number | string;
  milestone_slug?: string;
  milestone_title?: string;
  model?: string;
  vm?: boolean;
}

export interface StudioDispatchResponse {
  accepted: boolean;
  job: Job;
  issue_number?: number | string | null;
  milestone_slug?: string | null;
  branch: string;
  target_branch: string;
  preview_url?: string | null;
  preview?: PreviewState | null;
  stage: string;
}

export interface ScratchFeature {
  slug: string;
  issues: Array<{ id: string; title?: string }>;
}

export interface ScratchMetadata {
  repo: string;
  has_scratch: boolean;
  features: ScratchFeature[];
}

export interface LaunchJobParams {
  repo: string;
  feature?: string;
  issue?: string;
  model: string;
  vm: boolean;
  dev: boolean;
}

export interface Job {
  id: string;
  repo: string;
  feature?: string;
  issue?: string | null;
  model: string;
  vm: boolean;
  dev: boolean;
  preview_url?: string | null;
  status: JobStatus;
  stage: JobStage;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration?: number | null;
  log_count: number;
  event_count: number;
  logs?: string[];
  events?: AgentEvent[];
}

export interface AgentEvent {
  type: "thinking" | "tool_start" | "tool_result" | "stage" | "reviewer_rejection" | "attempt_start" | string;
  stage?: string;
  timestamp?: number;
  data: any;
}

export interface GrillQuestion {
  id: string;
  title: string;
  question: string;
  recommended: string;
  options?: string[];
}

export interface DraftADR {
  title: string;
  filename: string;
  content: string;
}

export interface DomainTermSharpening {
  fuzzy_term: string;
  canonical_term: string;
  explanation: string;
}

export interface GrillTurnResult {
  type: "grill_round" | "ready_for_approval" | "error";
  round: number;
  questions: GrillQuestion[];
  formatted_text?: string;
  summary?: string;
  plan?: string | null;
  draft_adr?: DraftADR | null;
  sharpened_terms?: DomainTermSharpening[];
  context_update?: string | null;
  error_message?: string | null;
  error_details?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  timestamp: number;
  jobId?: string;
  stage?: JobStage | string;
  thinking?: {
    text: string;
    durationMs?: number;
    done: boolean;
  };
  stepChips?: Array<{
    id: string;
    toolName: string;
    label: string;
    data: any;
    stage?: string;
    toolCallId?: string;
  }>;
  refusal?: {
    message: string;
    reason?: string;
    category?: string;
  };
  grillTurn?: GrillTurnResult;
}

export interface DbChatMessage {
  id: string;
  repo: string;
  milestone_slug?: string | null;
  issue_number?: number | null;
  role: "user" | "assistant";
  content: string;
  turn_data?: any;
  draft_adr?: DraftADR | null;
  created_at: number;
}

export type ViewportMode = "desktop" | "tablet" | "mobile";

