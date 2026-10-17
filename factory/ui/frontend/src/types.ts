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

export type PullRequestStatus =
  | "draft"
  | "ready_for_review"
  | "merged"
  | "conflict"
  | "closed"
  | string;

export interface PullRequest {
  id?: number;
  number: number;
  title: string;
  body?: string;
  state: "open" | "closed" | string;
  status: PullRequestStatus;
  draft: boolean;
  merged: boolean;
  mergeable?: boolean | null;
  mergeable_state?: string | null;
  head_branch: string;
  base_branch: string;
  html_url: string;
  created_at?: string | null;
  updated_at?: string | null;
  merged_at?: string | null;
  closed_at?: string | null;
}

export interface MergePullRequestParams {
  commit_title?: string;
  commit_message?: string;
}

export interface MergePullRequestResponse {
  accepted: boolean;
  merged: boolean;
  result?: {
    sha?: string;
    branch?: string;
    pull_number?: number;
    branch_deleted?: boolean;
    commit_title?: string;
    commit_message?: string;
    message?: string;
  };
  preview_synced?: boolean;
}

export interface DeliveryGateData {
  phase?: "init" | "finalized" | string;
  pull_number?: number;
  pull_request_number?: number;
  pullRequestNumber?: number;
  pull_request?: PullRequest;
  resolved_issues?: Array<string | number>;
  test_verdict?: string;
  status?: string;
  draft?: boolean;
  ready_for_review?: boolean;
  merged?: boolean;
  sha?: string;
  branch?: string;
  commit_title?: string;
  commit_message?: string;
  preview_synced?: boolean;
  result?: any;
  reverted?: boolean;
  reverted_at?: number;
  revert_commit?: string;
}

export interface MarkPullRequestReadyResponse {
  success: boolean;
  ready_for_review: boolean;
  pull_number: number;
  pull: PullRequest;
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
  turn_data?: any;
  deliveryGate?: DeliveryGateData;
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

export interface TurnRollbackData {
  type: "turn_rollback";
  original_message_id?: string | null;
  original_commit_sha?: string | null;
  revert_commit_sha?: string | null;
  issue_number?: number | string | null;
  branch?: string | null;
  [key: string]: any;
}

export interface RollbackTurnParams {
  repo: string;
  message_id?: string | null;
  branch?: string | null;
}

export interface RollbackTurnResponse {
  success: boolean;
  branch: string;
  original_commit: string;
  revert_commit: string;
  issue_number?: number | string | null;
  message: string;
}

export interface RollbackTarget {
  messageId?: string;
  branch?: string;
  commitSha?: string | null;
  issueNumber?: number | string | null;
  issueTitle?: string | null;
}

export interface FailedCommand {
  id: string;
  command: string;
  cwd?: string;
  stage: string;
  exitCode: number;
  exit_code?: number;
  durationMs?: number;
  duration_ms?: number;
  stdout?: string;
  stderr?: string;
  output?: string;
  isError?: boolean;
  is_error?: boolean;
  timestamp?: number;
}

export type DrawerTab = "timeline" | "logs" | "bottlenecks" | "failed-commands" | "history";
export type DrawerTabParam = DrawerTab | "failed_commands";
export type ActivityDrawerTab = DrawerTab;

export interface RepoBottleneck {
  command: string;
  category: string;
  stage?: string;
  count: number;
  invocation_count?: number;
  total_duration_ms: number;
  total_time?: number;
  avg_duration_ms: number;
  avg_time?: number;
  max_duration_ms: number;
  max_time?: number;
}

export interface RepoBottlenecksResponse {
  repo: string;
  bottlenecks: RepoBottleneck[];
}


