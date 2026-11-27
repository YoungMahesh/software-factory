import { proxyControlPlaneRequest } from "@/lib/control-plane";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ deployId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { deployId } = await context.params;
  if (!deployId || !/^[A-Za-z0-9_-]+$/.test(deployId)) {
    return Response.json({ detail: "Invalid deploy ID." }, { status: 400 });
  }
  return proxyControlPlaneRequest(`/api/dashboard/deploy/${encodeURIComponent(deployId)}`, {
    method: "GET",
    signal: request.signal,
  });
}
