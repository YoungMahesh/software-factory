import { z } from "zod";

export const HealthCheckResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "error"]),
  uptime: z.number(),
  timestamp: z.string(),
  environment: z.string(),
});
export type HealthCheckResponse = z.infer<typeof HealthCheckResponseSchema>;

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
