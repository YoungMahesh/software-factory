import { listProjects } from "@/services/projects";
import DashboardHome from "./dashboard-home";

export const dynamic = "force-dynamic";

export default async function Page() {
  const projects = await listProjects().catch(() => []);
  return <DashboardHome initialProjects={projects} />;
}
