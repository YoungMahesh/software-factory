import { NextResponse } from "next/server";
import type { HealthCheckResponse } from "@dashboard/types";
import { loadWorkspaceEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function GET() {
  loadWorkspaceEnv();
  const payload: HealthCheckResponse = {
    status: "ok",
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV ?? "development",
    apps_base_domain: process.env.APPS_BASE_DOMAIN?.trim() || null,
    dashboard_commit: process.env.NEXT_PUBLIC_DASHBOARD_COMMIT?.trim() || null,
  };
  return NextResponse.json(payload);
}
