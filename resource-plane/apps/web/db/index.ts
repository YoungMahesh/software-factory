import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema";
import { getMasterDatabaseCredentials } from "../services/master-credentials";

const { Pool } = pg;

let globalPool: pg.Pool | null = null;
let currentConnectionString: string | null = null;
let drizzleInstance: ReturnType<typeof drizzle<typeof schema>> | null = null;

export function getDatabaseUrl(): string {
	if (process.env.DATABASE_URL) {
		return process.env.DATABASE_URL;
	}
	const host = process.env.POSTGRES_HOST || "localhost";
	const port = process.env.POSTGRES_PORT || "5432";
	const { username, password } = getMasterDatabaseCredentials();
	return `postgresql://${username}:${password}@${host}:${port}/neon_control_plane`;
}

export function getDb(
	connectionString?: string,
): ReturnType<typeof drizzle<typeof schema>> {
	const url = connectionString || getDatabaseUrl();
	if (!drizzleInstance || currentConnectionString !== url) {
		if (globalPool) {
			globalPool.end().catch(() => {});
		}
		currentConnectionString = url;
		globalPool = new Pool({ connectionString: url });
		globalPool.on("error", (err) => {
			console.error("Postgres pool unexpected error:", err);
		});
		drizzleInstance = drizzle(globalPool, { schema });
	}
	return drizzleInstance;
}

export const db = new Proxy({} as ReturnType<typeof drizzle<typeof schema>>, {
	get(_target, prop) {
		const instance = getDb();
		const val = (instance as any)[prop];
		if (typeof val === "function") {
			return val.bind(instance);
		}
		return val;
	},
});
