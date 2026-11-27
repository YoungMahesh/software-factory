import { z } from "zod";

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
  target: z.literal("apex").default("apex"),
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

export interface DeployerStatusPayload {
  apps_base_domain: string | null;
  target_url: string | null;
  deployer_commit: string | null;
  control_plane_configured: boolean;
  control_plane_error: string | null;
  control_plane_version: VersionInfo | null;
  live_dashboard_commit: string | null;
  live_dashboard_reachable: boolean;
  latest_deploy: DashboardDeployRecord | null;
}

export function isActiveDashboardDeploy(
  deploy: DashboardDeployRecord | null | undefined,
): boolean {
  if (!deploy) return false;
  return deploy.status === "queued" || deploy.status === "cloning" || deploy.status === "deploying";
}

export async function extractApiError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown; message?: string };
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
    if (
      data.detail &&
      typeof data.detail === "object" &&
      "message" in data.detail &&
      typeof (data.detail as { message?: unknown }).message === "string"
    ) {
      return (data.detail as { message: string }).message;
    }
    if (typeof data.message === "string" && data.message.trim()) return data.message;
  } catch {
    // Ignore non-JSON error bodies and fall back to status text.
  }
  return `Request failed (${res.status} ${res.statusText})`;
}
