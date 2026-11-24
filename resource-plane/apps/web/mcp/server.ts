import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { and, eq, or } from "drizzle-orm";
import { z } from "zod";
import { db } from "../db/index";
import { databases, objectStorages, projects } from "../db/schema";
import {
	CA_DOWNLOAD_PATH,
	getCaCertificate,
	getPublicPostgresHost,
} from "../services/certs";
import {
	createDatabase,
	type DatabaseCredentials,
	formatDatabaseCredentials,
	getDatabaseCredentials,
	listDatabases,
	sanitizeDatabaseName,
} from "../services/databases";
import {
	createProject,
	getProject,
	listProjects,
	type Project,
	type ProjectWithStats,
	slugify,
} from "../services/projects";
import {
	createObjectStorage,
	formatStorageCredentials,
	getStorageCredentials,
	listObjectStorages,
	type StorageCredentials,
} from "../services/storage";

/**
 * Resolves a project by ID or by name/slug.
 * Throws a descriptive error if neither or not found.
 */
export async function resolveProject(input: {
	projectId?: string;
	projectName?: string;
}): Promise<Project | ProjectWithStats> {
	const idOrName = input.projectId || input.projectName;
	if (!idOrName || !idOrName.trim()) {
		throw new Error("Either projectId or projectName must be provided");
	}

	const query = idOrName.trim();

	// 1. Try getProject (handles UUID or slug)
	const bySlugOrId = await getProject(query);
	if (bySlugOrId) {
		return bySlugOrId;
	}

	// 2. Try looking up directly by name or slugified name in projects table
	const slugified = slugify(query);
	const rows = await db
		.select()
		.from(projects)
		.where(or(eq(projects.name, query), eq(projects.slug, slugified)))
		.limit(1);

	if (rows.length > 0) {
		return rows[0];
	}

	throw new Error(`Project not found for identifier: ${idOrName}`);
}

/**
 * Resolves database credentials by databaseId or by databaseName (+ optional projectId).
 */
export async function resolveDatabaseCredentials(input: {
	databaseId?: string;
	databaseName?: string;
	projectId?: string;
}): Promise<DatabaseCredentials> {
	if (input.databaseId) {
		return await getDatabaseCredentials(input.databaseId);
	}

	if (input.databaseName) {
		const rawName = input.databaseName.trim();
		const sanitized = sanitizeDatabaseName(rawName);

		const conditions = [
			or(eq(databases.name, rawName), eq(databases.name, sanitized)),
		];

		if (input.projectId) {
			conditions.push(eq(databases.projectId, input.projectId));
		}

		const [found] = await db
			.select()
			.from(databases)
			.where(and(...conditions))
			.limit(1);

		if (!found) {
			throw new Error(`Database "${input.databaseName}" not found`);
		}

		return formatDatabaseCredentials(found);
	}

	throw new Error("Either databaseId or databaseName must be provided");
}

/**
 * Resolves storage credentials by storageId or by bucketName (+ optional projectId).
 */
export async function resolveStorageCredentials(input: {
	storageId?: string;
	bucketName?: string;
	projectId?: string;
}): Promise<StorageCredentials> {
	if (input.storageId) {
		const creds = await getStorageCredentials(input.storageId);
		if (!creds) {
			throw new Error(`Storage "${input.storageId}" not found`);
		}
		return creds;
	}

	if (input.bucketName) {
		const cleanBucketName = input.bucketName.trim().toLowerCase();
		const conditions = [eq(objectStorages.bucketName, cleanBucketName)];

		if (input.projectId) {
			conditions.push(eq(objectStorages.projectId, input.projectId));
		}

		const [found] = await db
			.select()
			.from(objectStorages)
			.where(and(...conditions))
			.limit(1);

		if (!found) {
			throw new Error(`Object storage bucket "${input.bucketName}" not found`);
		}

		return {
			id: found.id,
			projectId: found.projectId,
			bucketName: found.bucketName,
			accessKeyId: found.accessKeyId,
			secretAccessKey: found.secretAccessKey,
			endpoint: found.endpoint,
			region: found.region,
		};
	}

	throw new Error("Either storageId or bucketName must be provided");
}

/**
 * Factory function to create a new Neon Control Plane McpServer instance.
 * Exposes the non-destructive MCP tool suite (ADR 0003, ADR 0013, Spec US 18, 19).
 */
export function createNeonMcpServer(): McpServer {
	const server = new McpServer({
		name: "neon-control-plane",
		version: "1.0.0",
	});

	// 1. list_projects (Spec US 18)
	server.registerTool(
		"list_projects",
		{
			title: "List Projects",
			description:
				"Lists all projects with their ID, name, slug, region, databaseCount, storageCount, and createdAt.",
			inputSchema: {},
		},
		async () => {
			const projectList = await listProjects();
			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(projectList, null, 2),
					},
				],
			};
		},
	);

	// 2. create_project (Spec US 19)
	server.registerTool(
		"create_project",
		{
			title: "Create Project",
			description:
				"Creates a new project for grouping PostgreSQL databases and S3 object storages.",
			inputSchema: {
				name: z.string().describe("Name of the project"),
				region: z
					.string()
					.optional()
					.describe("Project region (optional, defaults to us-east-1)"),
			},
		},
		async ({ name, region }) => {
			const project = await createProject({ name, region });
			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(project, null, 2),
					},
				],
			};
		},
	);

	// 3. create_database
	server.registerTool(
		"create_database",
		{
			title: "Create Database",
			description:
				"Provisions an isolated PostgreSQL database with dedicated user role and credentials.",
			inputSchema: {
				projectId: z
					.string()
					.optional()
					.describe("Target project UUID (or provide projectName)"),
				projectName: z
					.string()
					.optional()
					.describe("Target project name or slug (or provide projectId)"),
				databaseName: z.string().describe("Name of the database to provision"),
			},
		},
		async ({ projectId, projectName, databaseName }) => {
			const project = await resolveProject({ projectId, projectName });
			const result = await createDatabase({
				projectId: project.id,
				name: databaseName,
			});

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(result, null, 2),
					},
				],
			};
		},
	);

	// 2. list_databases
	server.registerTool(
		"list_databases",
		{
			title: "List Databases",
			description: "Lists all provisioned PostgreSQL databases in a project.",
			inputSchema: {
				projectId: z.string().optional().describe("Project UUID"),
				projectName: z.string().optional().describe("Project name or slug"),
			},
		},
		async ({ projectId, projectName }) => {
			const project = await resolveProject({ projectId, projectName });
			const dbList = await listDatabases(project.id);

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(dbList, null, 2),
					},
				],
			};
		},
	);

	// 3. get_database_credentials
	server.registerTool(
		"get_database_credentials",
		{
			title: "Get Database Credentials",
			description:
				"Retrieves connection URI and credential parameters for a database by ID or name.",
			inputSchema: {
				databaseId: z.string().optional().describe("Database UUID"),
				databaseName: z.string().optional().describe("Database name"),
				projectId: z
					.string()
					.optional()
					.describe("Optional project UUID to disambiguate database name"),
			},
		},
		async ({ databaseId, databaseName, projectId }) => {
			const credentials = await resolveDatabaseCredentials({
				databaseId,
				databaseName,
				projectId,
			});

			const caCertificate = getCaCertificate();
			const publicHost = getPublicPostgresHost();
			const port = process.env.PORT || "3000";
			const caDownloadUrl = `http://${publicHost}:${port}${CA_DOWNLOAD_PATH}`;

			const payload = {
				...credentials,
				caCertificate,
				caDownloadUrl,
			};

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(payload, null, 2),
					},
				],
			};
		},
	);

	// 4. create_object_storage
	server.registerTool(
		"create_object_storage",
		{
			title: "Create Object Storage",
			description:
				"Provisions a new SeaweedFS S3 bucket with dedicated IAM credentials.",
			inputSchema: {
				projectId: z
					.string()
					.optional()
					.describe("Target project UUID (or provide projectName)"),
				projectName: z
					.string()
					.optional()
					.describe("Target project name or slug (or provide projectId)"),
				bucketName: z.string().describe("S3 bucket name"),
			},
		},
		async ({ projectId, projectName, bucketName }) => {
			const project = await resolveProject({ projectId, projectName });
			const storage = await createObjectStorage({
				projectId: project.id,
				bucketName,
			});

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(storage, null, 2),
					},
				],
			};
		},
	);

	// 5. list_object_storages
	server.registerTool(
		"list_object_storages",
		{
			title: "List Object Storages",
			description: "Lists all S3 object storage buckets in a project.",
			inputSchema: {
				projectId: z.string().optional().describe("Project UUID"),
				projectName: z.string().optional().describe("Project name or slug"),
			},
		},
		async ({ projectId, projectName }) => {
			const project = await resolveProject({ projectId, projectName });
			const storages = await listObjectStorages(project.id);

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify(storages, null, 2),
					},
				],
			};
		},
	);

	// 6. get_storage_credentials
	server.registerTool(
		"get_storage_credentials",
		{
			title: "Get Storage Credentials",
			description:
				"Retrieves S3 configuration bundle and credentials by ID or bucket name.",
			inputSchema: {
				storageId: z.string().optional().describe("Storage UUID"),
				bucketName: z.string().optional().describe("S3 bucket name"),
				projectId: z
					.string()
					.optional()
					.describe("Optional project UUID to disambiguate bucket name"),
			},
		},
		async ({ storageId, bucketName, projectId }) => {
			const credentials = await resolveStorageCredentials({
				storageId,
				bucketName,
				projectId,
			});
			const formatted = formatStorageCredentials(credentials);

			return {
				content: [
					{
						type: "text",
						text: JSON.stringify({ ...credentials, formatted }, null, 2),
					},
				],
			};
		},
	);

	return server;
}
