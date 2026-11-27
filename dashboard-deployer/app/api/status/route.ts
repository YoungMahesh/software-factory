import { NextResponse } from "next/server";
import { gatherDeployerStatus } from "@/lib/control-plane";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const payload = await gatherDeployerStatus();
  return NextResponse.json(payload, {
    headers: { "Cache-Control": "no-store" },
  });
}
