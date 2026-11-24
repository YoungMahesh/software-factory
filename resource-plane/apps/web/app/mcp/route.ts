import { handleAuthenticatedMcpRequest } from "@/routes/mcp";

export async function POST(req: Request) {
  return handleAuthenticatedMcpRequest(req);
}
