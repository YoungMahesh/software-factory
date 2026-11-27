import { z } from "zod";

export const HealthCheckResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "error"]),
  uptime: z.number(),
  timestamp: z.string(),
  environment: z.string(),
  apps_base_domain: z.string().nullable().optional(),
  dashboard_commit: z.string().nullable().optional(),
});
export type HealthCheckResponse = z.infer<typeof HealthCheckResponseSchema>;

export const DashboardDeployTargetSchema = z.enum(["apex", "subdomain"]);
export type DashboardDeployTarget = z.infer<typeof DashboardDeployTargetSchema>;

export const DashboardDeployStatusSchema = z.enum([
  "queued",
  "cloning",
  "deploying",
  "ready",
  "failed",
]);
export type DashboardDeployStatus = z.infer<typeof DashboardDeployStatusSchema>;

export const DashboardDeployRecordSchema = z.object({
  deploy_id: z.string(),
  target: DashboardDeployTargetSchema,
  status: DashboardDeployStatusSchema,
  current_label: z.string(),
  target_url: z.string().nullable().optional().default(null),
  commit_short: z.string().nullable().optional().default(null),
  control_plane_url: z.string().nullable().optional().default(null),
  logs: z.array(z.string()).optional().default([]),
  error: z.string().nullable().optional().default(null),
  created_at: z.string(),
  updated_at: z.string(),
});
export type DashboardDeployRecord = z.infer<typeof DashboardDeployRecordSchema>;

export const DashboardDeployStatusResponseSchema = z.object({
  deploy: DashboardDeployRecordSchema.nullable().optional().default(null),
});
export type DashboardDeployStatusResponse = z.infer<
  typeof DashboardDeployStatusResponseSchema
>;

export const VersionInfoSchema = z.object({
  commit: z.string(),
  commit_short: z.string(),
  ref: z.string(),
  dirty: z.boolean(),
});
export type VersionInfo = z.infer<typeof VersionInfoSchema>;

export const ProfileInfoSchema = z.object({
  name: z.string(),
  active: z.boolean().optional().default(false),
  environment: z.string().optional(),
});
export type ProfileInfo = z.infer<typeof ProfileInfoSchema>;

export const ApiErrorDetailSchema = z.object({
  detail: z.union([
    z.string(),
    z.object({
      code: z.string().optional(),
      message: z.string().optional(),
      snapshot_image_id: z.string().nullable().optional(),
      snapshot_name: z.string().nullable().optional(),
    }),
  ]),
});
export type ApiErrorDetail = z.infer<typeof ApiErrorDetailSchema>;
