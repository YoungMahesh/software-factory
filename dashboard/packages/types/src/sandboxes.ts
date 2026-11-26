import { z } from "zod";

export const SandboxSummarySchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  running: z.boolean(),
  exit_code: z.number().int().nullable().optional(),
  app_name: z.string().nullable().optional(),
  profile: z.string().nullable().optional(),
  ssh_command: z.string().nullable().optional(),
  ssh_config: z.string().nullable().optional(),
  t3_pair_url: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  timeout_secs: z.number().nullable().optional(),
});
export type SandboxSummary = z.infer<typeof SandboxSummarySchema>;

export const SnapshotSummarySchema = z.object({
  image_id: z.string(),
  sandbox_id: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  ttl_days: z.number().int().nullable().optional(),
  ttl_seconds: z.number().int().nullable().optional(),
  is_vm: z.boolean().optional().default(false),
  profile: z.string().nullable().optional(),
  software_factory_commit: z.string().nullable().optional(),
  software_factory_dirty: z.string().nullable().optional(),
});
export type SnapshotSummary = z.infer<typeof SnapshotSummarySchema>;

export const FreshSandboxLaunchPayloadSchema = z.object({
  mode: z.enum(["repo", "standalone"]).default("repo"),
  repo: z.string().nullable().optional(),
  github_branch: z.string().default("main"),
  testing: z.boolean().default(false),
  full_clone: z.boolean().default(false),
  name: z.string().nullable().optional(),
  profile: z.string().nullable().optional(),
  vm: z.boolean().default(false),
  memory: z.number().int().nullable().optional(),
  no_cloudflare: z.boolean().default(false),
  t3: z.boolean().default(true),
  modal: z.boolean().default(true),
  sops: z.boolean().default(true),
  browser: z.boolean().optional(),
  react_native: z.boolean().optional(),
});
export type FreshSandboxLaunchPayload = z.infer<typeof FreshSandboxLaunchPayloadSchema>;

export const SnapshotCreatePayloadSchema = z.object({
  name: z.string().default(""),
  ttl_days: z.number().int().min(1).max(365).default(30),
  terminate: z.boolean().default(false),
  profile: z.string().nullable().optional(),
  timeout: z.number().int().min(10).max(600).default(180),
});
export type SnapshotCreatePayload = z.infer<typeof SnapshotCreatePayloadSchema>;

export const SnapshotLaunchPayloadSchema = z.object({
  name: z.string().default("resumed-sandbox"),
  vm: z.boolean().default(false),
  memory: z.number().int().nullable().optional(),
  no_cloudflare: z.boolean().optional(),
  t3: z.boolean().default(true),
  modal: z.boolean().default(true),
  sops: z.boolean().default(true),
  profile: z.string().nullable().optional(),
});
export type SnapshotLaunchPayload = z.infer<typeof SnapshotLaunchPayloadSchema>;

export const LaunchResponseSchema = z.object({
  sandbox_id: z.string(),
  app_name: z.string(),
  sandbox_name: z.string(),
  ssh_info: z.tuple([z.string(), z.number().int()]).nullable().optional(),
  ssh_command: z.string().nullable().optional(),
  ssh_config: z.string().nullable().optional(),
  metro_url: z.string().nullable().optional(),
  metro_port: z.number().int().nullable().optional(),
  t3_url: z.string().nullable().optional(),
  t3_port: z.number().int().nullable().optional(),
  t3_pair_url: z.string().nullable().optional(),
  t3_qr_code: z.string().nullable().optional(),
  t3_ssh_host: z.string().nullable().optional(),
  codex_profile: z.string().nullable().optional(),
  t3_persist: z.boolean().optional().default(false),
  t3_usage_volume: z.string().nullable().optional(),
  xfce_url: z.string().nullable().optional(),
  xfce_port: z.number().int().nullable().optional(),
  xfce_password: z.string().nullable().optional(),
  memory_gb: z.number().int().nullable().optional(),
  cloudflare_enabled: z.boolean().optional().default(true),
  sops_enabled: z.boolean().optional().default(false),
  is_vm: z.boolean().optional().default(false),
});
export type LaunchResponse = z.infer<typeof LaunchResponseSchema>;

export const SnapshotResponseSchema = z.object({
  sandbox_id: z.string(),
  image_id: z.string(),
  ttl_days: z.number().int(),
  ttl_seconds: z.number().int(),
  terminated: z.boolean(),
});
export type SnapshotResponse = z.infer<typeof SnapshotResponseSchema>;

export const FreshLaunchStreamEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("log"), message: z.string() }),
  z.object({ type: z.literal("done"), response: LaunchResponseSchema }),
  z.object({ type: z.literal("error"), detail: z.string() }),
]);
export type FreshLaunchStreamEvent = z.infer<typeof FreshLaunchStreamEventSchema>;
