import { defineRelations } from "drizzle-orm";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import { resolveDatabaseConfig } from "./config";
import * as schema from "./schema";

const { connectionString, ssl } = resolveDatabaseConfig();

const pool = new Pool({
  connectionString,
  ...(ssl ? { ssl } : {}),
});

export const relations = defineRelations(schema);
export const db = drizzle({ client: pool, relations });
