import { NextResponse } from "next/server";
import type { HealthCheckResponse } from "@repo/types";

export async function GET() {
  const payload: HealthCheckResponse = {
    status: "ok",
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV ?? "development",
  };
  return NextResponse.json(payload);
}
