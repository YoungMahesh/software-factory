import { proxyDeployStatusById } from "@/lib/control-plane";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ deployId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { deployId } = await context.params;
  return proxyDeployStatusById("/api/dashboard/deploy", deployId, request.signal);
}
