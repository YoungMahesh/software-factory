import { getProject } from "@/services/projects";
import { listDatabases } from "@/services/databases";
import { listObjectStorages } from "@/services/storage";
import ProjectDetailPage from "./project-detail-client";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const project = await getProject(projectId);
  if (!project) {
    notFound();
  }
  const databases = await listDatabases(project.id).catch(() => []);
  const storages = await listObjectStorages(project.id).catch(() => []);

  return (
    <ProjectDetailPage
      project={project}
      initialDatabases={databases}
      initialStorages={storages}
    />
  );
}
