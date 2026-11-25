import { defineConfig } from "drizzle-kit";
import { resolveDatabaseConfig } from "./db/config";

const { connectionString } = resolveDatabaseConfig();

export default defineConfig({
  schema: "./db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: connectionString,
  },
});
