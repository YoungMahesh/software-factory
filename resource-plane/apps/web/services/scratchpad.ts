import { z } from "zod";
import pg from "pg";
import { getDatabase } from "./databases";
import { ensureSystemReady } from "./bootstrap";

export interface ExecuteSqlInput {
	databaseId: string;
	query: string;
}

export interface SqlExecutionResult {
	columns: string[];
	rows: Record<string, any>[];
	rowCount: number;
	executionTimeMs: number;
}

/**
 * Executes an arbitrary SQL query against a provisioned PostgreSQL database.
 * Connects using the database's dedicated role credentials and returns
 * structured column headers, row records, row count, and execution time in milliseconds.
 */
export async function executeSqlQuery(
	input: ExecuteSqlInput,
): Promise<SqlExecutionResult> {
	await ensureSystemReady().catch(() => {});

	const rawQuery = input.query?.trim();
	if (!rawQuery) {
		throw new Error("Query cannot be empty");
	}

	const dbRecord = await getDatabase(input.databaseId);
	if (!dbRecord) {
		throw new Error(`Database not found for ID "${input.databaseId}"`);
	}

	// Connect directly to the target database using its dedicated resource role credentials
	const client = new pg.Client({
		host: dbRecord.host,
		port: dbRecord.port,
		user: dbRecord.username,
		password: dbRecord.password,
		database: dbRecord.name,
	});

	try {
		await client.connect();
	} catch (err: any) {
		throw new Error(`Database connection failed: ${err.message}`);
	}

	return await runQueryOnClient(client, rawQuery);
}

async function runQueryOnClient(
	client: pg.Client,
	query: string,
): Promise<SqlExecutionResult> {
	const startTime = performance.now();
	try {
		const res = await client.query(query);
		const executionTimeMs =
			Math.round((performance.now() - startTime) * 100) / 100;

		// Handle single or multi-statement results
		const finalRes = Array.isArray(res) ? res[res.length - 1] : res;

		const columns: string[] = finalRes?.fields
			? finalRes.fields.map((f: any) => f.name)
			: [];

		const rows: Record<string, any>[] = Array.isArray(finalRes?.rows)
			? finalRes.rows
			: [];

		const rowCount: number =
			typeof finalRes?.rowCount === "number" ? finalRes.rowCount : rows.length;

		return {
			columns,
			rows,
			rowCount,
			executionTimeMs,
		};
	} catch (err: any) {
		throw new Error(err.message || "Failed to execute query");
	} finally {
		await client.end().catch(() => {});
	}
}

// ==========================================
// TanStack Start Server Function
// ==========================================

export const executeSqlSchema = z.object({
	databaseId: z.string().uuid("Valid database ID required"),
	query: z.string().min(1, "SQL query cannot be empty"),
});

export interface ExecuteSqlQueryFn {
	(input: { data: { databaseId: string; query: string } } | { databaseId: string; query: string }): Promise<SqlExecutionResult>;
	url: string;
}

export const executeSqlQueryFn: ExecuteSqlQueryFn = Object.assign(
	async (input: { data: { databaseId: string; query: string } } | { databaseId: string; query: string }) => {
		const data = "data" in input ? input.data : input;
		return executeSqlQuery(data);
	},
	{ url: "/api/scratchpad" },
);
