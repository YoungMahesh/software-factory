import { eq, or, sql } from "drizzle-orm";
import { z } from "zod";
import { db } from "../db/index";
import { projects, databases, objectStorages } from "../db/schema";
import { ensureSystemReady } from "./bootstrap";

export interface Project {
	id: string;
	name: string;
	slug: string;
	region: string;
	createdAt: Date;
	updatedAt: Date;
}

export interface ProjectWithStats extends Project {
	databaseCount: number;
	storageCount: number;
}

export interface CreateProjectInput {
	name: string;
	slug?: string;
	region?: string;
}

export function slugify(text: string): string {
	const slug = text
		.toString()
		.toLowerCase()
		.trim()
		.replace(/\s+/g, "-") // Replace spaces with -
		.replace(/[^\w-]+/g, "") // Remove all non-word chars
		.replace(/--+/g, "-") // Replace multiple - with single -
		.replace(/^-+/, "") // Trim - from start of text
		.replace(/-+$/, ""); // Trim - from end of text

	return slug || "project";
}

export async function createProject(
	input: CreateProjectInput,
): Promise<Project> {
	await ensureSystemReady().catch(() => {});

	const trimmedName = input.name.trim();
	if (!trimmedName) {
		throw new Error("Project name cannot be empty");
	}

	const baseSlug = input.slug ? slugify(input.slug) : slugify(trimmedName);
	const region = input.region?.trim() || "us-east-1";

	// Ensure unique slug
	let finalSlug = baseSlug;
	let attempts = 0;
	while (attempts < 10) {
		const existing = await db
			.select({ id: projects.id })
			.from(projects)
			.where(eq(projects.slug, finalSlug))
			.limit(1);

		if (existing.length === 0) {
			break;
		}

		attempts++;
		const randomSuffix = Math.random().toString(36).substring(2, 7);
		finalSlug = `${baseSlug}-${randomSuffix}`;
	}

	const [created] = await db
		.insert(projects)
		.values({
			name: trimmedName,
			slug: finalSlug,
			region,
			updatedAt: new Date(),
		})
		.returning();

	return created;
}

export async function listProjects(): Promise<ProjectWithStats[]> {
	await ensureSystemReady().catch(() => {});

	const rows = await db
		.select({
			id: projects.id,
			name: projects.name,
			slug: projects.slug,
			region: projects.region,
			createdAt: projects.createdAt,
			updatedAt: projects.updatedAt,
			databaseCount: sql<number>`cast(count(distinct ${databases.id}) as integer)`,
			storageCount: sql<number>`cast(count(distinct ${objectStorages.id}) as integer)`,
		})
		.from(projects)
		.leftJoin(databases, eq(databases.projectId, projects.id))
		.leftJoin(objectStorages, eq(objectStorages.projectId, projects.id))
		.groupBy(projects.id)
		.orderBy(sql`${projects.createdAt} desc`);

	return rows;
}

export async function getProject(
	idOrSlug: string,
): Promise<ProjectWithStats | null> {
	await ensureSystemReady().catch(() => {});

	if (!idOrSlug) {
		return null;
	}

	const isUuid =
		/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
			idOrSlug,
		);

	const whereClause = isUuid
		? or(eq(projects.id, idOrSlug), eq(projects.slug, idOrSlug))
		: eq(projects.slug, idOrSlug);

	const rows = await db
		.select({
			id: projects.id,
			name: projects.name,
			slug: projects.slug,
			region: projects.region,
			createdAt: projects.createdAt,
			updatedAt: projects.updatedAt,
			databaseCount: sql<number>`cast(count(distinct ${databases.id}) as integer)`,
			storageCount: sql<number>`cast(count(distinct ${objectStorages.id}) as integer)`,
		})
		.from(projects)
		.leftJoin(databases, eq(databases.projectId, projects.id))
		.leftJoin(objectStorages, eq(objectStorages.projectId, projects.id))
		.where(whereClause)
		.groupBy(projects.id)
		.limit(1);

	return rows[0] || null;
}

export const createProjectSchema = z.object({
	name: z.string().min(1, "Project name is required").max(64),
	slug: z.string().max(64).optional(),
	region: z.string().optional(),
});

export async function listProjectsFn(): Promise<ProjectWithStats[]> {
	return listProjects();
}

export async function getProjectFn(opts: { data: string } | string): Promise<ProjectWithStats> {
	const idOrSlug = typeof opts === "object" && opts !== null && "data" in opts ? opts.data : opts;
	const p = await getProject(idOrSlug);
	if (!p) throw new Error("Project not found");
	return p;
}

export async function createProjectFn(opts: { data: { name: string; slug?: string; region?: string } }): Promise<Project> {
	return createProject(opts.data);
}
