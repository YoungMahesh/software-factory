import { getServicesHealth } from "@/services/bootstrap";

export async function GET() {
  const health = await getServicesHealth();
  return Response.json(health);
}
