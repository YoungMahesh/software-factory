import fs from "node:fs";
import path from "node:path";

/**
 * Loads environment variables from dashboard-deployer/.env and monorepo-root .env
 * without overriding variables already present in process.env.
 */
export function loadWorkspaceEnv(cwd: string = process.cwd()): void {
  const candidates = [
    path.resolve(cwd, ".env"),
    path.resolve(cwd, "../.env"),
  ];

  for (const envPath of candidates) {
    if (!fs.existsSync(/*turbopackIgnore: true*/ envPath)) continue;

    const raw = fs.readFileSync(/*turbopackIgnore: true*/ envPath, "utf-8");
    for (const rawLine of raw.split(/\r?\n/)) {
      let line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      if (line.startsWith("export ") || line.startsWith("export\t")) {
        line = line.slice(6).trim();
      }
      const eqIdx = line.indexOf("=");
      if (eqIdx <= 0) continue;

      const key = line.slice(0, eqIdx).trim();
      let val = line.slice(eqIdx + 1).trim();
      if (
        (val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))
      ) {
        val = val.slice(1, -1);
      }

      if (key && process.env[key] === undefined) {
        process.env[key] = val;
      }
    }
  }
}
