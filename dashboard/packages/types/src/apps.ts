import { z } from "zod";

export const AppTemplateKindSchema = z.enum(["nextjs", "blank"]);
export type AppTemplateKind = z.infer<typeof AppTemplateKindSchema>;

export const LaunchStatusSchema = z.enum([
  "queued",
  "launching_sandbox",
  "scaffolding_workspace",
  "waiting_t3",
  "starting_thread",
  "ready",
  "failed",
]);
export type LaunchStatus = z.infer<typeof LaunchStatusSchema>;

export const AppRuntimeStatusSchema = z.enum([
  "provisioning",
  "running",
  "stopped",
  "failed",
]);
export type AppRuntimeStatus = z.infer<typeof AppRuntimeStatusSchema>;

export const ModelOptionSchema = z.object({
  id: z.string(),
  label: z.string(),
});
export type ModelOption = z.infer<typeof ModelOptionSchema>;

export const ModelChoiceSchema = z.object({
  provider: z.string(),
  model: z.string(),
  label: z.string(),
  is_default: z.boolean().optional().default(false),
  thought_levels: z.array(ModelOptionSchema).optional().default([]),
  default_thought_level: z.string().nullable().optional(),
});
export type ModelChoice = z.infer<typeof ModelChoiceSchema>;

export const CachedGitHubRepoSchema = z.object({
  full_name: z.string(),
  name: z.string(),
  owner: z.string(),
  private: z.boolean().optional().default(false),
  default_branch: z.string().optional().default("main"),
  description: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  html_url: z.string().nullable().optional(),
});
export type CachedGitHubRepo = z.infer<typeof CachedGitHubRepoSchema>;

export const RepositoryCatalogCacheSchema = z.object({
  org: z.string().nullable().optional(),
  refreshed_at: z.string().nullable().optional(),
  repos: z.array(CachedGitHubRepoSchema).optional().default([]),
});
export type RepositoryCatalogCache = z.infer<typeof RepositoryCatalogCacheSchema>;

export const LaunchStepSchema = z.object({
  key: LaunchStatusSchema,
  label: z.string(),
  status: z.enum(["pending", "active", "done", "error"]),
});
export type LaunchStep = z.infer<typeof LaunchStepSchema>;

export const CreateAppPayloadSchema = z.object({
  prompt: z.string().default(""),
  name: z.string().nullable().optional(),
  repo: z.string().nullable().optional(),
  branch: z.string().nullable().optional(),
  template: AppTemplateKindSchema.default("nextjs"),
  web_app: z.boolean().nullable().optional(),
  mobile_app: z.boolean().default(false),
  vm: z.boolean().default(true),
  memory: z.number().int().nullable().optional().default(1),
  testing: z.boolean().optional().default(false),
  full_clone: z.boolean().optional().default(false),
  t3: z.boolean().optional().default(true),
  no_t3_persist: z.boolean().optional().default(false),
  t3_usage_volume: z.string().optional().default("t3code-usage-v1"),
  t3_port: z.number().int().optional().default(3775),
  t3_ssh_host: z.string().nullable().optional(),
  metro_port: z.number().int().optional().default(8081),
  modal: z.boolean().optional().default(true),
  sops: z.boolean().optional().default(true),
  browser: z.boolean().optional().default(false),
  react_native: z.boolean().optional().default(false),
  no_cloudflare: z.boolean().optional().default(true),
  xfce: z.boolean().optional().default(false),
  xfce_port: z.number().int().optional().default(3000),
  xfce_password: z.string().nullable().optional(),
  profile: z.string().nullable().optional(),
  provider: z.string().default("antigravity"),
  model: z.string().default("gemini-4-hydrogen"),
  thought_level: z.string().nullable().optional(),
});
export type CreateAppPayload = z.infer<typeof CreateAppPayloadSchema>;

export const FactoryAppRecordSchema = z.object({
  app_id: z.string(),
  slug: z.string(),
  title: z.string(),
  prompt: z.string().optional().default(""),
  repo: z.string().nullable().optional(),
  branch: z.string().nullable().optional(),
  worktree_branch: z.string().nullable().optional(),
  workspace_path: z.string().nullable().optional(),
  repo_base_path: z.string().nullable().optional(),
  template: AppTemplateKindSchema.optional().default("nextjs"),
  web_app: z.boolean().optional().default(true),
  mobile_app: z.boolean().optional().default(false),
  vm: z.boolean().optional().default(true),
  memory: z.number().int().nullable().optional(),
  testing: z.boolean().optional().default(false),
  full_clone: z.boolean().optional().default(false),
  t3: z.boolean().optional().default(true),
  no_t3_persist: z.boolean().optional().default(false),
  t3_usage_volume: z.string().optional(),
  t3_port: z.number().int().optional(),
  t3_ssh_host: z.string().nullable().optional(),
  metro_port: z.number().int().optional(),
  modal: z.boolean().optional().default(true),
  sops: z.boolean().optional().default(true),
  browser: z.boolean().optional().default(false),
  react_native: z.boolean().optional().default(false),
  no_cloudflare: z.boolean().optional().default(true),
  xfce: z.boolean().optional().default(false),
  xfce_port: z.number().int().optional(),
  xfce_password: z.string().nullable().optional(),
  profile: z.string().nullable().optional(),
  provider_instance_id: z.string().nullable().optional(),
  provider: z.string().optional().default("antigravity"),
  model: z.string().optional().default("gemini-4-hydrogen"),
  thought_level: z.string().nullable().optional(),
  status: z.enum(["provisioning", "ready", "failed"]),
  latest_request_id: z.string().nullable().optional(),
  failed_step: LaunchStatusSchema.nullable().optional(),
  workspace_ready: z.boolean().optional().default(false),
  sandbox_id: z.string().nullable().optional(),
  sandbox_name: z.string().nullable().optional(),
  environment_id: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
  thread_id: z.string().nullable().optional(),
  t3_url: z.string().nullable().optional(),
  chat_url: z.string().nullable().optional(),
  database_name: z.string().nullable().optional(),
  dev_port: z.number().int().nullable().optional(),
  prime_key: z.string().nullable().optional(),
  last_error: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type FactoryAppRecord = z.infer<typeof FactoryAppRecordSchema>;

export const FactoryAppViewSchema = FactoryAppRecordSchema.extend({
  runtime_status: AppRuntimeStatusSchema.optional().default("provisioning"),
  snapshot_image_id: z.string().nullable().optional(),
  snapshot_name: z.string().nullable().optional(),
});
export type FactoryAppView = z.infer<typeof FactoryAppViewSchema>;

export const PrimeSandboxViewSchema = z.object({
  prime_key: z.string(),
  profile: z.string().nullable().optional(),
  vm: z.boolean().optional().default(false),
  mobile_app: z.boolean().optional().default(false),
  status: z.enum(["provisioning", "ready", "failed", "stopped"]),
  owner_request_id: z.string().nullable().optional(),
  sandbox_id: z.string().nullable().optional(),
  sandbox_name: z.string().nullable().optional(),
  t3_url: z.string().nullable().optional(),
  environment_id: z.string().nullable().optional(),
  next_port: z.number().int().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  runtime_status: AppRuntimeStatusSchema.optional().default("provisioning"),
  app_count: z.number().int().optional().default(0),
  app_ids: z.array(z.string()).optional().default([]),
});
export type PrimeSandboxView = z.infer<typeof PrimeSandboxViewSchema>;

export const LaunchRequestRecordSchema = z.object({
  request_id: z.string(),
  app_id: z.string(),
  kind: z.enum(["create", "relaunch"]).optional().default("create"),
  resume_from_step: LaunchStatusSchema.nullable().optional(),
  execution_started_at: z.string().nullable().optional(),
  created_sandbox_id: z.string().nullable().optional(),
  published_sandbox_id: z.string().nullable().optional(),
  failed_step: LaunchStatusSchema.nullable().optional(),
  status: LaunchStatusSchema,
  current_label: z.string(),
  steps: z.array(LaunchStepSchema).optional().default([]),
  logs: z.array(z.string()).optional().default([]),
  handoff_url: z.string().nullable().optional(),
  handoff_expires_at: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type LaunchRequestRecord = z.infer<typeof LaunchRequestRecordSchema>;

export const LaunchStatusResponseSchema = z.object({
  request: LaunchRequestRecordSchema,
  app: FactoryAppRecordSchema.nullable().optional(),
});
export type LaunchStatusResponse = z.infer<typeof LaunchStatusResponseSchema>;

export const LaunchAcceptedResponseSchema = z.object({
  app_id: z.string(),
  request_id: z.string(),
  status_url: z.string(),
  app: FactoryAppRecordSchema,
  request: LaunchRequestRecordSchema,
});
export type LaunchAcceptedResponse = z.infer<typeof LaunchAcceptedResponseSchema>;

export const OpenAppResponseSchema = z.object({
  app_id: z.string(),
  handoff_url: z.string(),
  chat_url: z.string(),
});
export type OpenAppResponse = z.infer<typeof OpenAppResponseSchema>;
