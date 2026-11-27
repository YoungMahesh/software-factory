import { NextResponse } from "next/server";
import { loadWorkspaceEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function GET() {
  loadWorkspaceEnv();
  return NextResponse.json({
    status: "ok",
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV ?? "development",
    apps_base_domain: process.env.APPS_BASE_DOMAIN?.trim() || null,
    deployer_commit: process.env.NEXT_PUBLIC_DASHBOARD_COMMIT?.trim() || null,
  });
}
