import { proxyControlPlaneRequest } from "@/lib/control-plane";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  return proxyControlPlaneRequest("/api/docs/deploy", {
    method: "POST",
    signal: request.signal,
  });
}
