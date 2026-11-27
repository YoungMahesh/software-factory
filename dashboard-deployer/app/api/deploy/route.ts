import { proxyControlPlaneRequest } from "@/lib/control-plane";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  return proxyControlPlaneRequest("/api/dashboard/deploy", {
    method: "POST",
    body: JSON.stringify({ target: "apex" }),
    signal: request.signal,
  });
}
