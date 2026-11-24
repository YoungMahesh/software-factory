import type { DatabaseCredentials } from "../lib/database-helpers";
export type { DatabaseCredentials };
import crypto from "node:crypto";
import { eq, sql } from "drizzle-orm";
import { z } from "zod";
import pg from "pg";
import { db } from "../db/index";
import { databases, projects } from "../db/schema";
import { ensureSystemReady, resolvePostgresPort } from "./bootstrap";
import { getMasterDatabaseCredentials } from "./master-credentials";

export interface DatabaseRecord {
	id: string;
	projectId: string;
	name: string;
	username: string;
	password: string;
	host: string;
	port: number;
	createdAt: Date;
}



export function sanitizeDatabaseName(name: string): string {
	const sanitized = name
		.trim()
		.toLowerCase()
		.replace(/[-\s]+/g, "_")
		.replace(/[^a-z0-9_]/g, "")
		.slice(0, 50);

	return sanitized;
}

export function formatDatabaseCredentials(
	dbRecord: DatabaseRecord,
): DatabaseCredentials {
	const { id, projectId, name, username, password, port, createdAt } = dbRecord;
	const resolvedHost =
		process.env.PUBLIC_POSTGRES_HOST ||
		process.env.PUBLIC_HOST ||
		dbRecord.host ||
		"localhost";
	const resolvedPort =
		process.env.PUBLIC_POSTGRES_PORT
			? Number.parseInt(process.env.PUBLIC_POSTGRES_PORT, 10)
			: (process.env.POSTGRES_PORT && process.env.POSTGRES_PORT !== "5432"
				? Number.parseInt(process.env.POSTGRES_PORT, 10)
				: (port && port !== 5432 ? port : 54320));

	const connectionString = `postgresql://${username}:${password}@${resolvedHost}:${resolvedPort}/${name}?sslmode=verify-full&sslrootcert=ca.crt`;
	const envSnippet = `DATABASE_URL="${connectionString}"`;
	const psqlCommand = `psql "${connectionString}"`;
	const psqlCommandRaw = `PGPASSWORD="${password}" PGSSLMODE=verify-full PGSSLROOTCERT=ca.crt psql -h ${resolvedHost} -p ${resolvedPort} -U ${username} -d ${name}`;

	const prismaSnippet = `// 1. Save ca.crt in your project root or prisma/ directory
// 2. Ensure DATABASE_URL includes ?sslmode=verify-full&sslrootcert=ca.crt

// prisma/schema.prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

// .env
DATABASE_URL="${connectionString}"`;

	const drizzleSnippet = `// db.ts
import fs from 'node:fs'
import { drizzle } from 'drizzle-orm/node-postgres'
import pg from 'pg'

const { Pool } = pg

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || "${connectionString}",
  ssl: {
    rejectUnauthorized: true,
    ca: fs.readFileSync('ca.crt').toString(),
  },
})

export const db = drizzle(pool)`;

	return {
		id,
		projectId,
		name,
		username,
		password,
		host: resolvedHost,
		port,
		createdAt,
		connectionString,
		envSnippet,
		psqlCommand,
		psqlCommandRaw,
		prismaSnippet,
		drizzleSnippet,
	};
}

export async function getAdminPgClient(): Promise<pg.Client> {
	const host = process.env.POSTGRES_HOST || "localhost";
	const port =
		host === "postgres" ? 5432 : await resolvePostgresPort();
	const { username, password } = getMasterDatabaseCredentials();
	const client = new pg.Client({
		host,
		port,
		user: username,
		password,
		database: "postgres",
	});
	await client.connect();
	return client;
}

export async function withAdminClient<T>(
	callback: (client: pg.Client) => Promise<T>,
): Promise<T> {
	const client = await getAdminPgClient();
	try {
		return await callback(client);
	} finally {
		await client.end().catch(() => {});
	}
}

export interface CreateDatabaseInput {
	projectId: string;
	name: string;
}

export async function createDatabase(
	input: CreateDatabaseInput,
): Promise<DatabaseCredentials> {
	await ensureSystemReady().catch(() => {});

	const rawName = input.name?.trim();
	if (!rawName) {
		throw new Error("Database name cannot be empty");
	}

	const sanitizedName = sanitizeDatabaseName(rawName);
	if (!sanitizedName) {
		throw new Error("Database name must contain alphanumeric characters");
	}

	// 1. Verify Project Exists
	const projectRows = await db
		.select({ id: projects.id })
		.from(projects)
		.where(eq(projects.id, input.projectId))
		.limit(1);

	if (projectRows.length === 0) {
		throw new Error("Project not found");
	}

	// 2. Check if database name already exists in control plane metadata
	const existingDb = await db
		.select({ id: databases.id })
		.from(databases)
		.where(eq(databases.name, sanitizedName))
		.limit(1);

	if (existingDb.length > 0) {
		throw new Error(`Database with name "${sanitizedName}" already exists`);
	}

	const port = await resolvePostgresPort();
	const host = process.env.POSTGRES_HOST || "localhost";

	// 3. Generate Dedicated Resource Role & Cryptographic Password
	const roleSuffix = crypto.randomBytes(4).toString("hex");
	const username = `${sanitizedName.slice(0, 16)}_u_${roleSuffix}`;
	const password = crypto.randomBytes(16).toString("hex");

	// 4. Execute Administrative DDL on PostgreSQL
	await withAdminClient(async (client) => {
		// Check if db already exists in PostgreSQL engine
		const checkRes = await client.query(
			"SELECT 1 FROM pg_database WHERE datname = $1",
			[sanitizedName],
		);
		if (checkRes.rowCount && checkRes.rowCount > 0) {
			throw new Error(
				`Database with name "${sanitizedName}" already exists in PostgreSQL`,
			);
		}

		// Step A: Create dedicated role with login password
		await client.query(
			`CREATE ROLE "${username}" WITH LOGIN PASSWORD '${password}';`,
		);

		try {
			// Step B: Create logical database owned by the dedicated role
			await client.query(
				`CREATE DATABASE "${sanitizedName}" OWNER "${username}";`,
			);

			// Step C: Revoke public connect from target database
			await client.query(
				`REVOKE CONNECT ON DATABASE "${sanitizedName}" FROM PUBLIC;`,
			);

			// Step D: Grant connect and all privileges strictly to dedicated role
			await client.query(
				`GRANT CONNECT ON DATABASE "${sanitizedName}" TO "${username}";`,
			);
			await client.query(
				`GRANT ALL PRIVILEGES ON DATABASE "${sanitizedName}" TO "${username}";`,
			);

			// Step E: Ensure cross-database connections to control plane and postgres are explicitly blocked
			await client
				.query(
					`REVOKE CONNECT ON DATABASE neon_control_plane FROM "${username}";`,
				)
				.catch(() => {});
			await client
				.query(`REVOKE CONNECT ON DATABASE postgres FROM "${username}";`)
				.catch(() => {});
		} catch (err) {
			// Clean up role if database creation failed
			await client.query(`DROP ROLE IF EXISTS "${username}";`).catch(() => {});
			throw err;
		}
	});

	// 5. Persist Metadata in neon_control_plane Drizzle Database
	let createdRecord: DatabaseRecord;
	try {
		const [inserted] = await db
			.insert(databases)
			.values({
				projectId: input.projectId,
				name: sanitizedName,
				username,
				password,
				host,
				port,
			})
			.returning();
		createdRecord = inserted;
	} catch (err) {
		// Rollback Postgres resources if metadata insert failed
		await withAdminClient(async (client) => {
			await client
				.query(`DROP DATABASE IF EXISTS "${sanitizedName}";`)
				.catch(() => {});
			await client.query(`DROP ROLE IF EXISTS "${username}";`).catch(() => {});
		}).catch(() => {});
		throw err;
	}

	return formatDatabaseCredentials(createdRecord);
}

export async function listDatabases(
	projectId: string,
): Promise<DatabaseCredentials[]> {
	await ensureSystemReady().catch(() => {});

	const rows = await db
		.select()
		.from(databases)
		.where(eq(databases.projectId, projectId))
		.orderBy(sql`${databases.createdAt} desc`);

	return rows.map(formatDatabaseCredentials);
}

export async function getDatabase(
	id: string,
): Promise<DatabaseCredentials | null> {
	await ensureSystemReady().catch(() => {});

	const rows = await db
		.select()
		.from(databases)
		.where(eq(databases.id, id))
		.limit(1);

	if (rows.length === 0) {
		return null;
	}

	return formatDatabaseCredentials(rows[0]);
}

export async function getDatabaseCredentials(
	databaseId: string,
): Promise<DatabaseCredentials> {
	const found = await getDatabase(databaseId);
	if (!found) {
		throw new Error("Database not found");
	}
	return found;
}

export async function resetDatabasePassword(
	databaseId: string,
	customPassword?: string,
): Promise<DatabaseCredentials> {
	await ensureSystemReady().catch(() => {});

	const found = await getDatabase(databaseId);
	if (!found) {
		throw new Error("Database not found");
	}

	const newPassword =
		customPassword?.trim() || crypto.randomBytes(16).toString("hex");
	const escapedPassword = newPassword.replace(/'/g, "''");

	// Update PostgreSQL user role password and terminate active connections
	await withAdminClient(async (client) => {
		// Terminate existing backends so old sessions are disconnected
		await client.query(
			"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid();",
			[found.name],
		);

		// Alter role password
		await client.query(
			`ALTER ROLE "${found.username}" WITH PASSWORD '${escapedPassword}';`,
		);
	});

	// Update Drizzle table record
	const [updated] = await db
		.update(databases)
		.set({ password: newPassword })
		.where(eq(databases.id, databaseId))
		.returning();

	return formatDatabaseCredentials(updated);
}

export async function deleteDatabase(
	databaseId: string,
): Promise<{ success: boolean; id: string }> {
	await ensureSystemReady().catch(() => {});

	const found = await getDatabase(databaseId);
	if (!found) {
		throw new Error("Database not found");
	}

	await withAdminClient(async (client) => {
		// 1. Terminate all active backend connections to the target database
		await client.query(
			"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid();",
			[found.name],
		);

		// 2. Drop the database
		try {
			await client.query(
				`DROP DATABASE IF EXISTS "${found.name}" WITH (FORCE);`,
			);
		} catch {
			await client.query(`DROP DATABASE IF EXISTS "${found.name}";`);
		}

		// 3. Drop the dedicated user role
		await client.query(`DROP ROLE IF EXISTS "${found.username}";`);
	});

	// 4. Delete record from Drizzle
	await db.delete(databases).where(eq(databases.id, databaseId));

	return { success: true, id: databaseId };
}

// ==========================================
// TanStack Start Server Functions
// ==========================================

export async function createDatabaseFn(opts: { data: { projectId: string; name: string } }): Promise<DatabaseCredentials> {
	return createDatabase(opts.data);
}
export async function listDatabasesFn(opts: { data: { projectId: string } } | string): Promise<DatabaseCredentials[]> {
	const projectId = typeof opts === "string" ? opts : opts.data.projectId;
	return listDatabases(projectId);
}
export async function getDatabaseCredentialsFn(opts: { data: { databaseId: string } } | string): Promise<DatabaseCredentials> {
	const databaseId = typeof opts === "string" ? opts : opts.data.databaseId;
	return getDatabaseCredentials(databaseId);
}
export async function resetDatabasePasswordFn(opts: { data: { databaseId: string; newPassword?: string } } | string): Promise<DatabaseCredentials> {
	const data = typeof opts === "string" ? { databaseId: opts } : opts.data;
	return resetDatabasePassword(data.databaseId, data.newPassword);
}
export async function deleteDatabaseFn(opts: { data: { databaseId: string } } | string): Promise<{ success: boolean; id: string }> {
	const databaseId = typeof opts === "string" ? opts : opts.data.databaseId;
	return deleteDatabase(databaseId);
}
