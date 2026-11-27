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

export const T3PairingLinkStatusSchema = z.enum(["active", "used", "expired"]);
export type T3PairingLinkStatus = z.infer<typeof T3PairingLinkStatusSchema>;

export const T3PairingLinkEntrySchema = z.object({
  id: z.string().nullable().optional(),
  url: z.string(),
  status: T3PairingLinkStatusSchema,
  label: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  expires_at: z.string().nullable().optional(),
});
export type T3PairingLinkEntry = z.infer<typeof T3PairingLinkEntrySchema>;

export const SandboxT3LinksResponseSchema = z.object({
  sandbox_id: z.string(),
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  t3_url: z.string().nullable().optional(),
  links: z.array(T3PairingLinkEntrySchema).default([]),
});
export type SandboxT3LinksResponse = z.infer<typeof SandboxT3LinksResponseSchema>;

export const SandboxCostSchema = z.object({
  sandbox_id: z.string(),
  profile: z.string().nullable().optional(),
  cost_usd: z.number().nullable(),
  cost_by_resource_usd: z.record(z.string(), z.number()).optional().default({}),
  duration_seconds: z.number().nullable().optional(),
  billed_cpu_core_seconds: z.number().nullable().optional(),
  billed_memory_gib_seconds: z.number().nullable().optional(),
  since: z.string().nullable().optional(),
  until: z.string().nullable().optional(),
  source: z.enum(["sandbox_stats", "app_stats", "unavailable"]).optional().default("unavailable"),
  cached: z.boolean().optional().default(false),
  error: z.string().nullable().optional(),
});
export type SandboxCost = z.infer<typeof SandboxCostSchema>;

export const SandboxCostsResponseSchema = z.object({
  fetched_at: z.string(),
  costs: z.record(z.string(), SandboxCostSchema).optional().default({}),
});
export type SandboxCostsResponse = z.infer<typeof SandboxCostsResponseSchema>;

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
  rootfs_bytes: z.number().int().nullable().optional(),
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
  vm: z.boolean().default(true),
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
  rootfs_bytes: z.number().int().nullable().optional(),
});
export type SnapshotResponse = z.infer<typeof SnapshotResponseSchema>;

export const FreshLaunchStreamEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("log"), message: z.string() }),
  z.object({ type: z.literal("done"), response: LaunchResponseSchema }),
  z.object({ type: z.literal("error"), detail: z.string() }),
]);
export type FreshLaunchStreamEvent = z.infer<typeof FreshLaunchStreamEventSchema>;
